# FleetWatch Operator Dashboard

This is the standalone dashboard project. It monitors a tenant's robot fleet; it does not contain the ROS inspection pipeline.

## Capabilities

- FastAPI API with registration and JWT login
- tenant-scoped robot inventory, fleet summaries, status, and fault history
- authenticated robot telemetry ingestion
- InfluxDB storage and Flux queries
- built-in HTML operator dashboard
- telemetry simulator for five sample AMRs
- optional Grafana dashboard definition
- CORS, separate ingestion credentials, and environment-based secrets

## Layout

- `app/main.py` — API, authentication, telemetry ingestion, queries, and UI serving
- `Fleetwatch.html` — built-in browser dashboard
- `robot_sim.py` — sample fleet telemetry generator
- `robot_fleet_dashboard.json` — Grafana import
- `.env.example` — required configuration template
- `STARTUP_PROJECT_SUMMARY.md` — original product notes

## Run

Requires Python 3.10+ and InfluxDB 2.x.

```bash
cd /home/samarth/projects/robot-fleet-observability-platform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Replace every placeholder secret and configure the InfluxDB bucket.
set -a; source .env; set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run `python3 robot_sim.py` in a second configured shell, then open `http://localhost:8000/`; API documentation is at `/docs`. Import `robot_fleet_dashboard.json` into Grafana when the optional Grafana view is wanted.

## Scope and provenance

Copied from `/home/samarth/fleet_api` without changing that source folder. Local secrets and generated Python caches were excluded. This is the original lightweight monitoring MVP: it has no inspection-artifact sync, SQLite findings workflow, ROS mission dispatch, or incident-intelligence system; those live in the fusion project.
