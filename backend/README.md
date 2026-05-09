# Datafix Oracle - Backend FastAPI

Backend que conecta el frontend HTML con un motor **Oracle XE real** usando
`python-oracledb` para ejecutar DRY RUN seguros (SAVEPOINT + ROLLBACK garantizado).

## Arquitectura

```
┌────────────────────┐      HTTP/JSON      ┌──────────────────┐     TNS      ┌────────────┐
│ datafix_oracle.html│ ──────────────────▶ │ FastAPI backend  │ ───────────▶ │ Oracle XE  │
│   (navegador)      │                     │  main.py :8000   │              │  :1521     │
└────────────────────┘                     └──────────────────┘              └────────────┘
```

## Opción A — Docker (recomendado)

Levanta Oracle XE 21c **+** el backend en un solo comando:

```bash
cd backend
docker compose up -d
```

- Oracle XE: `localhost:1521/XEPDB1` (SYS password: `OraclePwd1`)
- Backend: `http://localhost:8000/api/health`

El script `init/01_create_appuser.sql` se ejecuta la primera vez y crea el
usuario `appuser/app123` con tablas de ejemplo (`employees`, `audit_log`).

La primera vez tarda ~5 min en inicializar Oracle XE. Monitorea con:
```bash
docker logs -f oracle-xe
```

## Opción B — Instalación local (sin Docker)

1. **Instala Oracle XE** descargando desde
   <https://www.oracle.com/database/technologies/xe-downloads.html>
   o usando el contenedor oficial:
   ```bash
   docker run -d --name oracle-xe \
     -p 1521:1521 \
     -e ORACLE_PWD=OraclePwd1 \
     container-registry.oracle.com/database/express:21.3.0-xe
   ```

2. **Crea el usuario appuser** (conéctate como SYS y ejecuta el contenido de
   `init/01_create_appuser.sql`).

3. **Instala el backend Python**:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate          # Linux/Mac
   .venv\Scripts\activate             # Windows
   pip install -r requirements.txt
   ```

4. **Arranca**:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

5. Abre <http://localhost:8000/docs> para ver la API interactiva (Swagger).

## Endpoints

### `GET /api/health`
Verifica que el servicio está vivo.
```json
{ "status": "ok", "driver": "oracledb 2.4.1", "ts": "2026-04-23T18:00:00" }
```

### `POST /api/test-connection`
Prueba credenciales contra Oracle XE.
```json
// Request
{
  "config": {
    "host":"localhost","port":"1521","sid":"XEPDB1",
    "user":"appuser","password":"app123"
  }
}

// Response
{ "ok": true, "version":"Oracle Database 21c Express Edition …", "db_name":"XE", "user":"APPUSER" }
```

### `POST /api/dryrun`
Ejecuta el script dentro de `SAVEPOINT dryrun_sp` y hace `ROLLBACK` SIEMPRE.

Incluye:
- `EXPLAIN PLAN` para cada DML.
- Conteo real de filas afectadas (`cur.rowcount`).
- Bloqueo por **whitelist de esquemas**.
- Corte por **maxRows** configurable.
- Rollback explícito en `finally` ante cualquier excepción.

```json
// Request
{
  "sql": "UPDATE appuser.employees SET salary = salary*1.05 WHERE department_id=50;",
  "config": {
    "host":"localhost","port":"1521","sid":"XEPDB1",
    "user":"appuser","password":"app123",
    "timeout":30,"maxRows":10000,"whitelist":"APPUSER,HR"
  },
  "username":"dev"
}
```

## Integración con el frontend

El archivo `datafix_oracle.html` ya tiene integrado un cliente que, cuando el
motor XE está habilitado, llama a este backend en `http://localhost:8000` para:

- Botón **🔌 Test Connection**
- Botón **🧪 DRY RUN**

La URL del backend se configura en la pestaña **Oracle XE** del HTML (campo
"Backend URL", por defecto `http://localhost:8000`).

## Seguridad

- **Nunca** ejecutes este backend contra producción: usa una BD sandbox.
- El usuario `appuser` del ejemplo tiene permisos mínimos (`CONNECT, RESOURCE`).
- Para producción, reemplaza CORS `allow_origins=["*"]` por tu dominio real.
- Considera agregar autenticación JWT al endpoint `/api/dryrun`.

## Tests rápidos (curl)

```bash
# Health
curl http://localhost:8000/api/health

# Test connection
curl -X POST http://localhost:8000/api/test-connection \
  -H "Content-Type: application/json" \
  -d '{"config":{"host":"localhost","port":"1521","sid":"XEPDB1","user":"appuser","password":"app123"}}'

# Dry run
curl -X POST http://localhost:8000/api/dryrun \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT COUNT(*) FROM appuser.employees;","config":{"host":"localhost","port":"1521","sid":"XEPDB1","user":"appuser","password":"app123"},"username":"test"}'
```
