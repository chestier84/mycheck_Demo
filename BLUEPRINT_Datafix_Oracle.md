# Blueprint — Datafix Oracle Automático

Documento completo para reconstruir el sistema en otra IA. Copia este archivo entero como prompt o repártelo por secciones.

---

## 1. Qué es

Sistema web que valida, audita y simula scripts SQL/PLSQL contra Oracle XE **antes** de tocar producción. Reemplaza el "checklist mental" del DBA por reglas codificadas + DRY RUN real con SAVEPOINT/ROLLBACK + reporte de Score (max 100).

**Stack:** HTML+TailwindCSS (frontend) → Nginx (reverse proxy) → FastAPI + python-oracledb (backend) → Oracle XE 21c (DB) — todo en Docker.

**Cuatro capacidades exigidas por el cliente:**

1. Validar sintaxis SQL/PLSQL
2. Validador de reglas de auditoría Oracle (alerta comandos críticos)
3. Botón de simulación tipo Liquibase **DRY RUN**
4. Botón **Exportar Reporte** con puntaje máx. 100

---

## 2. Jerarquía de carpetas

```
1 Datafix Oracle automatico/
├── Prompt_Datafix_Oracle.md           ← prompt original del cliente
├── datafix_oracle.html                 ← FRONTEND completo (single-file, ~670 líneas)
├── Datafix_MetLife_Slides.html         ← deck visual-explainer (16 slides Editorial)
├── BLUEPRINT_Datafix_Oracle.md         ← este archivo
│
├── backend/
│   ├── Dockerfile                      ← imagen FastAPI + oracledb
│   ├── docker-compose.yml              ← stack: oracle-xe + backend + nginx
│   ├── main.py                         ← API FastAPI (~340 líneas)
│   ├── nginx.conf                      ← reverse proxy / + /api/
│   ├── requirements.txt                ← fastapi, uvicorn, oracledb, pydantic
│   ├── README.md                       ← instrucciones de despliegue
│   └── init/
│       └── 01_create_appuser.sql       ← crea usuario APPUSER al levantar Oracle XE
│
├── presentacion/                       ← assets antiguos (puede ignorarse)
├── CLIENTE FALABELLA/                  ← outputs PPT versión Falabella
│   └── Datafix_Falabella.pptx
└── METLIFE/                            ← outputs PPT versión MetLife
    └── Datafix_MetLife.pptx
```

---

## 3. La página web — pestañas y secciones

`datafix_oracle.html` es un **single-page app** con TailwindCSS por CDN y JavaScript vanilla. Tiene login + 5 pestañas principales.

### Flujo de entrada

1. **Modal de login** (fullscreen overlay)
   - Inputs: usuario, contraseña
   - Usuario demo hardcoded: `admin` / `admin123`
   - Al loguear, esconde el modal y muestra la app

2. **Header fijo** (top)
   - Logo "Datafix Oracle Automático"
   - Saludo "Hola, {username}"
   - Botón "Salir" (logout)

3. **Tab navigation** (debajo del header)
   - 5 botones: Editor SQL · Mantenedor · Oracle XE · Reglas · Historial

### Pestaña 1 — `📝 Editor SQL` (default activa)

La pestaña principal donde el DBA trabaja.

**Layout: 2 columnas**

**Columna izquierda — Editor**
- `<textarea>` grande con código SQL (font monospace, syntax-friendly)
- Botones encima del editor: 🧹 Limpiar, 📂 Cargar, 💾 Guardar
- Botones de acción debajo (cinco):
  - 🔍 **Validar Sintaxis** → llama a parser local (regex) → muestra errores línea por línea
  - ⚖️ **Auditoría** → corre las reglas Oracle → lista hallazgos por severidad
  - 🧪 **DRY RUN** → POST `/api/dryrun` → ejecuta en Oracle XE con SAVEPOINT y ROLLBACK
  - 🚀 **Ejecutar Todo** → encadena las 3 acciones
  - 📄 **Exportar Reporte** → genera PDF con score, hallazgos, log, recomendación

