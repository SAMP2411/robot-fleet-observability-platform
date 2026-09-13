"""
Robot Fleet Observability — FastAPI Backend
Multi-tenant SaaS layer on top of InfluxDB.

Endpoints:
  POST /auth/register        — create tenant account
  POST /auth/token           — login, get JWT
  GET  /fleet/robots         — list robots for this tenant
  GET  /fleet/robots/{id}    — single robot status + last metrics
  GET  /fleet/summary        — fleet-wide KPIs
  GET  /fleet/faults         — fault log for this tenant
  POST /ingest/{robot_id}    — robot pushes telemetry (used by the sim)

Run with:
  cd ~/fleet_api
  uvicorn app.main:app --reload --port 8000
"""

from datetime import datetime, timezone, timedelta
from typing import Literal, Optional
import os
import json
import re
import secrets
from pathlib import Path

from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from jose import JWTError, jwt
from passlib.context import CryptContext
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ── CONFIG ────────────────────────────────────────────────────────────────────
INFLUX_URL    = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG    = os.getenv("INFLUX_ORG",   "startup-robot-dashboard")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "robot_fleet")
INGEST_API_KEY = os.getenv("INGEST_API_KEY", "")
DEMO_EMAIL      = os.getenv("DEMO_EMAIL", "")
DEMO_PASSWORD   = os.getenv("DEMO_PASSWORD", "")
DEMO_COMPANY    = os.getenv("DEMO_COMPANY", "FleetWatch")
DEMO_TENANT_ID  = os.getenv("DEMO_TENANT_ID", "tenant_fleetwatch")

SECRET_KEY    = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
ALGORITHM     = "HS256"
TOKEN_EXPIRE  = 60 * 24  # minutes — 1 day
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Fleet Observability API",
    description="Multi-tenant robot fleet monitoring SaaS",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx.write_api(write_options=SYNCHRONOUS)
query_api  = influx.query_api()

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ── In-memory "database" (swap for PostgreSQL in production) ──────────────────
# Structure: { email: { hashed_password, tenant_id, company } }
USERS: dict = {}

# Tenant → robot mapping  { tenant_id: [robot_id, ...] }
TENANT_ROBOTS: dict = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:     str
    password:  str
    company:   str
    robots:    list[str] = Field(default_factory=lambda: ["AMR-01", "AMR-02", "AMR-03", "AMR-04", "AMR-05"])

class Token(BaseModel):
    access_token: str
    token_type:   str

class RobotTelemetry(BaseModel):
    battery:    float
    status:     Literal["idle", "moving", "charging", "fault"]
    x:          float
    y:          float
    speed:      float
    tasks_done: int
    fault_code: Optional[str] = None
    uptime_s: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_fault(self):
        if self.status == "fault" and not self.fault_code:
            raise ValueError("fault_code is required when status is fault")
        if self.status != "fault" and self.fault_code:
            raise ValueError("fault_code is only valid when status is fault")
        return self


# ── Auth helpers ──────────────────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def flux_string(value: str) -> str:
    """Encode user-controlled values safely as Flux string literals."""
    return json.dumps(value)

def bootstrap_demo_user() -> None:
    """Create an explicit local demo account when configured by the operator."""
    if not DEMO_EMAIL or not DEMO_PASSWORD:
        return
    USERS[DEMO_EMAIL] = {
        "email": DEMO_EMAIL,
        "hashed_password": hash_password(DEMO_PASSWORD),
        "tenant_id": DEMO_TENANT_ID,
        "company": DEMO_COMPANY,
    }
    TENANT_ROBOTS.setdefault(
        DEMO_TENANT_ID, ["AMR-01", "AMR-02", "AMR-03", "AMR-04", "AMR-05"]
    )

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None or email not in USERS:
            raise credentials_exception
        return USERS[email]
    except JWTError:
        raise credentials_exception


