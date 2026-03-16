# Call Center

Aplicacion dividida en dos partes:

- `callcenter_front-main`: interfaz en React + Vite.
- `callcenter_backend--main`: API en FastAPI con PostgreSQL, `pgvector` y LM Studio.

El frontend escucha voz desde el navegador, detecta la incidencia y consulta una solucion sugerida al backend.

## Requisitos

- Node.js 18 o superior
- npm
- Python 3.10 o superior
- PostgreSQL con la extension `vector` (`pgvector`)
- LM Studio corriendo localmente con:
  - `openai/gpt-oss-20b`
  - `intfloat/multilingual-e5-large`
- Un navegador con soporte de `SpeechRecognition`
  - Recomendado: Chrome o Edge

## Estructura

```text
call/
|- callcenter_backend--main/
|  \- app/
\- callcenter_front-main/
```

## 1. Levantar el backend

Abre una terminal en `callcenter_backend--main`:

```powershell
cd callcenter_backend--main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r app/requirements.txt
```

### Si `python` o `py` no existen

Primero verifica si Python esta instalado:

```powershell
python --version
```

Si PowerShell responde que `python` no se reconoce, instala Python 3 y vuelve a abrir la terminal.

Ejemplo con `winget`:

```powershell
winget install -e --id Python.Python.3.12
```

Despues repite:

```powershell
cd callcenter_backend--main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r app/requirements.txt
```

Si PowerShell bloquea la activacion del entorno virtual, usa:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Variables de entorno

Crea un archivo `.env` dentro de `callcenter_backend--main` con este contenido:

```env
OPENAI_BASE_URL=http://localhost:1234/v1
OPENAI_API_KEY=lm-studio
LLM_MODEL=openai/gpt-oss-20b
EMBEDDING_MODEL=intfloat/multilingual-e5-large
ROUTING_BASE_URL=https://router.project-osrm.org
ROUTING_PROFILE=driving
DATABASE_URL=postgresql://usuario:password@localhost:5432/callcenter
```

`OPENAI_BASE_URL` apunta al servidor compatible con OpenAI de LM Studio. `OPENAI_API_KEY=lm-studio` es solo un valor dummy para el cliente Python.
`ROUTING_BASE_URL` y `ROUTING_PROFILE` controlan el servicio que convierte las paradas en una ruta sobre calles.

### Base de datos

La version ideal del proyecto usa `pgvector`, de modo que PostgreSQL calcula la similitud de embeddings directamente.

Lo que debes hacer en PostgreSQL para que el proyecto funcione es:

1. Crear la base de datos.
2. Entrar a esa base con `psql`.
3. Habilitar `pgvector`.
4. Recrear la tabla `cases` con `VECTOR(1024)`.
5. Crear un indice para acelerar busquedas vectoriales.

Ejemplo completo:

```sql
CREATE DATABASE callcenter;
```

Luego entra a la base:

```powershell
psql -U postgres -d callcenter
```

Ya dentro de `psql`, ejecuta:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS cases;

CREATE TABLE cases (
    id BIGSERIAL PRIMARY KEY,
    incident_text TEXT NOT NULL,
    solution_text TEXT NOT NULL,
    incident_embedding VECTOR(1024) NOT NULL,
    times_used INTEGER NOT NULL DEFAULT 0,
    times_helpful INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX cases_incident_embedding_idx
ON cases
USING ivfflat (incident_embedding vector_cosine_ops)
WITH (lists = 100);
```

Si quieres usar un usuario especifico para la aplicacion, puedes crearlo asi:

```sql
CREATE USER callcenter_user WITH PASSWORD 'tu_password';
GRANT ALL PRIVILEGES ON DATABASE callcenter TO callcenter_user;
```

Y despues usar en `.env` algo como:

```env
DATABASE_URL=postgresql://callcenter_user:tu_password@localhost:5432/callcenter
```

Para verificar que la extension, la tabla y el indice quedaron creados correctamente dentro de `psql`:

```sql
\dx
\d cases
\di cases_incident_embedding_idx
```

Con `intfloat/multilingual-e5-large`, la dimension correcta es `1024`.

Si venias de la version sin `pgvector`, el `DROP TABLE IF EXISTS cases;` elimina la tabla vieja para crear la nueva con el tipo correcto.

Si ya tenias casos guardados con embeddings de OpenAI, debes regenerarlos. No mezcles embeddings de modelos distintos en la misma columna.

### Ejecutar la API

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Prueba rapida:

```text
http://localhost:8000/health
```

Debe responder:

```json
{"ok": true}
```

## 2. Levantar el frontend

Abre otra terminal en `callcenter_front-main`:

```powershell
cd callcenter_front-main
npm install
npm run dev
```

Abre:

```text
http://localhost:5173
```

## 3. Flujo de ejecucion

1. Simula una llamada desde la interfaz.
2. Acepta la llamada.
3. El navegador activa el microfono.
4. El frontend envia el texto al backend en `/detect-problem`.
5. Luego consulta `/search` para obtener una solucion sugerida.

## Endpoints principales

- `GET /health`: estado del servicio
- `POST /clean`: limpia texto hablado
- `POST /detect-problem`: resume el problema detectado
- `POST /search`: busca una solucion
- `POST /cases`: crea un nuevo caso
- `POST /feedback`: registra feedback de utilidad

## Detalles importantes

- El frontend usa `http://localhost:8000` como API fija en [callcenter_front-main/src/App.jsx](/c:/Users/omarc/OneDrive/Desktop/Proyectos/Gob/call/callcenter_front-main/src/App.jsx).
- El backend solo permite CORS para `http://localhost:5173` en [callcenter_backend--main/app/main.py](/c:/Users/omarc/OneDrive/Desktop/Proyectos/Gob/call/callcenter_backend--main/app/main.py).
- Si cambias host o puerto en frontend, tambien debes actualizar CORS en el backend.
- Sin `OPENAI_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL` o `DATABASE_URL`, el backend no va a arrancar correctamente.

## Problemas comunes

### Error de conexion a la base de datos

Revisa que `DATABASE_URL` apunte a una base existente y que PostgreSQL este levantado.

### Error con `vector`

Si falla algo relacionado con `type "vector" does not exist`, entonces `pgvector` no esta instalado en tu servidor PostgreSQL o no ejecutaste:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Error con LM Studio o embeddings

Revisa que LM Studio este levantado en `http://localhost:1234`, que `openai/gpt-oss-20b` este cargado para respuestas y que `intfloat/multilingual-e5-large` este disponible para embeddings.

### No funciona el microfono

- Usa Chrome o Edge.
- Acepta permisos del navegador.
- Verifica que tu equipo tenga microfono activo.

## Ejecucion rapida

En dos terminales:

```powershell
# Terminal 1
cd callcenter_backend--main
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal 2
cd callcenter_front-main
npm install
npm run dev
```