**Columna derecha — Resultados (sub-tabs)**
- Sub-pestaña **Sintaxis** — lista de errores con número de línea y sugerencia
- Sub-pestaña **Auditoría** — tabla de hallazgos: regla / severidad (🔴 CRITICO 🟡 ALTO ⚪ MEDIO) / línea / acción
- Sub-pestaña **DRY RUN** — log estilo terminal con timestamps `[hh:mm:ss] INFO|CONN|EXEC|ROLL`
- Sub-pestaña **Puntaje** — gauge SVG con score numérico, fórmula y desglose

### Pestaña 2 — `👥 Mantenedor`

Mantenedor de seguridad con 5 sub-pestañas:

- **👤 Usuarios** — tabla CRUD: username, email, AD group, rol, estado, fecha creación. Botón "+ Nuevo Usuario" abre modal.
- **🏢 Grupos AD** — tabla: nombre grupo, OU, miembros, rol mapeado. Botón "⬇️ Importar desde AD".
- **🎭 Roles** — tabla: rol, permisos asociados, usuarios asignados.
- **🔑 Permisos** — matriz de permisos: validar / auditar / dry-run / exportar / config / mantener.
- **📋 Auditoría** — log inmutable: usuario, acción, timestamp, IP, recurso. Botón "Exportar CSV".

### Pestaña 3 — `🗄️ Oracle XE`

Configuración de la conexión a la base de datos.

**Form (2 columnas):**
- Host (default `oracle-xe` o `localhost`)
- Port (default `1521`)
- SID / Service name (default `XEPDB1`)
- Usuario (default `appuser`)
- Password (default `app123`)
- Wallet path (opcional)
- Timeout (segundos, default 30)
- Max rows (default 10000)
- Whitelist de esquemas (CSV, ej. `HR,APP_USER`)
- Ambiente (DEV / QA / PROD)
- Modo de ejecución (`SAVEPOINT + ROLLBACK automático` por defecto)

**Botones:**
- 🔌 **Test Connection** → POST `/api/test-connection` → muestra versión de Oracle, DB name, usuario conectado
- 💾 **Guardar** → persiste en `localStorage`
- 🔄 **Recargar** → relee del localStorage
- 🧹 **Reset** → vuelve a defaults

### Pestaña 4 — `⚖️ Reglas`

Catálogo editable de reglas de auditoría Oracle.

- Tabla con columnas: Código, Nombre, Severidad, Patrón regex, Acción (Bloquear / Alertar / Sugerir), Activa.
- Botón "+ Nueva Regla".
- 25+ reglas pre-cargadas:
  - `UPDATE sin WHERE` — CRITICO — Bloquear
  - `DELETE sin WHERE` — CRITICO — Bloquear
  - `TRUNCATE TABLE` — CRITICO — Bloquear
  - `DROP / ALTER en core` — CRITICO — Bloquear
  - `GRANT a usuario directo` — ALTO — Alertar
  - `Sin COMMIT explícito` — ALTO — Alertar
  - `Lock > 100k filas` — ALTO — Alertar
  - `Sin SAVEPOINT` — MEDIO — Sugerir
  - `Tipos de dato implícitos` — MEDIO — Sugerir
  - … (resto en JSON dentro del HTML)

### Pestaña 5 — `📜 Historial`

Tabla de ejecuciones históricas: fecha, usuario, archivo, acción, score, resultado. Filtros por usuario y fecha. Click en fila → modal con detalle completo del log.

### Modales globales

- Modal usuario (alta/edición)
- Modal regla (alta/edición)
- Modal detalle ejecución
- Modal confirmación de DRY RUN antes de ejecutar

---

## 4. Backend — FastAPI

`backend/main.py` (~340 líneas).

### Endpoints

| Método | Ruta | Función |
|---|---|---|
| `GET`  | `/api/health`           | health check + versión driver oracledb |
| `POST` | `/api/test-connection`  | abre conexión, retorna versión Oracle, DB name, user |
| `POST` | `/api/dryrun`           | ejecuta script en SAVEPOINT y ROLLBACK garantizado |

### Modelos Pydantic

