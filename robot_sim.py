"""
Robot Fleet Telemetry Simulator
Publishes fake AMR data to InfluxDB every second.
Edit INFLUX_* constants to match your setup.
"""

import time
import random
import math
import os
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ── CONFIG ─────────────────────────────────────────────────────────────────────
INFLUX_URL    = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG    = os.getenv("INFLUX_ORG", "startup-robot-dashboard")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "robot_fleet")
TENANT_ID     = os.getenv("TENANT_ID", "tenant_fleetwatch")
# ───────────────────────────────────────────────────────────────────────────────

ROBOTS = ["AMR-01", "AMR-02", "AMR-03", "AMR-04", "AMR-05"]

class RobotState:
    """Simulates a single AMR with realistic drifting state."""
    def __init__(self, robot_id):
        self.id            = robot_id
        self.battery       = random.uniform(60, 100)   # %
        self.x             = random.uniform(0, 50)     # metres
        self.y             = random.uniform(0, 30)
        self.speed         = 0.0                       # m/s
        self.tasks_done    = 0
        self.status        = "idle"                    # idle | moving | charging | fault
        self.fault_code    = None
        self.task_timer    = 0
        self.uptime_s      = 0

    def tick(self):
        """Advance state by 1 second."""
        self.uptime_s += 1
        self.battery  -= random.uniform(0.01, 0.04)   # drain

        # Random fault ~0.3% chance per tick
        if random.random() < 0.003 and self.status != "fault":
            self.status     = "fault"
            self.fault_code = random.choice(["NAV_TIMEOUT", "SENSOR_ERR", "ESTOP"])
            self.speed      = 0.0
            return

        # Clear fault after ~15 s
        if self.status == "fault":
            if random.random() < 0.07:
                self.status     = "idle"
                self.fault_code = None
            return

        # Go charge when battery low
        if self.battery < 20:
            self.status = "charging"
            self.speed  = 0.0
            self.battery = min(100, self.battery + 0.5)
            return
        if self.status == "charging" and self.battery < 95:
            self.battery = min(100, self.battery + 0.5)
            return
        if self.status == "charging" and self.battery >= 95:
            self.status = "idle"

        # Execute tasks
        if self.status == "idle" and random.random() < 0.1:
            self.status     = "moving"
            self.task_timer = random.randint(10, 40)

        if self.status == "moving":
            self.task_timer -= 1
            self.speed = random.uniform(0.8, 1.5)
            angle = random.uniform(0, 2 * math.pi)
            self.x = max(0, min(50, self.x + math.cos(angle) * self.speed))
            self.y = max(0, min(30, self.y + math.sin(angle) * self.speed))
            if self.task_timer <= 0:
                self.status    = "idle"
                self.speed     = 0.0
                self.tasks_done += 1

    def to_points(self):
        """Return list of InfluxDB Points for this tick."""
        ts = datetime.now(timezone.utc)
        points = []

        # Heartbeat / status
        points.append(
            Point("robot_status")
            .tag("tenant_id", TENANT_ID)
            .tag("robot_id", self.id)
            .field("status", self.status)
            .field("uptime_s", self.uptime_s)
            .field("fault_code", self.fault_code or "none")
            .time(ts, WritePrecision.S)
        )

        # Battery
        points.append(
            Point("battery")
            .tag("tenant_id", TENANT_ID)
            .tag("robot_id", self.id)
            .field("soc_pct", round(self.battery, 2))
            .time(ts, WritePrecision.S)
        )

        # Odometry
        points.append(
            Point("odometry")
            .tag("tenant_id", TENANT_ID)
            .tag("robot_id", self.id)
            .field("x_m", float(round(self.x, 3)))
            .field("y_m", float(round(self.y, 3)))
            .field("speed_ms", round(self.speed, 3))
            .time(ts, WritePrecision.S)
        )

        # Task counter
        points.append(
            Point("tasks")
            .tag("tenant_id", TENANT_ID)
            .tag("robot_id", self.id)
            .field("completed_total", self.tasks_done)
            .time(ts, WritePrecision.S)
        )

        return points


def main():
    if not INFLUX_TOKEN:
        raise SystemExit("INFLUX_TOKEN must be set")
    client    = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    robots    = [RobotState(rid) for rid in ROBOTS]

    print(f"Simulating {len(robots)} robots for {TENANT_ID} → InfluxDB at {INFLUX_URL}")
    print("Press Ctrl+C to stop.\n")

    tick = 0
    try:
        while True:
            all_points = []
            for robot in robots:
                robot.tick()
                all_points.extend(robot.to_points())

            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=all_points)

            # Console summary every 10 ticks
            if tick % 10 == 0:
                summary = "  ".join(
                    f"{r.id}:{r.status[:4].upper()} bat={r.battery:.0f}% tasks={r.tasks_done}"
                    for r in robots
                )
                print(f"[{tick:05d}s] {summary}", flush=True)

            tick += 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
