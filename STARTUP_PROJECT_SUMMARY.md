# FleetWatch Startup Project Summary

**Document purpose:** This is a self-contained description of the FleetWatch
project as it currently exists. It is intended to be pasted into ChatGPT and
compared with the original startup plan, product requirements, or business
vision.

**Project stage:** Working local MVP / technical proof of concept

**Last reviewed:** July 2026

---

## 1. Executive Summary

FleetWatch is a multi-tenant robot fleet monitoring and observability product
for organizations operating autonomous mobile robots (AMRs), particularly in
warehouses and industrial facilities.

The current MVP collects robot telemetry, stores time-series data in InfluxDB,
calculates fleet-level operational indicators, and presents live robot status
through two interfaces:

1. A custom FleetWatch web dashboard served by the FastAPI application.
2. An optional Grafana dashboard for operational charts and time-series
   analysis.

The system currently tracks five simulated robots and reports battery level,
operating status, position, speed, completed tasks, uptime, and faults. It also
separates telemetry by tenant so one customer's API and Grafana queries do not
include another customer's data.

This is a functional monitoring MVP, not yet a production SaaS platform. The
core observability workflow works locally, while durable identity storage,
deployment automation, customer onboarding, alert delivery, billing, and
production security remain future work.

---

## 2. Startup Problem Being Addressed

Warehouse and industrial robot operators need a single place to answer basic
operational questions such as:

- Which robots are currently online?
- Which robots are moving, idle, charging, or faulted?
- Is battery health affecting operations?
- Where is a robot and how fast is it moving?
- How much work has the fleet completed?
- Which faults are active or occurred recently?
- What is the overall operational uptime of the fleet?
- Can data belonging to different customer fleets be kept separate?

Without a fleet observability layer, operators may need to inspect individual
robots, vendor-specific systems, or raw time-series data. FleetWatch aims to
provide a unified, vendor-neutral monitoring layer over robot telemetry.

---

## 3. Product Vision

The broader product direction suggested by the current MVP is:

> Build a multi-tenant robot fleet observability SaaS that gives warehouse
> operators a real-time and historical view of robot health, productivity,
> availability, and faults across an entire fleet.

The current code supports the technical foundation of that vision. It does not
yet establish product-market fit, commercial validation, integrations with
real robot vendors, or the complete operational requirements of a SaaS
business.

---

## 4. Objectives Covered by the Current Project

### 4.1 Centralized fleet visibility

The project provides one dashboard for viewing all robots assigned to a tenant.
Each robot has a status card and a detail view.

**Covered metrics:**

- Robot ID
- Operating state: `idle`, `moving`, `charging`, or `fault`
- Battery state of charge
- X/Y position in metres
- Speed in metres per second
- Cumulative completed tasks
- Robot uptime in seconds
- Current fault code
- Last telemetry observed within the active monitoring window

### 4.2 Fleet-level operational KPIs

The API and dashboards calculate:

- Registered robot count
- Online robot count
- Offline robot count
- Average battery percentage
- Total completed tasks
- Active fault count
- Fleet uptime percentage

For the MVP, a robot is considered online when recent status telemetry exists
within the configured five-minute query window. Fleet uptime is calculated as
the proportion of registered robots that are online and not currently faulted.

### 4.3 Fault visibility

The project supports:

- A current active-fault count
- Fault codes attached to individual robot status
- A fault table covering the last 24 hours
- Status/fault consistency validation during API ingestion
- Simulated faults such as `NAV_TIMEOUT`, `SENSOR_ERR`, and `ESTOP`

### 4.4 Real-time telemetry simulation

The included simulator models five AMRs and writes new telemetry every second.
It simulates:

- Battery drain and charging behavior
- Idle-to-moving task transitions
- Movement within a bounded 50 m by 30 m area
- Variable robot speed
- Task completion
- Random faults and recovery
- Uptime and heartbeat data

The simulator makes it possible to demonstrate and test the product without
connecting physical robots.

### 4.5 Historical time-series observability

InfluxDB stores telemetry as time-series measurements. Grafana can display:

- Battery history for all robots
- Robot speed history
- Cumulative completed tasks
- Current robot status
- Fault history
- Fleet KPI stat panels

The Grafana queries aggregate across robots correctly and include a tenant
selector.

### 4.6 Basic tenant isolation

Telemetry includes a `tenant_id` tag. Protected API queries filter by both the
authenticated user's tenant and their assigned robot IDs. Grafana queries also
filter by a selected tenant.

