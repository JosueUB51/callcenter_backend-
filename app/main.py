from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os

from app.db import get_conn
from app.schemas import SearchRequest, SearchResult, CreateCaseRequest, FeedbackRequest
from app.embeddings import embed

app = FastAPI(title="CallCenter KB API")

SIMILARITY_THRESHOLD = 0.20

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        raise HTTPException(status_code=400, detail="Texto vacío")

    prompt = f"""
Convierte el siguiente texto hablado en una descripción clara y breve
de una incidencia ciudadana.

Ejemplos:

Entrada:
"eh buenas tardes no sirve el semáforo en cinco señores"

Salida:
"No funciona el semáforo en la zona de Cinco Señores."

Entrada:
"pues mire el camión de basura no pasó hoy"

Salida:
"No pasó el camión de recolección de basura."

Texto:
{text}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    clean = response.output_text.strip()

    return {"clean_text": clean}


# -----------------------------
# DETECTAR PROBLEMA EN CONVERSACIÓN
# -----------------------------
@app.post("/detect-problem")
def detect_problem(req: SearchRequest):

    text = (req.text or "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Texto vacío")

    prompt = f"""
Analiza la siguiente conversación entre un ciudadano y un operador.

Detecta el problema que el ciudadano está reportando.

Devuelve SOLO una frase clara que describa el problema.

Conversación:
{text}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
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
        raise HTTPException(status_code=400, detail="Texto vacío")

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
                    (case_id,)
                )

                conn.commit()

                return SearchResult(
                    found=True,
                    case_id=case_id,
                    solution_text=solution_text,
                    similarity=1.0
                )

            q_emb = embed(q)
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
                (case_id,)
            )

            conn.commit()

    return SearchResult(
        found=True,
        case_id=case_id,
        solution_text=solution_text,
        similarity=similarity
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
            detail="incident_text y solution_text son requeridos"
        )

    emb = embed(incident)
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
# FEEDBACK
# -----------------------------
@app.post("/feedback")
def feedback(req: FeedbackRequest):

    with get_conn() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT id FROM cases WHERE id = %s",
                (req.case_id,)
            )

            if not cur.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="case_id no existe"
                )

            if req.helpful:
                cur.execute(
                    "UPDATE cases SET times_helpful = times_helpful + 1 WHERE id = %s",
                    (req.case_id,)
                )

            conn.commit()

    return {"ok": True}