bootstrap_demo_user()


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/auth/register", tags=["auth"])
def register(req: RegisterRequest):
    if req.email in USERS:
        raise HTTPException(status_code=400, detail="Email already registered")
    company_slug = re.sub(r"[^a-z0-9]+", "_", req.company.lower()).strip("_")
    if not company_slug:
        raise HTTPException(status_code=400, detail="Company must contain letters or numbers")
    # New organizations receive unique tenant IDs. Joining an existing tenant
    # should be implemented later through an authenticated invitation flow.
    tenant_id = f"tenant_{company_slug}_{secrets.token_hex(4)}"
    USERS[req.email] = {
        "email":           req.email,
        "hashed_password": hash_password(req.password),
        "tenant_id":       tenant_id,
        "company":         req.company,
    }
    TENANT_ROBOTS[tenant_id] = list(dict.fromkeys(req.robots))
    return {"message": "Account created", "tenant_id": tenant_id}


@app.post("/auth/token", response_model=Token, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = USERS.get(form.username)
    if not user or not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_token({"sub": user["email"]})
    return {"access_token": token, "token_type": "bearer"}


# ── Fleet routes ──────────────────────────────────────────────────────────────

@app.get("/fleet/robots", tags=["fleet"])
def list_robots(user: dict = Depends(get_current_user)):
    robots = TENANT_ROBOTS.get(user["tenant_id"], [])
    return {"tenant": user["company"], "robots": robots, "count": len(robots)}


@app.get("/fleet/robots/{robot_id}", tags=["fleet"])
def get_robot(robot_id: str, user: dict = Depends(get_current_user)):
    robots = TENANT_ROBOTS.get(user["tenant_id"], [])
    if robot_id not in robots:
        raise HTTPException(status_code=404, detail="Robot not in your fleet")

    tenant_id = flux_string(user["tenant_id"])
    safe_robot_id = flux_string(robot_id)
    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -5m)
  |> filter(fn: (r) => r.tenant_id == {tenant_id} and r.robot_id == {safe_robot_id})
  |> last()
"""
    tables = query_api.query(flux, org=INFLUX_ORG)

    result = {"robot_id": robot_id, "metrics": {}}
    for table in tables:
        for record in table.records:
            result["metrics"][f"{record.get_measurement()}.{record.get_field()}"] = record.get_value()

    return result


@app.get("/fleet/summary", tags=["fleet"])
def fleet_summary(user: dict = Depends(get_current_user)):
    robots = TENANT_ROBOTS.get(user["tenant_id"], [])
    robot_filter = " or ".join([f"r.robot_id == {flux_string(r)}" for r in robots]) or "false"
    tenant_filter = f"r.tenant_id == {flux_string(user['tenant_id'])}"

    battery_flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "battery" and r._field == "soc_pct")
  |> filter(fn: (r) => {tenant_filter})
  |> filter(fn: (r) => {robot_filter})
  |> last()
  |> group()
  |> mean()
"""
    tasks_flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "tasks" and r._field == "completed_total")
  |> filter(fn: (r) => {tenant_filter})
  |> filter(fn: (r) => {robot_filter})
  |> last()
  |> group()
  |> sum()
"""
    fault_flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "robot_status" and r._field == "fault_code")
  |> filter(fn: (r) => {tenant_filter})
  |> filter(fn: (r) => {robot_filter})
  |> last()
  |> filter(fn: (r) => r._value != "none")
  |> group()
  |> count()
"""
    online_flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "robot_status" and r._field == "status")
  |> filter(fn: (r) => {tenant_filter})
  |> filter(fn: (r) => {robot_filter})
  |> last()
  |> group()
  |> count()