```python
class XEConfig(BaseModel):
    host: str
    port: str = "1521"
    sid: str                    # XEPDB1
    user: str
    password: str               # ⚠ El frontend debe mandar 'password', no 'pass'
    wallet: Optional[str] = None
    timeout: int = 30
    maxRows: int = 10000
    whitelist: Optional[str] = ""
    env: Optional[str] = "DEV"
    mode: Optional[str] = "SAVEPOINT + ROLLBACK automático"

class TestConnReq(BaseModel):
    config: XEConfig

class DryRunReq(BaseModel):
    sql: str
    config: XEConfig
    username: Optional[str] = "anonymous"
```

### Lógica clave

- **Resolución de host:** si el backend corre en Docker, traduce `localhost`/`127.0.0.1` enviado por el navegador a `oracle-xe` (DNS interno de docker-compose) usando `ORACLE_HOST_OVERRIDE`.
- **Split de sentencias:** parser propio que respeta bloques PLSQL (`BEGIN`/`END`) y separadores `/`.
- **DRY RUN:** abre conexión → `SAVEPOINT pre_datafix` → ejecuta sentencia por sentencia capturando `cur.rowcount` → al final hace **siempre** `ROLLBACK TO pre_datafix`. Devuelve `{ ok, log:[], affected_rows, statements, errors, warnings, score }`.
- **Verdict por sentencia:** 🔴 si contiene `DROP|TRUNCATE|ALTER SYSTEM|SHUTDOWN`, 🟡 si `UPDATE/DELETE` sin `WHERE`, 🟢 en otro caso.
- **CORS abierto** (`allow_origins=["*"]`) — en producción se debe acotar.

### Fórmula de score

```
SCORE = 100 − 25 × CRITICO − 10 × ALTO − 3 × MEDIO
```

Tope inferior 0. Score ≥ 90 ⇒ auto-aprobación. 70-89 ⇒ aprobado con observaciones. <70 ⇒ rechazado.

---

## 5. Docker stack

### `backend/docker-compose.yml`

Tres servicios en una red interna:

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
    healthcheck: sqlplus check cada 30s

  backend:
    build: .
    ports: ["8000:8000"]
    depends_on: [oracle-xe]
    environment:
      ORACLE_HOST_OVERRIDE: oracle-xe
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    image: nginx:alpine
    ports: ["8080:80"]
    volumes:
      - ../datafix_oracle.html:/usr/share/nginx/html/index.html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

### `backend/nginx.conf`

```nginx
server {
  listen 80;
  location / {
    root /usr/share/nginx/html;
    index index.html;
  }
  location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }
}
```

Esto resuelve CORS porque frontend y `/api/*` viajan por el **mismo origen** `http://localhost:8080`.

### `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `backend/requirements.txt`

```
fastapi>=0.100
uvicorn[standard]
oracledb>=2.0
pydantic>=2
python-multipart
```

### `backend/init/01_create_appuser.sql`

Se ejecuta una sola vez al inicializar Oracle XE. Crea el usuario de aplicación:

```sql
ALTER SESSION SET CONTAINER = XEPDB1;
CREATE USER appuser IDENTIFIED BY app123;
GRANT CONNECT, RESOURCE TO appuser;
GRANT UNLIMITED TABLESPACE TO appuser;
```

### Comandos de despliegue

```bash
cd backend
docker compose up -d
# espera ~3-5 min a que Oracle XE quede HEALTHY
docker compose ps
# abre http://localhost:8080
```

URLs expuestas:
- 🌐 `http://localhost:8080` — sistema web
- 📚 `http://localhost:8080/docs` — Swagger del backend
- 🔌 `http://localhost:8000` — backend directo
- 🗄️ `localhost:1521/XEPDB1` — Oracle XE
- 🌐 `https://localhost:5500/em` — Oracle EM Express (`SYS / OraclePwd1`)

---

## 6. Identidad visual

### Frontend (HTML)