New organization registrations receive unique tenant IDs. The local demo fleet
uses `tenant_fleetwatch` so the simulator, demo account, API, and dashboards all
reference the same data.

### 4.7 Authentication and protected fleet access

The backend supports:

- Account registration
- Password hashing with bcrypt
- OAuth2-compatible username/password login
- JWT access tokens
- Protected fleet endpoints
- One-day token expiration
- Frontend handling for invalid or expired sessions

### 4.8 Controlled telemetry ingestion

The ingestion API requires:

- An `X-API-Key` header
- An `X-Tenant-ID` header
- A valid telemetry payload
- A supported robot status value
- Consistent fault state and fault code values

Invalid keys, malformed tenant IDs, and contradictory status/fault payloads are
rejected.

### 4.9 Local demonstration and developer usability

The project includes:

- Interactive OpenAPI/Swagger documentation
- A health endpoint that checks InfluxDB connectivity
- A web dashboard served directly from FastAPI
- A configurable telemetry simulator
- An importable Grafana dashboard
- Environment variable examples
- Local setup documentation

---

## 5. Current User Experience

### Operator workflow

1. The operator opens the FleetWatch web dashboard.
2. They sign in with their account.
3. The dashboard loads fleet KPIs, individual robot cards, and recent faults.
4. The operator can select a robot to view its current metrics.
5. Data automatically refreshes every 15 seconds or can be refreshed manually.
6. The operator can use Grafana for more detailed time-series charts.

### Developer/integration workflow

1. InfluxDB is started with the configured organization and bucket.
2. FastAPI is started with database, JWT, ingestion, and optional demo-account
   environment variables.
3. A robot or simulator sends tenant-tagged telemetry.
4. API endpoints query recent or historical InfluxDB data.
5. FleetWatch and Grafana visualize the same underlying measurements.

---

## 6. System Architecture

```text
Robot simulator or robot agent
          |
          | tenant-tagged telemetry
          v
      InfluxDB 2.x
       /       \
      /         \
FastAPI API     Grafana
    |
    | JSON over HTTP + JWT
    v
FleetWatch web dashboard
```

### Main components

| Component | Responsibility |
|---|---|
| `app/main.py` | Authentication, tenant-scoped fleet APIs, ingestion, KPI queries, health check, and serving the web UI |
| `Fleetwatch.html` | Login, KPI cards, robot cards, detail modal, fault table, refresh lifecycle, and browser session handling |
| `robot_sim.py` | Generation of realistic development telemetry for five AMRs |
| `robot_fleet_dashboard.json` | Grafana dashboard definition and tenant-filtered Flux queries |
| InfluxDB | Time-series storage and aggregation source |
| Grafana | Historical and operational visualization |

---

## 7. Telemetry Data Model

Every measurement written by the synchronized system includes:

- `tenant_id` tag
- `robot_id` tag
- UTC timestamp

### Measurements and fields

| Measurement | Fields |
|---|---|
| `robot_status` | `status`, `fault_code`, optional `uptime_s` |
| `battery` | `soc_pct` |
| `odometry` | `x_m`, `y_m`, `speed_ms` |
| `tasks` | `completed_total` |

### Supported robot states

- `idle`
- `moving`
- `charging`
- `fault`

The API, simulator, custom dashboard, and Grafana dashboard use the same names
and field conventions.

---

## 8. Available API Capabilities

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | FleetWatch web dashboard |
| `GET` | `/health` | API and InfluxDB health |
| `POST` | `/auth/register` | Create a new organization account and tenant |
| `POST` | `/auth/token` | Authenticate and receive a JWT |
| `GET` | `/fleet/robots` | List robots assigned to the authenticated tenant |
| `GET` | `/fleet/robots/{robot_id}` | Get the latest telemetry for one authorized robot |
| `GET` | `/fleet/summary` | Get fleet-wide KPI values |
| `GET` | `/fleet/faults` | Get recent tenant-scoped faults |
| `POST` | `/ingest/{robot_id}` | Submit validated tenant-tagged robot telemetry |
| `GET` | `/docs` | Interactive API documentation |

---

## 9. Security and Isolation Already Implemented

- Passwords are stored as bcrypt hashes in the current process.
- Fleet APIs require JWT bearer authentication.
- JWT signing secrets are supplied through environment configuration.
- InfluxDB tokens are no longer embedded in source files.
- Telemetry ingestion uses a separate API key.
- Tenant IDs and robot IDs are escaped in Flux queries.
- API queries filter tenant data and authorized robot lists.
- User-controlled values are escaped before insertion into dashboard HTML.
- Registration produces unique tenant IDs.
- CORS origins are configurable and restricted by default to the local API.
- `.env` is excluded by `.gitignore`.

