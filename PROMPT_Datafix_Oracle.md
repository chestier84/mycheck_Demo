# Prompt — Datafix Oracle Automático

Pega este prompt en otra IA (Claude, ChatGPT, Cursor, etc.) para que reconstruya el sistema y los servicios.

---

## PROMPT (copiar desde aquí)

Construye una plataforma web llamada **"Datafix Oracle Automático"** que valida, audita y simula scripts SQL/PLSQL contra Oracle XE antes de tocar producción. La idea es reemplazar el "checklist mental" del DBA senior por reglas codificadas + simulación segura. Es un producto SaaS para equipos de bases de datos en banca y seguros.

### Objetivo de negocio

Reducir el ciclo de un datafix Oracle de 14-40 h a 3.5-7.5 h (-75%), con -80% de impacto en falla, -90% de issues por script, +60% de velocidad de despliegue. Suscripción mensual fija por organización (sin licencia por usuario).

### Las 4 capacidades obligatorias

1. **Validador de sintaxis SQL/PLSQL** — detecta errores antes de pasar al DBA, resaltado de línea con sugerencias.
2. **Auditor de reglas Oracle** — 25+ reglas codificadas con tres niveles de severidad (CRITICO bloquea, ALTO alerta, MEDIO sugiere). Reglas críticas: `UPDATE/DELETE sin WHERE`, `TRUNCATE`, `DROP`, `ALTER SYSTEM`. Reglas altas: `GRANT a usuario directo`, `sin COMMIT explícito`, `lock > 100k filas`. Reglas medias: `sin SAVEPOINT`, `tipos de dato implícitos`.
3. **DRY RUN tipo Liquibase** — ejecuta el script en una sesión real con `SAVEPOINT pre_datafix` + `ROLLBACK TO pre_datafix` garantizado en try/finally. Reporta filas afectadas y tiempo, sin tocar la base productiva.
4. **Reporte de Score (max 100)** — fórmula `SCORE = 100 − 25 × CRITICO − 10 × ALTO − 3 × MEDIO`. Score ≥ 90 ⇒ auto-aprobación. 70-89 ⇒ aprobado con observaciones. <70 ⇒ rechazado. Botón **Exportar Reporte** genera PDF con score, hallazgos, log y recomendación, anexable al ticket de cambio.

### Stack técnico

- **Frontend:** un solo archivo `datafix_oracle.html` con TailwindCSS por CDN y JavaScript vanilla. Sin build, sin bundler.
- **Backend:** FastAPI + python-oracledb. Tres endpoints: `GET /api/health`, `POST /api/test-connection`, `POST /api/dryrun`.
- **DB:** Oracle XE 21c en Docker (`container-registry.oracle.com/database/express:21.3.0-xe`).
- **Reverse proxy:** nginx:alpine, sirve el HTML en `/` y proxypass a `backend:8000` en `/api/*` (resuelve CORS por mismo origen).
- **Orquestación:** `docker-compose.yml` con tres servicios (`oracle-xe`, `backend`, `frontend`) en una red interna.

### Página web — estructura

**Login modal fullscreen** al entrar — usuario `admin` / contraseña `admin123` (demo hardcoded).

**Header** con logo, saludo "Hola, {username}" y botón "Salir".

**5 pestañas principales:**

1. **📝 Editor SQL** (default) — layout de 2 columnas:
   - Izquierda: `<textarea>` monospace + botones `🧹 Limpiar`, `📂 Cargar`, `💾 Guardar` y los 5 botones de acción: `🔍 Validar Sintaxis`, `⚖️ Auditoría`, `🧪 DRY RUN`, `🚀 Ejecutar Todo`, `📄 Exportar Reporte`.
   - Derecha: panel de resultados con 4 sub-pestañas: **Sintaxis** (errores línea por línea), **Auditoría** (tabla con regla / severidad / línea / acción), **DRY RUN** (log estilo terminal con timestamps), **Puntaje** (gauge SVG con score numérico, fórmula y desglose).

2. **👥 Mantenedor** — 5 sub-pestañas: **Usuarios** (CRUD), **Grupos AD** (con botón "Importar desde AD"), **Roles**, **Permisos** (matriz validar/auditar/dry-run/exportar/config/mantener), **Auditoría** (log inmutable con exportar CSV).

3. **🗄️ Oracle XE** — formulario de configuración: host, port (1521), SID (XEPDB1), usuario, password, wallet, timeout, max rows, whitelist de esquemas, ambiente (DEV/QA/PROD), modo. Botones: `🔌 Test Connection`, `💾 Guardar`, `🔄 Recargar`, `🧹 Reset`. Persiste en `localStorage`.

4. **⚖️ Reglas** — catálogo editable: tabla con código, nombre, severidad, patrón regex, acción, activa. Botón "+ Nueva Regla". 25+ reglas pre-cargadas.

5. **📜 Historial** — tabla de ejecuciones con filtros por usuario y fecha, click en fila abre modal de detalle.

### Backend — modelos y lógica

```python
class XEConfig(BaseModel):
    host: str
    port: str = "1521"
    sid: str                       # XEPDB1
    user: str
    password: str                  # ⚠ campo 'password' (NO 'pass')
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
```

Implementa estas piezas:

