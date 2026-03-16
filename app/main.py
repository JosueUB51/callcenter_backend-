from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
from openai import OpenAI

from app.db import get_conn
from app.embeddings import embed_passage, embed_query
from app.schemas import (
    BinnibusRoute,
    BinnibusStop,
    CreateCaseRequest,
    FeedbackRequest,
    SearchRequest,
    SearchResult,
)
from app.settings import API_BASE_URL, API_KEY, LLM_MODEL, ROUTING_BASE_URL, ROUTING_PROFILE

app = FastAPI(title="CallCenter KB API")

SIMILARITY_THRESHOLD = 0.20

client = OpenAI(
    base_url=API_BASE_URL,
    api_key=API_KEY,
)


def build_fallback_path(stops: list[BinnibusStop]) -> list[list[float]]:
    return [[stop.latitude, stop.longitude] for stop in stops]


def get_route_path(stops: list[BinnibusStop]) -> list[list[float]]:
    if len(stops) < 2:
        return build_fallback_path(stops)

    coordinates = ";".join(f"{stop.longitude},{stop.latitude}" for stop in stops)
    url = (
        f"{ROUTING_BASE_URL}/route/v1/{ROUTING_PROFILE}/{coordinates}"
        "?overview=full&geometries=geojson&continue_straight=true"
    )

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        geometry = payload["routes"][0]["geometry"]["coordinates"]
        if geometry:
            return [[point[1], point[0]] for point in geometry]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        pass

    return build_fallback_path(stops)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


# -----------------------------
# LIMPIAR TEXTO CON IA
# -----------------------------
@app.post("/clean")
def clean_text(req: SearchRequest):
    text = (req.text or "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Texto vacio")

    prompt = f"""
Convierte el siguiente texto hablado en una descripcion clara y breve
de una incidencia ciudadana.

Ejemplos:

Entrada:
"eh buenas tardes no sirve el semaforo en cinco senores"

Salida:
"No funciona el semaforo en la zona de Cinco Senores."

Entrada:
"pues mire el camion de basura no paso hoy"

Salida:
"No paso el camion de recoleccion de basura."

Texto:
{text}
"""

    response = client.responses.create(
        model=LLM_MODEL,
        input=prompt,
    )

    clean = response.output_text.strip()
    return {"clean_text": clean}


# -----------------------------
# DETECTAR PROBLEMA EN CONVERSACION
# -----------------------------
@app.post("/detect-problem")
def detect_problem(req: SearchRequest):
    text = (req.text or "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Texto vacio")

    prompt = f"""
Analiza la siguiente conversacion entre un ciudadano y un operador.

Detecta el problema que el ciudadano esta reportando.

Devuelve SOLO una frase clara que describa el problema.

Conversacion:
{text}
"""

    response = client.responses.create(
        model=LLM_MODEL,
        input=prompt,
    )

    problem = response.output_text.strip()
    return {"problem": problem}


# -----------------------------
# SEARCH
# -----------------------------
@app.post("/search", response_model=SearchResult)
def search(req: SearchRequest):
    q = (req.text or "").strip().lower()

    if not q:
        raise HTTPException(status_code=400, detail="Texto vacio")

    like = f"%{q}%"

    with get_conn() as conn:
        with conn.cursor() as cur:
            sql_text = """
            SELECT id, incident_text, solution_text
            FROM cases
            WHERE incident_text ILIKE %s
               OR solution_text ILIKE %s
            LIMIT 1;
            """

            cur.execute(sql_text, (like, like))
            row = cur.fetchone()

            if row:
                case_id, incident_text, solution_text = row

                cur.execute(
                    "UPDATE cases SET times_used = times_used + 1 WHERE id = %s",
                    (case_id,),
                )

                conn.commit()

                return SearchResult(
                    found=True,
                    case_id=case_id,
                    solution_text=solution_text,
                    similarity=1.0,
                )

            q_emb = embed_query(q)
            q_vector = "[" + ",".join(map(str, q_emb)) + "]"

            sql_vector = """
            SELECT id, incident_text, solution_text,
                   1 - (incident_embedding <=> %s::vector) AS similarity
            FROM cases
            ORDER BY incident_embedding <=> %s::vector
            LIMIT 5;
            """

            cur.execute(sql_vector, (q_vector, q_vector))
            rows = cur.fetchall()

            if not rows:
                return SearchResult(found=False)

            best = max(rows, key=lambda r: r[3])

            case_id = best[0]
            solution_text = best[2]
            similarity = float(best[3])

            if similarity < SIMILARITY_THRESHOLD:
                return SearchResult(found=False)

            cur.execute(
                "UPDATE cases SET times_used = times_used + 1 WHERE id = %s",
                (case_id,),
            )

            conn.commit()

    return SearchResult(
        found=True,
        case_id=case_id,
        solution_text=solution_text,
        similarity=similarity,
    )