- **Framework:** TailwindCSS por CDN
- **Paleta:** rojo corporativo `#DC2626` (Falabella) o navy `#1A2438` (MetLife) en botones primarios; slate-900 para fondos oscuros, blanco para cards.
- **Tipografía:** sans-serif del sistema + monospace `Consolas/Menlo` para el editor.
- **Iconos:** emojis (sin librería externa) — minimiza dependencias.

### Presentación HTML (Datafix_MetLife_Slides.html)

Estilo Editorial:
- Paleta: `#F4EEE2` cream paper / `#1A2438` navy / `#B8893E` gold cálido
- Fonts: Instrument Serif (titulares cursiva) + Manrope (body) + JetBrains Mono (code)
- Scroll-snap mandatory, dots de navegación, ↑↓ keyboard nav
- 16 láminas con alternancia cream/navy/gold para ritmo editorial
- Soporte light/dark mode automático via `prefers-color-scheme`

### PPTX (versiones Falabella y MetLife)

- **Falabella:** verde corporativo `#00A651` + dorado `#FDB913`, Cambria + Calibri, 13.33×7.5"
- **MetLife:** navy `#051C2B` + cyan `#129EED` + gold `#FDB913`, Calibri Light, 10×5.625"

---

## 7. Datos comerciales (para slides de venta)

| Métrica | Valor |
|---|---|
| Datafix por mes (cliente promedio) | 40 |
| Horas/script HOY (Dev + DBA + Implementador) | 27 h |
| Horas/script con MyCheck | 5.5 h |
| Ahorro mensual | 860 h |
| Costo hora cargado | CLP 22.000 |
| Ahorro CLP | 18.9 M / mes |
| Suscripción mensual | 4.5 M |
| ROI | 4.2× |
| Payback | < 7 días |
| Ciclo total HOY | 14 – 40 h |
| Ciclo con MyCheck | 3.5 – 7.5 h |
| Reducción ciclo | −75% |
| Reducción impacto en falla | −80% |
| Reducción issues por script | −90% |
| Aumento velocidad despliegue | +60% |

### Tabla comparativa etapa por etapa

| Etapa | HOY | MyCheck | Ahorro |
|---|---|---|---|
| 1. Solicitud y armado | 2-4 h | 30 min | −75% |
| 2. Chequeo de sintaxis | 1-2 h | <1 min | −99% |
| 3. Auditoría reglas Oracle | 1-3 h | <1 min | −99% |
| 4. Simulación / DRY RUN | 2-6 h | 2-5 min | −95% |
| 5. Revisión y aprobación DBA | 4-12 h | 1-2 h | −80% |
| 6. Ejecución y rollback | 4-12 h | 1-3 h | −70% |

### Casos de uso por industria

**Banco (Falabella):** Riesgo y Provisiones · Tarjetas de Crédito · Cobranza · Captación / Cuentas

**Seguros (MetLife):** Pólizas de Vida · Comisiones de Brokers · Reservas Técnicas IFRS-17 · Siniestros y Pagos

### Roadmap de implementación (8 semanas)

| Fase | Semanas | Acciones |
|---|---|---|
| Setup | 1-2 | Despliegue contenedor en DEV. Conexión Oracle XE pruebas. Carga reglas cliente. |
| Piloto | 3-4 | 2 equipos · 30 scripts reales. Métricas vs proceso actual. Tuning de reglas. |
| Expansión | 5-6 | 3 equipos adicionales. SSO con AD. Dashboard ejecutivo. |
| Producción | 7-8 | Despliegue producción · alta disponibilidad · soporte SLA · capacitación. |

---

## 8. Cómo reconstruirlo en otra IA — prompt sugerido

