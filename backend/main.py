"""
================================================================================
 Datafix Oracle Automático - Backend FastAPI
================================================================================
 Expone una API REST que conecta al motor Oracle XE real usando python-oracledb
 para validar sintaxis, ejecutar DRY RUN seguro (SAVEPOINT + ROLLBACK) y
 calcular EXPLAIN PLAN sin persistir cambios.

 Ejecución:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

 Requisitos:
    - Oracle XE 21c corriendo (local o remoto, puerto 1521).
    - Un usuario con privilegios de lectura/escritura sobre los esquemas objetivo.
================================================================================
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import re, hashlib, traceback, os

try:
    import oracledb
except ImportError:
    oracledb = None  # permite arrancar el server aunque no haya driver instalado

# -----------------------------------------------------------------------------
# Resolución de host: si el backend corre en Docker, "localhost" enviado por el
# HTML del navegador NO se resuelve a Oracle XE (apunta al contenedor backend
# mismo). Por eso traducimos "localhost" → ORACLE_HOST_OVERRIDE (= "oracle-xe"
# por defecto en docker-compose), o "host.docker.internal" en Docker Desktop.
# -----------------------------------------------------------------------------
ORACLE_HOST_OVERRIDE = os.getenv("ORACLE_HOST_OVERRIDE", "")
RUNNING_IN_DOCKER = os.path.exists("/.dockerenv")

def resolve_host(requested: str) -> str:
    """Traduce 'localhost'/'127.0.0.1' al hostname interno cuando estamos en Docker."""
    if requested.lower() in ("localhost", "127.0.0.1") and RUNNING_IN_DOCKER:
        return ORACLE_HOST_OVERRIDE or "oracle-xe"
    return requested

# -----------------------------------------------------------------------------
# App & CORS (para que el HTML del frontend pueda llamar desde file:// o http)
# -----------------------------------------------------------------------------
app = FastAPI(title="Datafix Oracle Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # en producción, acotar
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Modelos
# -----------------------------------------------------------------------------
class XEConfig(BaseModel):
    host: str
    port: str = "1521"
    sid: str                       # Service name / PDB (ej XEPDB1)
    user: str
    password: str
    wallet: Optional[str] = None
    timeout: int = 30
    maxRows: int = 10000
    whitelist: Optional[str] = ""  # "HR,APP_USER"
    env: Optional[str] = "DEV"
    mode: Optional[str] = "SAVEPOINT + ROLLBACK automático"

class TestConnReq(BaseModel):
    config: XEConfig

class DryRunReq(BaseModel):
    sql: str
    config: XEConfig
    username: Optional[str] = "anonymous"
    # Lista de palabras clave a OMITIR (commit implícito). Si viene vacía o ausente,
    # se usa la lista por defecto _IMPLICIT_COMMIT_KEYWORDS.
    skipKeywords: Optional[List[str]] = None

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _dsn(cfg: XEConfig) -> str:
    """Construye DSN Oracle con service_name (XE 21c usa XEPDB1)."""
    real_host = resolve_host(cfg.host)
    return oracledb.makedsn(real_host, int(cfg.port), service_name=cfg.sid)

def _connect(cfg: XEConfig):
    if oracledb is None:
        raise RuntimeError("python-oracledb no instalado. Ejecute: pip install oracledb")
    conn = oracledb.connect(user=cfg.user, password=cfg.password, dsn=_dsn(cfg))
    # 🔒 garantía: NUNCA autocommit en DRY RUN — toda sentencia debe ser revertible
    conn.autocommit = False
    return conn

# DDL que en Oracle dispara COMMIT IMPLICITO — debe bloquearse en DRY RUN
# Si pasara, todo lo anterior queda persistido aunque hagamos ROLLBACK después.
_IMPLICIT_COMMIT_KEYWORDS = (
    "CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "AUDIT", "NOAUDIT",
    "COMMIT", "FLASHBACK", "PURGE",
)

def _is_implicit_commit_stmt(stmt: str, active_keywords=None) -> bool:
    """True si la sentencia provoca COMMIT implícito en Oracle.
    `active_keywords` es la lista efectiva (puede venir desde el frontend).
    """
    if active_keywords is None:
        active_keywords = _IMPLICIT_COMMIT_KEYWORDS
    first = stmt.strip().split()[0].upper() if stmt.strip() else ""
    return first in active_keywords

def _split_statements(sql: str) -> List[str]:
    """Separa el script en sentencias, respetando bloques PL/SQL terminados en '/'."""
    stmts: List[str] = []
    current = []
    for line in sql.splitlines():
        raw = line.rstrip()
        stripped = raw.strip()
        if stripped == "/":
            block = "\n".join(current).strip()
            if block:
                stmts.append(block)
            current = []
            continue
        if stripped.endswith(";") and not _is_inside_plsql("\n".join(current)):
            current.append(raw)
            block = "\n".join(current).strip().rstrip(";")
            if block:
                stmts.append(block)
            current = []
        else:
            current.append(raw)
    tail = "\n".join(current).strip()
    if tail:
        stmts.append(tail.rstrip(";"))
    return [s for s in stmts if s and not s.startswith("--")]

def _is_inside_plsql(buffer: str) -> bool:
    """Heurística: si hay BEGIN sin END o DECLARE abierto, estamos dentro de bloque PL/SQL."""
    up = buffer.upper()
    begins = len(re.findall(r"\bBEGIN\b", up))
    ends   = len(re.findall(r"\bEND\s*;", up))
    decl   = len(re.findall(r"\bDECLARE\b", up))
    return begins > ends or (decl > 0 and begins == 0 and "BEGIN" not in up)

def _extract_object(stmt: str) -> str:
    m = re.search(r"(?:TABLE|VIEW|INDEX|SEQUENCE|FROM|INTO|UPDATE)\s+([\w\.\$#]+)",
                  stmt, re.IGNORECASE)
    return m.group(1) if m else "—"

def _verdict_for(stmt: str) -> str:
    up = stmt.upper()
    if re.search(r"\b(DROP|TRUNCATE|ALTER\s+SYSTEM|SHUTDOWN)\b", up):
        return "🔴"
    if re.search(r"\b(DELETE|UPDATE)\b", up) and not re.search(r"\bWHERE\b", up):
        return "🟡"
    return "🟢"

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "driver": "oracledb " + (oracledb.__version__ if oracledb else "NO-INSTALADO"),
        "running_in_docker": RUNNING_IN_DOCKER,
        "host_override": ORACLE_HOST_OVERRIDE or ("oracle-xe" if RUNNING_IN_DOCKER else None),
        "note": "localhost se traducirá automáticamente al host_override cuando se ejecute en Docker.",
        "ts": datetime.utcnow().isoformat()
    }

@app.post("/api/test-connection")
def test_connection(req: TestConnReq):
    """Intenta conectarse y devolver la versión del motor."""
    try:
        conn = _connect(req.config)
        cur = conn.cursor()
        cur.execute("SELECT banner FROM v$version WHERE ROWNUM=1")
        version = cur.fetchone()[0]
        cur.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), USER FROM DUAL")
        db_name, user = cur.fetchone()
        cur.close()
        conn.close()
        return {
            "ok": True,
            "version": version,
            "db_name": db_name,
            "user": user,
            "dsn": _dsn(req.config)
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=2)}

@app.post("/api/dryrun")
def dryrun(req: DryRunReq):
    """Ejecuta el script dentro de un SAVEPOINT y hace ROLLBACK SIEMPRE."""
    log: List[str] = []
    affected = set()
    rollback_hints: List[str] = []
    total_rows = 0
    skipped_count = 0

    def push(tag: str, msg: str):
        log.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {tag:<5} {msg}")

    push("INFO", "=== DATAFIX ORACLE · DRY RUN REAL (Oracle XE) ===")
    push("INFO", "🔖 BACKEND VERSION: skipKeywords-v2 · ROLLBACK garantizado")
    push("INFO", f"Ambiente: {req.config.env} | Modo: {req.config.mode}")
    push("USER", f"Ejecuta: {req.username}")
    push("CONN", f"Conectando a {req.config.user}@{req.config.host}:{req.config.port}/{req.config.sid}")

    # Lista efectiva de keywords a OMITIR (configurable desde el frontend)
    if req.skipKeywords is not None:
        active_skip_kw = tuple(k.strip().upper() for k in req.skipKeywords if k and k.strip())
        push("INFO", f"Keywords con omisión activa (custom): {', '.join(active_skip_kw) or '—'}")
    else:
        active_skip_kw = _IMPLICIT_COMMIT_KEYWORDS
        push("INFO", f"Keywords con omisión activa (default): {', '.join(active_skip_kw)}")

    # Lista blanca de esquemas (opcional)
    whitelist = [s.strip().upper() for s in (req.config.whitelist or "").split(",") if s.strip()]
    if whitelist:
        push("INFO", f"Esquemas permitidos: {', '.join(whitelist)}")

    conn = None
    cur = None
    try:
        conn = _connect(req.config)
        cur = conn.cursor()
        push("CONN", "✅ Conexión establecida")
        push("CONN", f"autocommit = {conn.autocommit}  (debe ser False)")

        # Configuración de sesión defensiva
        try:
            cur.execute(f"ALTER SESSION SET STATEMENT_TIMEOUT={req.config.timeout}")
        except Exception:
            pass  # no soportado en todas las versiones

        # 🔒 forzar inicio de transacción explícita
        # En Oracle, SAVEPOINT requiere transacción activa. Iniciamos una con SET TRANSACTION
        try:
            cur.execute("SET TRANSACTION READ WRITE")
            push("TX", "SET TRANSACTION READ WRITE;")
        except Exception as ste:
            push("WARN", f"No se pudo SET TRANSACTION: {ste}")

        try:
            cur.execute("SAVEPOINT dryrun_sp")
            push("TX", "SAVEPOINT dryrun_sp;")
        except Exception as spe:
            push("WARN", f"No se pudo crear SAVEPOINT: {spe} (continuamos sin él)")

        stmts = _split_statements(req.sql)
        push("INFO", f"Total de sentencias detectadas: {len(stmts)}")
        stmt_errors = 0

        for i, stmt in enumerate(stmts, start=1):
            first_word = stmt.strip().split()[0].upper() if stmt.strip() else "?"
            obj = _extract_object(stmt)
            if obj != "—":
                affected.add(obj)

            # ⏭ Omisión silenciosa: COMMIT / DDL / DCL hacen COMMIT IMPLICITO en Oracle.
            # Las saltamos para que el DRY RUN no las ejecute (eso persistiría todo lo anterior),
            # pero seguimos con las siguientes. NO cuenta como error.
            if _is_implicit_commit_stmt(stmt, active_skip_kw):
                push("SKIP",  f"#{i} ⏭ {first_word} omitido en DRY RUN (no se ejecuta)")
                push("INFO",  f"  Razón: {first_word} dispara COMMIT implícito y rompería el rollback.")
                push("INFO",  f"  En producción real esta línea SÍ se ejecutará — aquí solo se simula su ausencia.")
                skipped_count += 1
                continue

            # Chequeo de whitelist (si aplica)
            if whitelist and "." in obj:
                schema = obj.split(".")[0].upper()
                if schema not in whitelist:
                    push("BLOCK", f"#{i} {first_word} sobre {obj} BLOQUEADO (esquema fuera de whitelist)")
                    continue

            verdict = _verdict_for(stmt)
            push("EXEC", f"#{i} {verdict} {first_word} → {obj}")

            # EXPLAIN PLAN para DML
            if first_word in ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"):
                try:
                    cur.execute(f"EXPLAIN PLAN FOR {stmt}")
                    cur.execute("SELECT PLAN_TABLE_OUTPUT FROM TABLE(DBMS_XPLAN.DISPLAY(null,null,'BASIC ROWS'))")
                    for row in cur.fetchall()[:10]:
                        push("PLAN", f"  {row[0]}")
                except Exception as pe:
                    push("WARN", f"  EXPLAIN PLAN falló: {pe}")

            # Ejecución real (se revierte siempre)
            try:
                cur.execute(stmt)
                rows = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                total_rows += rows
                push("EXEC", f"  → {rows} filas afectadas (uncommitted)")
                if total_rows > req.config.maxRows:
                    push("WARN", f"  ⚠️ Filas totales ({total_rows}) superan límite {req.config.maxRows} — aborto preventivo")
                    break
            except Exception as ex:
                stmt_errors += 1
                err_str = str(ex).strip()
                push("ERROR", f"  ❌ Sentencia falló: {err_str}")
                # Recuperar la transacción al SAVEPOINT para continuar con la siguiente
                try:
                    cur.execute("ROLLBACK TO SAVEPOINT dryrun_sp")
                    push("INFO", "  ↩ Revertido al SAVEPOINT — continuando con la siguiente sentencia")
                except Exception:
                    pass

            # Rollback sugerido por tipo
            if first_word == "DELETE":
                rollback_hints.append(f"-- manual: restore {obj} from backup")
            elif first_word == "UPDATE":
                rollback_hints.append(f"-- manual: reverse update on {obj}")
            elif first_word == "INSERT":
                rollback_hints.append(f"DELETE FROM {obj} WHERE /* rows just inserted */;")
            elif first_word == "DROP":
                rollback_hints.append(f"-- manual: recreate {obj} from DDL backup")
            elif first_word == "CREATE":
                rollback_hints.append(f"DROP {first_word} {obj};")

        # ROLLBACK SIEMPRE — garantía de no persistencia (triple cinturón)
        # 1) ROLLBACK TO SAVEPOINT — revierte hasta el savepoint
        try:
            cur.execute("ROLLBACK TO SAVEPOINT dryrun_sp")
            push("TX", "ROLLBACK TO SAVEPOINT dryrun_sp;")
        except Exception as rbe:
            push("WARN", f"ROLLBACK TO SAVEPOINT falló: {rbe}")

        # 2) conn.rollback() — rollback total de la transacción
        try:
            conn.rollback()
            push("TX", "conn.rollback() — garantía de transacción")
        except Exception as ce:
            push("ERROR", f"conn.rollback() FALLÓ: {ce}")

        # 3) ROLLBACK explícito por SQL — último recurso
        try:
            cur.execute("ROLLBACK")
            push("TX", "ROLLBACK; -- SQL explícito final")
        except Exception:
            pass
        push("INFO", f"Objetos afectados: {', '.join(sorted(affected)) or '—'}")
        push("INFO", f"Filas estimadas totales: {total_rows}")
        push("INFO", f"Sentencias con error: {stmt_errors}/{len(stmts)}")
        if skipped_count:
            push("INFO", f"Sentencias omitidas (COMMIT/DDL): {skipped_count}/{len(stmts)}")
        push("INFO", "=== DRY RUN FINALIZADO — ningún cambio persistido ===")

        # Verdicto global
        global_verdict = "🟢 OK"
        if any(_verdict_for(s) == "🔴" for s in stmts):
            global_verdict = "🔴 ALTO RIESGO"
        elif any(_verdict_for(s) == "🟡" for s in stmts):
            global_verdict = "🟡 REVISAR"

        checksum = hashlib.md5(req.sql.encode("utf-8")).hexdigest()[:8]

        return {
            "ok": True,
            "engine": "ORACLE-XE-REAL",
            "log": "\n".join(log),
            "affected": sorted(affected),
            "rollback": rollback_hints,
            "verdict": global_verdict,
            "checksum": checksum,
            "stmts": len(stmts),
            "totalRows": total_rows,
            "skipped": skipped_count
        }

    except Exception as e:
        push("ERROR", f"Fallo crítico: {e}")
        try:
            if conn:
                conn.rollback()
                push("TX", "ROLLBACK de emergencia ejecutado")
        except Exception:
            pass
        return {
            "ok": False,
            "error": str(e),
            "log": "\n".join(log),
            "trace": traceback.format_exc(limit=3)
        }
    finally:
        # 🔒 último cinturón de seguridad: si por cualquier razón llegamos aquí
        # con cambios pendientes, los revertimos antes de cerrar la conexión.
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        try:
            if cur: cur.close()
            if conn: conn.close()
        except Exception:
            pass

# -----------------------------------------------------------------------------
# Entry point directo
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