"""

    def first_value(flux_query, default=0):
        try:
            tables = query_api.query(flux_query, org=INFLUX_ORG)
            for table in tables:
                for record in table.records:
                    return record.get_value()
        except Exception:
            pass
        return default

    avg_battery   = first_value(battery_flux, default=0.0)
    total_tasks   = first_value(tasks_flux,   default=0)
    active_faults = first_value(fault_flux,   default=0)
    online_robots = first_value(online_flux, default=0)
    online_count = min(len(robots), int(online_robots) if online_robots else 0)
    fault_count = min(online_count, int(active_faults) if active_faults else 0)

    return {
        "tenant":         user["company"],
        "robot_count":    len(robots),
        "online_robots":  online_count,
        "offline_robots": len(robots) - online_count,
        "avg_battery_pct": round(float(avg_battery), 1) if avg_battery else 0.0,
        "total_tasks":    int(total_tasks) if total_tasks else 0,
        "active_faults":  fault_count,
        "fleet_uptime_pct": round((online_count - fault_count) / len(robots) * 100, 1) if robots else 0,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }


@app.get("/fleet/faults", tags=["fleet"])
def fault_log(limit: int = 20, user: dict = Depends(get_current_user)):
    robots = TENANT_ROBOTS.get(user["tenant_id"], [])
    robot_filter = " or ".join([f"r.robot_id == {flux_string(r)}" for r in robots]) or "false"
    tenant_filter = f"r.tenant_id == {flux_string(user['tenant_id'])}"

    flux = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "robot_status" and r._field == "fault_code")
  |> filter(fn: (r) => {tenant_filter})
  |> filter(fn: (r) => {robot_filter})
  |> filter(fn: (r) => r._value != "none")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    tables = query_api.query(flux, org=INFLUX_ORG)
    faults = []
    for table in tables:
        for record in table.records:
            faults.append({
                "robot_id":   record.values.get("robot_id"),
                "fault_code": record.get_value(),
                "timestamp":  record.get_time().isoformat(),
            })
    return {"faults": faults, "count": len(faults)}


# ── Ingest route (called by robot agent / simulator) ─────────────────────────

@app.post("/ingest/{robot_id}", tags=["ingest"])
def ingest(
    robot_id: str,
    telemetry: RobotTelemetry,
    x_api_key: str = Header(default="", alias="X-API-Key"),
    x_tenant_id: str = Header(default="", alias="X-Tenant-ID"),
):
    if not INGEST_API_KEY:
        raise HTTPException(status_code=503, detail="Telemetry ingestion is not configured")
    if not secrets.compare_digest(x_api_key, INGEST_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid ingestion API key")
    if not re.fullmatch(r"tenant_[a-z0-9_]+", x_tenant_id):
        raise HTTPException(status_code=400, detail="Invalid tenant ID")

    ts = datetime.now(timezone.utc)
    status_point = (
        Point("robot_status")
        .tag("tenant_id", x_tenant_id)
        .tag("robot_id", robot_id)
        .field("status", telemetry.status)
        .field("fault_code", telemetry.fault_code or "none")
        .time(ts, WritePrecision.S)
    )
    if telemetry.uptime_s is not None:
        status_point.field("uptime_s", telemetry.uptime_s)
    points = [
        status_point,
        Point("battery")
            .tag("tenant_id", x_tenant_id)
            .tag("robot_id", robot_id)
            .field("soc_pct", float(telemetry.battery))
            .time(ts, WritePrecision.S),
        Point("odometry")
            .tag("tenant_id", x_tenant_id)
            .tag("robot_id", robot_id)
            .field("x_m",     float(telemetry.x))
            .field("y_m",     float(telemetry.y))
            .field("speed_ms", float(telemetry.speed))
            .time(ts, WritePrecision.S),
        Point("tasks")
            .tag("tenant_id", x_tenant_id)
            .tag("robot_id", robot_id)
            .field("completed_total", int(telemetry.tasks_done))
            .time(ts, WritePrecision.S),
    ]
    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)
    return {"status": "ok", "robot_id": robot_id, "timestamp": ts.isoformat()}


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    try:
        database_status = "pass" if influx.health().status == "pass" else "fail"
    except Exception:
        database_status = "fail"
    return {"status": "ok" if database_status == "pass" else "degraded", "database": database_status, "version": "0.1.0",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).resolve().parent.parent / "Fleetwatch.html")