> Construye un sistema web que valide, audite y simule scripts SQL/PLSQL contra Oracle XE antes de tocar producción. Usa este blueprint:
>
> 1. **Frontend** — un solo archivo `datafix_oracle.html` con TailwindCSS por CDN y JS vanilla. Login modal (admin/admin123 hardcoded), 5 pestañas: Editor SQL, Mantenedor (usuarios/grupos AD/roles/permisos/auditoría), Oracle XE config, Reglas, Historial. La pestaña Editor SQL tiene editor `<textarea>`, 5 botones de acción (Validar Sintaxis · Auditoría · DRY RUN · Ejecutar Todo · Exportar Reporte), y panel de resultados con sub-pestañas (Sintaxis · Auditoría · DRY RUN · Puntaje).
>
> 2. **Backend** — FastAPI con 3 endpoints: `GET /api/health`, `POST /api/test-connection`, `POST /api/dryrun`. Modelos Pydantic `XEConfig` (campo `password`, NO `pass`), `TestConnReq`, `DryRunReq`. Conexión a Oracle XE con `python-oracledb`. DRY RUN ejecuta dentro de SAVEPOINT y hace ROLLBACK SIEMPRE.
>
> 3. **Docker** — `docker-compose.yml` con 3 servicios: `oracle-xe` (imagen oficial Oracle Database Express 21.3.0-xe, password `OraclePwd1`), `backend` (build local, env `ORACLE_HOST_OVERRIDE=oracle-xe`), `frontend` (nginx:alpine montando el HTML y el `nginx.conf`). El nginx hace reverse proxy: `/` sirve el HTML, `/api/` proxypass a `backend:8000` (resuelve CORS por mismo origen).
>
> 4. **Reglas Oracle** — 25+ reglas pre-cargadas con tres severidades: CRITICO (UPDATE/DELETE sin WHERE, TRUNCATE, DROP, ALTER SYSTEM) → Bloquear; ALTO (GRANT directo, sin COMMIT, lock >100k filas) → Alertar; MEDIO (sin SAVEPOINT, tipos implícitos) → Sugerir.
>
> 5. **Score** — `100 − 25×CRITICO − 10×ALTO − 3×MEDIO`. ≥90 auto-aprobación. 70-89 con observaciones. <70 rechazado. Botón Exportar Reporte genera PDF.
>
> 6. **Init script** — `init/01_create_appuser.sql` crea usuario `appuser/app123` en `XEPDB1` al levantar Oracle.
>
> Estructura de carpetas: `1 Datafix Oracle automatico/{datafix_oracle.html, backend/{Dockerfile, docker-compose.yml, main.py, nginx.conf, requirements.txt, init/01_create_appuser.sql}}`.
>
> Datos comerciales para slides de venta: 40 datafix/mes, ciclo 14-40h → 3.5-7.5h (-75%), ahorro 860 h/mes = CLP 18.9M, ROI 4.2×, payback <7 días, reducción impacto en falla -80%, issues por script -90%.

---

## 9. Defectos conocidos / cosas a no romper

- **`password` vs `pass`** — el frontend DEBE serializar el campo como `password` en la llamada a `/api/dryrun`. Mandar `pass` produce HTTP 422 Pydantic. Esto fue un bug histórico.
- **Resolución de host en Docker** — si quitas `ORACLE_HOST_OVERRIDE`, el backend dentro del contenedor intenta resolver `localhost` y apunta a sí mismo, no a Oracle. No tocar `resolve_host()` sin entender este detalle.
- **CORS** — está abierto (`*`). En producción acotar a los dominios del cliente.
- **Login hardcoded** — `admin/admin123` solo es demo. La pestaña Mantenedor presupone integración real con AD que aún no está.
- **DRY RUN garantiza ROLLBACK** — el `SAVEPOINT pre_datafix` + `ROLLBACK TO pre_datafix` está envuelto en try/finally para que ningún error escape sin rollback.
- **Volumen Docker `oracle-data`** — persiste entre `docker compose down`. Si quieres reset total: `docker compose down -v`.

---

## 10. Outputs ya generados en este proyecto

- `datafix_oracle.html` — frontend funcional (670 líneas)
- `backend/main.py` — backend FastAPI (340 líneas)
- `backend/docker-compose.yml` + `Dockerfile` + `nginx.conf` + `init/01_create_appuser.sql`
- `Datafix_MetLife_Slides.html` — deck visual-explainer 16 slides Editorial
- `CLIENTE FALABELLA/Datafix_Falabella.pptx` — deck PPT verde Falabella, 16 slides
- `METLIFE/Datafix_MetLife.pptx` — deck PPT navy/cyan estilo Vermont, 19 slides