These protections are suitable for a local MVP baseline, but not a complete
production security model.

---

## 10. Validation Completed

The working local setup has been tested for:

- Python syntax validity
- Grafana dashboard JSON validity
- Dashboard loading in a headless Chrome browser
- InfluxDB health connectivity
- Account authentication
- JWT-protected endpoint access
- Five online simulator robots
- Fleet summary calculations
- Individual robot detail retrieval
- Fault retrieval
- Rejection of invalid ingestion API keys
- Acceptance of valid ingestion requests
- Rejection of contradictory fault payloads
- Isolation of a second tenant with no telemetry
- Unique tenant IDs for two registrations using the same company name
- Exact execution of the five corrected Grafana KPI Flux queries
- Discovery of `tenant_fleetwatch` through the Grafana tenant variable query
- Removal of the previously hardcoded InfluxDB token and JWT placeholder secret

At the time of the final smoke test, the system reported five online robots and
successfully returned live simulator data. Values such as battery, tasks, and
faults change continuously while the simulator runs.

---

## 11. What the MVP Does Not Yet Cover

The following are important boundaries when comparing the project with a full
startup or production plan.

### Product and customer capabilities not implemented

- Real robot manufacturer or ROS integrations
- Customer discovery or validated product-market fit
- Mobile application
- SMS, email, Slack, Teams, or webhook alerts
- Alert rules, acknowledgement, escalation, and on-call workflows
- Predictive maintenance or anomaly detection
- Battery degradation and remaining-useful-life analysis
- Route visualization or a live warehouse map
- Task creation, assignment, scheduling, or dispatch
- Robot remote control or emergency-stop control
- Maintenance work orders and service history
- SLA reporting and downloadable reports
- Customer-defined dashboards and KPI thresholds
- Roles such as owner, administrator, operator, and viewer
- User invitations into an existing organization
- Billing, subscriptions, trials, plans, or usage metering
- Vendor/device provisioning and key rotation workflows
- Public customer-facing API versioning or SDKs

### Production engineering not implemented

- Persistent user and organization database such as PostgreSQL
- Persistent tenant-to-robot assignment database
- Multiple API workers with shared identity state
- Per-tenant or per-device ingestion credentials
- Automatic credential rotation or secret-manager integration
- Refresh tokens, password reset, email verification, or MFA
- Rate limiting and abuse protection
- Audit logs
- Structured application logging and distributed tracing
- Background jobs or queues
- Automated unit/integration test suite in the repository
- CI/CD pipeline
- Docker Compose or Kubernetes deployment definition
- Managed InfluxDB/Grafana provisioning
- Database backup and disaster recovery process
- High availability, horizontal scaling, or load testing
- Formal monitoring of the monitoring platform itself

### Compliance and commercial readiness not implemented

- GDPR workflows and data-subject handling
- EU data residency controls
- Retention and deletion policies per tenant
- Security review, penetration testing, or threat model
- Data processing agreements and legal policies
- SOC 2 or ISO 27001 controls
- Defined pricing, ICP, go-to-market motion, or sales funnel
- Support operations and customer success processes

---

## 12. Known Technical Limitations and Risks

1. **Users are stored in memory.** Accounts created through the API disappear
   when the server restarts. The optional demo account is recreated from
   environment variables.

2. **Tenant-to-robot assignments are stored in memory.** They are not yet backed
   by a durable relational database.

3. **The ingestion key is global.** Production should issue scoped, revocable
   credentials per tenant or device.

4. **The simulator writes directly to InfluxDB.** This is convenient locally,
   but real robot agents should normally use an authenticated ingestion gateway
   so validation, quotas, and audit logging are centralized.

5. **Grafana tenant selection is not customer authentication.** Grafana queries
   are tenant-filtered, but a shared Grafana datasource can potentially query
   other tenants. Production isolation should use separate organizations,
   datasources, credentials, or an authenticated query layer.

6. **Fault history contains sampled fault values.** A fault persisting for
   multiple telemetry intervals can produce repeated records rather than one
   lifecycle event with opened/resolved timestamps.

7. **Uptime is a simplified operational KPI.** It is based on recent heartbeat
   availability and active fault state, not a formal SLA calculation over a
   long reporting interval.

8. **The backend uses synchronous InfluxDB calls.** This is acceptable for the
   local MVP but may limit concurrency under production load.

