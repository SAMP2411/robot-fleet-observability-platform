# Robot Fleet Observability Platform

A multi-tenant monitoring platform for autonomous mobile robot fleets. The system receives live robot telemetry, stores time-series measurements in InfluxDB, exposes tenant-scoped FastAPI endpoints, and presents fleet health, battery, task, uptime, position, and fault information in an operator dashboard.

## Objective and motivation

Warehouse and factory operators need a fast way to answer fleet-wide questions: Which robots are online? Which unit is faulted? Is battery health deteriorating? How much work has the fleet completed? Robot deployments often begin with device-level logs and vendor-specific tools that are useful to engineers but difficult for operations teams to use. This project demonstrates the service boundary between robots and operators: protected ingestion, durable time-series storage, fleet aggregation, fault history, browser visualization, and optional Grafana integration.

## Key capabilities

- Multi-tenant account registration and JWT authentication
- Separate API-key authentication for telemetry producers
- InfluxDB-backed status, battery, odometry, task, uptime, and fault measurements
- Tenant and robot filtering in every fleet query
- Fleet KPIs: online/offline counts, average battery, completed tasks, active faults, and uptime
- Per-robot latest metrics and 24-hour fault history
- Responsive browser dashboard served by FastAPI
- Five-robot AMR telemetry simulator
- Importable Grafana dashboard definition
- Environment-based CORS and secret configuration
- OpenAPI documentation and database-aware health reporting

## Architecture

```text
AMRs / telemetry simulator
          |
          | status, battery, odometry, tasks
          v
 FastAPI ingestion endpoint ---- API key + tenant identity
          |
          v
      InfluxDB 2.x
          |
          | tenant-scoped Flux queries
          v
 FastAPI fleet API ---- JWT authentication
          |
          +---- Built-in operator dashboard
          +---- OpenAPI clients
          +---- Optional Grafana dashboard
```

## Technology stack

- Python 3.10+
- FastAPI, Uvicorn, and Pydantic
- InfluxDB 2.x and Flux
- JSON Web Tokens with `python-jose`
- Passlib/bcrypt password hashing
- HTML, CSS, and browser JavaScript
- Grafana dashboard JSON

## Repository structure

```text
.
├── app/
│   └── main.py                  # API, authentication, ingestion, queries, UI serving
├── Fleetwatch.html              # Operator dashboard
├── robot_sim.py                 # Five-AMR telemetry simulator
├── robot_fleet_dashboard.json   # Optional Grafana dashboard
├── requirements.txt             # Python runtime dependencies
└── .env.example                 # Configuration template
```

## Prerequisites

- Git
- Python 3.10 or newer
- InfluxDB 2.x, installed locally or run with Docker
- Optional: Grafana for the separate dashboard definition

## Complete local setup

### 1. Clone the project

```bash
git clone https://github.com/SAMP2411/robot-fleet-observability-platform.git
cd robot-fleet-observability-platform
```

### 2. Start InfluxDB

The following creates a disposable local InfluxDB instance. Replace all sample credentials before using the system outside a local machine.

```bash
docker run -d \
  --name robot-fleet-influxdb \
  -p 8086:8086 \
  -e DOCKER_INFLUXDB_INIT_MODE=setup \
  -e DOCKER_INFLUXDB_INIT_USERNAME=admin \
  -e DOCKER_INFLUXDB_INIT_PASSWORD='local-development-password' \
  -e DOCKER_INFLUXDB_INIT_ORG=startup-robot-dashboard \
  -e DOCKER_INFLUXDB_INIT_BUCKET=robot_fleet \
  -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN='local-development-influx-token' \
  influxdb:2.7
```

InfluxDB will be available at <http://localhost:8086>.

### 3. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure the service

```bash
cp .env.example .env
```

Edit `.env` so `INFLUX_TOKEN` matches the token used above. Generate independent application secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use the first value for `SECRET_KEY` and the second for `INGEST_API_KEY`. The demo login is created only when both `DEMO_EMAIL` and `DEMO_PASSWORD` are set. `TENANT_ID` must match `DEMO_TENANT_ID` when the bundled simulator is used.

Load the configuration:

```bash
set -a
source .env
set +a
```

### 5. Start the API and dashboard

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

- Operator dashboard: <http://localhost:8000/>
- Interactive API documentation: <http://localhost:8000/docs>
- Health endpoint: <http://localhost:8000/health>

### 6. Start simulated telemetry

Open a second terminal:

```bash
cd robot-fleet-observability-platform
source .venv/bin/activate
set -a
source .env
set +a
python robot_sim.py
```

The simulator continuously publishes five robots, `AMR-01` through `AMR-05`. Battery, position, speed, operating status, completed tasks, uptime, and occasional faults evolve over time.

## API reference