# -----------------------------
# CREAR CASO
# -----------------------------
@app.post("/cases")
def create_case(req: CreateCaseRequest):
    incident = (req.incident_text or "").strip().lower()
    solution = (req.solution_text or "").strip()

    if not incident or not solution:
        raise HTTPException(
            status_code=400,
            detail="incident_text y solution_text son requeridos",
        )

    emb = embed_passage(incident)
    emb_vector = "[" + ",".join(map(str, emb)) + "]"

    sql = """
    INSERT INTO cases (incident_text, solution_text, incident_embedding)
    VALUES (%s, %s, %s::vector)
    RETURNING id;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (incident, solution, emb_vector))
            new_id = cur.fetchone()[0]

            conn.commit()

    return {"id": new_id}


# -----------------------------
# BINNIBUS ROUTES
# -----------------------------
@app.get("/binnibus/routes", response_model=list[BinnibusRoute])
def get_binnibus_routes(codes: list[str] = Query(...)):
    normalized_codes = [code.strip().upper() for code in codes if code.strip()]

    if not normalized_codes:
        raise HTTPException(status_code=400, detail="codes es requerido")

    sql = """
    SELECT
        r.id,
        r.route_code,
        r.route_name,
        r.origin,
        r.destination,
        r.display_name,
        r.description,
        s.stop_order,
        s.stop_name,
        s.latitude,
        s.longitude,
        s.description
    FROM binnibus_routes r
    LEFT JOIN binnibus_stops s ON s.route_id = r.id
    WHERE r.route_code = ANY(%s)
    ORDER BY r.route_code, s.stop_order;
    """

    routes_by_code = {}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (normalized_codes,))
            rows = cur.fetchall()

    for row in rows:
        route_code = row[1]
        route = routes_by_code.get(route_code)

        if route is None:
            route = {
                "route_code": row[1],
                "route_name": row[2],
                "origin": row[3],
                "destination": row[4],
                "display_name": row[5],
                "description": row[6],
                "stops": [],
                "path": [],
            }
            routes_by_code[route_code] = route

        if row[7] is not None:
            route["stops"].append(
                BinnibusStop(
                    stop_order=row[7],
                    stop_name=row[8],
                    latitude=float(row[9]),
                    longitude=float(row[10]),
                    description=row[11],
                )
            )

    result = []
    for code in normalized_codes:
        route = routes_by_code.get(code)
        if route is None:
            continue

        ordered_stops = sorted(route["stops"], key=lambda stop: stop.stop_order)
        route["stops"] = ordered_stops
        route["path"] = get_route_path(ordered_stops)
        result.append(route)

    return result


# -----------------------------
# FEEDBACK
# -----------------------------
@app.post("/feedback")
def feedback(req: FeedbackRequest):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM cases WHERE id = %s",
                (req.case_id,),
            )

            if not cur.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="case_id no existe",
                )

            if req.helpful:
                cur.execute(
                    "UPDATE cases SET times_helpful = times_helpful + 1 WHERE id = %s",
                    (req.case_id,),
                )

            conn.commit()

    return {"ok": True}