9. **The existing local Grafana instance requires its administrator login.** The
   updated dashboard file and queries are ready, but importing it remains a
   Grafana administration step.

---

## 13. Recommended Next Objectives

### Phase 1: Turn the technical demo into a durable MVP

1. Add PostgreSQL for users, organizations, robot assignments, and device keys.
2. Add organization invitations and role-based access control.
3. Route simulator and real device traffic through the ingestion API.
4. Issue separate, revocable credentials to every robot or customer agent.
5. Add automated tests for authentication, tenant isolation, Flux queries, and
   ingestion validation.
6. Create Docker Compose for API, PostgreSQL, InfluxDB, Grafana, and provisioning.
7. Add fault lifecycle events with opened, acknowledged, and resolved states.

### Phase 2: Validate operator value

1. Connect one real ROS/AMR data source.
2. Interview warehouse operators and define their top five daily decisions.
3. Add configurable alerts and one delivery channel.
4. Add a warehouse map and last-seen indicator.
5. Measure time-to-detect, time-to-recover, robot utilization, and task throughput.
6. Pilot the product with one warehouse and a clearly defined success metric.

### Phase 3: Prepare for a commercial SaaS launch

1. Add customer onboarding and device provisioning.
2. Define plans, limits, pricing, and a trial flow.
3. Add audit logs, retention policies, backups, and operational monitoring.
4. Complete a threat model and production security review.
5. Establish EU hosting, privacy, and compliance requirements.
6. Build repeatable sales, support, and customer-success processes.

---

## 14. Suggested Success Metrics

### Product metrics

- Daily and weekly active operators
- Number of connected robots and active fleets
- Dashboard sessions per operator
- Alert acknowledgement rate
- Mean time to detect a robot fault
- Mean time to resolve a robot fault
- Percentage of faults first detected by FleetWatch
- Reduction in manual robot inspection time

### Fleet outcomes

- Robot availability and operational uptime
- Fleet utilization
- Tasks completed per robot-hour
- Average charging time
- Fault frequency by robot and fault class
- Repeat-fault rate
- Unplanned downtime

### Business metrics

- Pilot-to-paid conversion
- Monthly recurring revenue
- Revenue per connected robot or fleet
- Customer acquisition cost
- Gross margin
- Net revenue retention
- Customer churn
- Support effort per customer

---

## 15. Questions for Comparison With the Original Plan

When comparing this implementation with the original startup plan, answer:

1. Is FleetWatch primarily observability software, a fleet management system,
   or a robot control platform?
2. Does the original target customer match warehouse and industrial AMR
   operators?
3. Which original must-have features are already implemented?
4. Which original must-have features are still absent?
5. Were Grafana and InfluxDB part of the intended architecture?
6. Was multi-tenancy required at MVP stage, and is the current isolation model
   sufficient?
7. Was the first release expected to integrate real ROS or vendor robots?
8. Did the original plan include alerts, predictive maintenance, maps, task
   dispatch, or remote control?
9. What was the intended buyer: warehouse operator, fleet manager, robotics
   integrator, robot manufacturer, or enterprise IT team?
10. What outcome was the customer expected to pay for: visibility, reduced
    downtime, higher throughput, compliance reporting, or fleet control?
11. Which missing capability blocks the first customer pilot?
12. Which current capabilities are unnecessary for the original MVP?
13. What measurable pilot success criterion was specified?
14. What pricing and go-to-market assumptions were in the original plan?
15. What should be built next based on customer risk rather than only technical
    completeness?

---

## 16. Concise Comparison Prompt

The text below can be pasted after the original startup plan and this document:

> Compare my original FleetWatch startup plan against the current project
> summary. Create a table with: original objective, current implementation
> status, evidence, gap, business importance, technical effort, and recommended
> priority. Separate true MVP blockers from later enhancements. Identify scope
> creep, missing customer validation, architecture mismatches, security risks,
> and the shortest path to a real customer pilot. End with a prioritized 30-day,
> 60-day, and 90-day execution plan.

---

## 17. Overall Assessment

FleetWatch currently proves that tenant-tagged AMR telemetry can flow into a
time-series database and be converted into useful fleet-level operational views
through both a custom product interface and Grafana. The system demonstrates
the core technical idea and is suitable for demos, experimentation, and early
operator feedback.

The largest remaining gap is not another dashboard metric. It is the transition
from a local observability prototype to a durable customer product: persistent
identity and fleet configuration, real robot integration, alert workflows,
automated deployment/testing, and evidence that operators will adopt and pay
for the resulting operational improvement.