- **Resolución de host:** si el backend corre en Docker, traduce `localhost`/`127.0.0.1` enviado por el navegador al hostname interno `oracle-xe` usando `ORACLE_HOST_OVERRIDE`. Sin esto, el backend resolvería `localhost` a sí mismo y nunca llegaría a Oracle.
- **Split de sentencias:** parser propio que respeta bloques PL/SQL (`BEGIN`/`END`) y separadores `/`.
- **DRY RUN:** abre conexión → `SAVEPOINT pre_datafix` → ejecuta sentencia por sentencia capturando `cur.rowcount` → al final hace **siempre** `ROLLBACK TO pre_datafix` en try/finally. Devuelve `{ ok, log, affected_rows, statements, errors, warnings, score }`.
- **Verdict por sentencia:** 🔴 si contiene `DROP|TRUNCATE|ALTER SYSTEM|SHUTDOWN`, 🟡 si `UPDATE/DELETE` sin `WHERE`, 🟢 en cualquier otro caso.

### Docker stack

```yaml
services:
  oracle-xe:
    image: container-registry.oracle.com/database/express:21.3.0-xe
    ports: ["1521:1521", "5500:5500"]
    environment:
      ORACLE_PWD: OraclePwd1
      ORACLE_CHARACTERSET: AL32UTF8
    volumes:
      - oracle-data:/opt/oracle/oradata
      - ./init:/opt/oracle/scripts/startup
    healthcheck:
      test: ["CMD", "sqlplus", "-S", "sys/OraclePwd1@//localhost:1521/XEPDB1", "as", "sysdba"]

  backend:
    build: .
    ports: ["8000:8000"]
    depends_on:
      oracle-xe: { condition: service_healthy }
    environment:
      ORACLE_HOST_OVERRIDE: oracle-xe
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    image: nginx:alpine
    ports: ["8080:80"]
    volumes:
      - ../datafix_oracle.html:/usr/share/nginx/html/index.html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro

volumes:
  oracle-data:
```

`nginx.conf` debe tener `location /` sirviendo el HTML y `location /api/ { proxy_pass http://backend:8000; }`.

`init/01_create_appuser.sql` se ejecuta una vez al levantar Oracle:
```sql
ALTER SESSION SET CONTAINER = XEPDB1;
CREATE USER appuser IDENTIFIED BY app123;
GRANT CONNECT, RESOURCE, UNLIMITED TABLESPACE TO appuser;
```

### Estructura de carpetas

```
1 Datafix Oracle automatico/
├── datafix_oracle.html
└── backend/
    ├── Dockerfile
    ├── docker-compose.yml
    ├── main.py
    ├── nginx.conf
    ├── requirements.txt   # fastapi, uvicorn[standard], oracledb, pydantic, python-multipart
    └── init/
        └── 01_create_appuser.sql
```

### URLs expuestas al levantar

- 🌐 `http://localhost:8080` — sistema web
- 📚 `http://localhost:8080/docs` — Swagger del backend
- 🔌 `http://localhost:8000` — backend directo
- 🗄️ `localhost:1521/XEPDB1` — Oracle XE
- 🌐 `https://localhost:5500/em` — Oracle EM Express (`SYS / OraclePwd1`)

### Datos comerciales (para deck de venta)

| Métrica | Valor |
|---|---|
| Datafix/mes (cliente promedio) | 40 |
| Ciclo HOY | 14-40 h |
| Ciclo con MyCheck | 3.5-7.5 h |
| Reducción ciclo | −75% |
| Reducción impacto en falla | −80% |
| Reducción issues por script | −90% |
| Aumento velocidad despliegue | +60% |
| Ahorro mensual | 860 h |
| Costo hora cargado | CLP 22.000 |
| Ahorro CLP | 18.9 M / mes |
| Suscripción mensual | 4.5 M |
| ROI | 4.2× |
| Payback | < 7 días |

**Tabla etapa por etapa:**

| Etapa | HOY | MyCheck | Ahorro |
|---|---|---|---|
| 1. Solicitud y armado | 2-4 h | 30 min | −75% |
| 2. Chequeo de sintaxis | 1-2 h | <1 min | −99% |
| 3. Auditoría reglas Oracle | 1-3 h | <1 min | −99% |
| 4. Simulación / DRY RUN | 2-6 h | 2-5 min | −95% |
| 5. Revisión y aprobación DBA | 4-12 h | 1-2 h | −80% |
| 6. Ejecución y rollback | 4-12 h | 1-3 h | −70% |

**Casos de uso por industria:**
- **Banco:** Riesgo y Provisiones · Tarjetas de Crédito · Cobranza · Captación / Cuentas
- **Seguros:** Pólizas de Vida · Comisiones de Brokers · Reservas Técnicas IFRS-17 · Siniestros y Pagos

**Roadmap de 8 semanas:** Setup (sem 1-2) → Piloto (sem 3-4, 2 equipos · 30 scripts) → Expansión (sem 5-6, SSO con AD, dashboard) → Producción (sem 7-8, alta disponibilidad + SLA).

### Detalles a no romper

- El campo de password DEBE llamarse `password` en el JSON enviado por el frontend. Mandar `pass` produce HTTP 422 Pydantic.
- `ORACLE_HOST_OVERRIDE=oracle-xe` es obligatorio cuando el backend corre en Docker.
- `SAVEPOINT pre_datafix` + `ROLLBACK TO pre_datafix` debe estar envuelto en try/finally para que ningún error escape sin rollback.
- CORS abierto solo para desarrollo (`allow_origins=["*"]`), acotar en producción.
- `oracle-data` persiste entre `docker compose down`; usa `down -v` para reset total.

### Entregable

Genera todos los archivos listos para `docker compose up -d`:
- `datafix_oracle.html` (frontend completo)
- `backend/main.py` (con los 3 endpoints)
- `backend/Dockerfile`, `docker-compose.yml`, `nginx.conf`, `requirements.txt`
- `backend/init/01_create_appuser.sql`

Al final, instrucciones para levantar el stack y verificar que `http://localhost:8080` responde.

---

## FIN DEL PROMPT
