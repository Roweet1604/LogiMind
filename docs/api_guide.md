# LogiMind API guide

The full, always-current reference is the OpenAPI page of a running server: `http://localhost:8000/docs`. This guide shows the main calls in order. Examples use `curl` from Git Bash; put your key in an environment variable, never in a file you commit.

```
export LM_KEY=...        # printed once by: python manage.py create-tenant "My fleet"
export API=http://localhost:8000
```

## 0. Before you start
- Start the API **and a worker** (from `backend/`): `uvicorn app.main:app --port 8000` and `python -m app.jobs.worker`. Without a worker, plans stay `queued` (decision 0021). For one-process development: `LOGIMIND_WORKER=inline`.
- `GET /api/health` (no key): versions, `research_endpoints`, `distances` (OSRM configured?), `jobs` (worker mode, queued, running, last heartbeat).
- Every tenant endpoint needs `X-API-Key`. Wrong or revoked key: `401`. Too many requests: `429` with `Retry-After` (default 60 per minute per key). Another tenant's object: `404`, the same answer as "does not exist".

## 1. Who am I
`GET /api/whoami` -> tenant id and name, key id.

## 2. Import orders (optional)
`POST /api/orders/import` (multipart, field `file`, .csv or .xlsx, at most 5 MB). Columns: `id, demand` and `x, y` or `lon, lat`; optional `ready_time, due_time, service_time`.
```
curl -s -H "X-API-Key: $LM_KEY" -F file=@orders.csv $API/api/orders/import
```
Answer: `ok`, `rows`, `issues` (each with the spreadsheet row, column and problem) and, only when every row is valid, `customers` ready for a plan. Nothing is stored.

## 3. Create a plan
`POST /api/plans` -> `202 {"plan_id", "state": "queued", "engine", "selection", "distance_source"}`.
```json
{
  "instance": {"name": "monday", "metric": "haversine", "depot_x": 77.5946, "depot_y": 12.9716,
               "vehicle_count": 3, "vehicle_capacity": 20, "fixed_vehicle_cost": 0,
               "customers": [{"id": 1, "x": 77.6408, "y": 12.9784, "demand": 3}]},
  "engine": "auto",
  "time_limit_s": 3,
  "distance_source": "straight_line"
}
```
- `engine`: `auto` (the picker chooses and explains why), `ortools`, `hybrid`, `ga` (GA + local search).
- `time_limit_s`: the engine's total wall-clock budget (default 10, at most `ROUTEOPT_MAX_TIME_LIMIT_S`).
- `distance_source` (lon/lat only): `straight_line` (default), `osrm` (self-hosted OSRM at `LOGIMIND_OSRM_URL`; if it is missing or down, the plan uses the estimate and `distance_source.fallback` is `true` with the reason), `estimate` (straight line x 1.3 at 25 km/h; labelled "not road data").
- Time windows: per customer `ready_time`, `due_time`, `service_time`; depot `depot_ready_time`, `depot_due_time`; `time_unit` (default `min`).
- Invalid input: `422` with every error listed.

## 4. Read plans
- `GET /api/plans` -> the tenant's plans, newest first (state, engine, feasible, distance, `distance_fallback`).
- `GET /api/plans/{id}` -> everything: `state` (`queued`, `running`, `completed`, `failed`), `status` (solver status, e.g. `solved`, `no_solution`, `hard_timeout`), **`feasible` (the validator's verdict)**, `result` (routes, validation with violations, metrics), `selection` (engine explanation), `distance_source`, `job` (attempts, worker, requeues after a worker crash), replan lineage.

Poll until `state` is `completed` or `failed`, or use a webhook.

## 5. Replan after a disruption
`POST /api/plans/{id}/replan` (only for a completed, feasible plan; otherwise `409`):
```json
{"event": {"type": "urgent_order", "completed": {"0": 2},
           "customer": {"id": 99, "x": 77.6974, "y": 12.9591, "demand": 1}},
 "engine": "ortools", "time_limit_s": 3}
```
Events: `vehicle_breakdown` (`vehicle`), `failed_delivery` (`customer_id`, `retry`), `urgent_order` (`customer`). `completed` = stops already done per vehicle; they are frozen. `now` (time-window plans) = current time. The GA is refused (`422`) when stops are frozen. The new plan links to its parent; `replan.timing.disruption_to_feasible_s` is measured from the request to the validated plan.

## 6. Webhooks
`POST /api/webhooks {"url": "https://...", "events": ["plan.completed", "plan.failed", "plan.replanned"]}` -> `201` with a `secret` (shown once). Each delivery is signed with HMAC-SHA256 in the `LogiMind-Signature` header; up to 4 attempts with back-off. `GET /api/webhooks`, `DELETE /api/webhooks/{id}`, `GET /api/webhooks/{id}/deliveries`. URLs on localhost or literal private addresses are refused (host names are not resolved; decision 0010).

## 7. Audit log
`GET /api/audit?limit=100`: plan create / complete / fail / replan (with job id and attempt), imports, webhook deliveries, driver links.

## 8. Drivers
- Dispatcher: `POST /api/plans/{id}/driver-links {"route_index": 0, "ttl_minutes": 720}` -> a signed link to one route (at most 24 h); `GET` lists, `DELETE /api/driver-links/{id}` revokes. `GET /api/plans/{id}/stop-reports`, `GET /api/photos/{id}`.
- Driver (header `X-Driver-Token`, from the link): `GET /api/driver/route`, `POST /api/driver/stops/{customer}/status {"status": "delivered" | "failed", "reason", "client_event_id"}`, `POST /api/driver/stops/{customer}/photo` (JPEG/PNG/WebP, at most 3 MB). Reports never change the plan.

## 9. Customer ETA messages (stub only)
`PUT /api/contacts/{customer_id} {"channel": "sms", "address": "...", "opt_in": true}`; `GET /api/plans/{id}/etas?shift_start=2026-11-06T08:00:00%2B05:30`; `POST /api/plans/{id}/notify-etas {"shift_start": ...}`; `GET /api/notifications`. The only sender is a **stub that logs and never sends**. ETAs are planned times, not live traffic.

## 10. Copilot
`GET /api/copilot/status` (is a local model available?), `POST /api/copilot/chat {"message": "...", "session_id": null}`, `POST /api/copilot/confirm {"session_id", "pending_id", "approve"}` (replans wait for this). Without Ollama the API says plainly that no local model is available. **No real model has been evaluated** (see report).

## 11. Research endpoints (development only, OFF by default)
`/api/instances`, `/api/runs`, `/api/experiments`, `/api/benchmarks` have no tenants and return `403` unless `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1`. Their runs are **benchmark jobs**: they run alone on the worker.