| Method | Endpoint | Purpose | Authentication |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Create a tenant account and fleet mapping | None |
| `POST` | `/auth/token` | Exchange credentials for a bearer token | Form credentials |
| `GET` | `/fleet/robots` | List robots assigned to the tenant | Bearer token |
| `GET` | `/fleet/robots/{robot_id}` | Return the robot's latest measurements | Bearer token |
| `GET` | `/fleet/summary` | Return fleet-wide KPIs | Bearer token |
| `GET` | `/fleet/faults` | Return recent fault events | Bearer token |
| `POST` | `/ingest/{robot_id}` | Write a telemetry sample | Ingestion key and tenant headers |
| `GET` | `/health` | Report API and InfluxDB health | None |

Telemetry ingestion requires `X-API-Key` and `X-Tenant-ID` headers. The request body contains `battery`, `status`, `x`, `y`, `speed`, `tasks_done`, optional `fault_code`, and optional `uptime_s`.

## End-to-end test procedure

Run these checks after the API, InfluxDB, and simulator are active.

### Check service health

```bash
curl -fsS http://localhost:8000/health
```

The API should report `status: ok` and `database: pass`. A `degraded` result means the API is running but cannot reach InfluxDB.

### Authenticate

```bash
TOKEN=$(curl -fsS -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "username=$DEMO_EMAIL" \
  --data-urlencode "password=$DEMO_PASSWORD" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
test -n "$TOKEN"
```

### Verify fleet queries

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" http://localhost:8000/fleet/robots
curl -fsS -H "Authorization: Bearer $TOKEN" http://localhost:8000/fleet/summary
curl -fsS -H "Authorization: Bearer $TOKEN" http://localhost:8000/fleet/robots/AMR-01
curl -fsS -H "Authorization: Bearer $TOKEN" 'http://localhost:8000/fleet/faults?limit=20'
```

Five robots should be listed. Recent measurements should appear after the simulator has run for several seconds. A request without the bearer token should return HTTP 401.

### Verify direct ingestion

```bash
curl -fsS -X POST http://localhost:8000/ingest/AMR-01 \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $INGEST_API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{"battery":87.5,"status":"moving","x":12.4,"y":8.1,"speed":1.1,"tasks_done":42,"uptime_s":3600}'
```

The endpoint should return HTTP 200 with `status: ok`. The robot and summary endpoints should subsequently reflect the sample.

### Verify the browser dashboard

Open <http://localhost:8000/>, sign in with the configured demo account, and confirm the fleet cards and summary values populate without browser console errors.

## Optional Grafana view

Start Grafana, configure an InfluxDB data source with the same organization, bucket, and token, then import `robot_fleet_dashboard.json`. The built-in FastAPI dashboard is the main UI; Grafana provides an additional operations view.

## Configuration reference

| Variable | Purpose |
| --- | --- |
| `INFLUX_URL` | InfluxDB base URL |
| `INFLUX_TOKEN` | InfluxDB API token |
| `INFLUX_ORG` | InfluxDB organization |
| `INFLUX_BUCKET` | Telemetry bucket |
| `SECRET_KEY` | JWT signing secret |
| `INGEST_API_KEY` | Shared key accepted by the ingestion endpoint |
| `CORS_ORIGINS` | Comma-separated browser origins |
| `DEMO_EMAIL` | Optional local demo account email |
| `DEMO_PASSWORD` | Optional local demo account password |
| `DEMO_COMPANY` | Demo tenant display name |
| `DEMO_TENANT_ID` | Demo account tenant identifier |
| `TENANT_ID` | Tenant tag written by `robot_sim.py` |

## Security and production considerations

- Replace all sample credentials and keep `.env` out of version control.
- Use HTTPS and a secret manager in deployed environments.
- Give telemetry producers separate, revocable credentials instead of sharing one fleet-wide key.
- Replace the in-memory user and tenant mappings with persistent storage before production use.
- Restrict InfluxDB tokens to the minimum bucket permissions required.
- Run the API behind a production process manager or container platform.
- Add rate limiting, audit events, token rotation, invitation-based tenant membership, and automated backups for production.

## Troubleshooting

- Health reports `degraded`: verify the InfluxDB container, URL, organization, bucket, and token.
- Login fails: confirm the demo variables were exported before Uvicorn started; the demo user is initialized at process startup.
- No measurements appear: confirm `TENANT_ID` equals `DEMO_TENANT_ID` and the simulator is running.
- Ingestion returns 401: `X-API-Key` must exactly match `INGEST_API_KEY`.
- Ingestion returns 400: tenant IDs must match `tenant_[a-z0-9_]+`.
- A fleet endpoint returns 401: request a new token; tokens expire after one day.

## Current boundaries

This repository focuses on fleet observability. It does not perform robot navigation, mission dispatch, or autonomous inspections. User and tenant registration is held in process memory, so accounts are recreated after a restart unless the optional demo account is configured. Telemetry remains durable in InfluxDB.
