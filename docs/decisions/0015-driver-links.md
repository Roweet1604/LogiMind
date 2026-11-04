# 0015: Driver access by signed per-route links (P9, backend)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- **No driver accounts.** A dispatcher (API key) creates a link for **one route of one plan**: `POST /api/plans/{id}/driver-links {route_index, ttl_minutes, label}`. Default lifetime 12 h, allowed 5 min to 24 h. Links are made only for completed plans that the validator accepted (409 otherwise), so an infeasible plan never reaches a driver as a working route.
- **Token** `dl1.<claims>.<HMAC-SHA256>`, with claims link id, tenant, plan, route and expiry. The secret is `LOGIMIND_DRIVER_LINK_SECRET` (at least 32 characters). Without it, a random per-process secret is used and links die on restart; this is for development only and logged as a warning. The token itself is not stored.
- **Every driver call** checks the signature and the expiry, then the `driver_links` row: it must exist, not be revoked, and name the same tenant, plan and route. The data is then read through a tenant session for the link's tenant (the usual data-layer filter). So even a correctly signed token that disagrees with its record is refused.
- **Responses:** a customer not on the link's route gets the same 404 as one that does not exist. A bad, expired or revoked token gets 401.
- **Link in the URL fragment:** `<LOGIMIND_DRIVER_APP_URL>/#t=<token>` (default `http://localhost:5174`). Browsers do not send fragments to servers, so the token does not end up in access logs. The PWA sends it as `X-Driver-Token`.
- **Separate credentials:** a driver token is never accepted as an API key, and an API key is never accepted as a driver token (tested). Each link has its own rate-limit bucket (`link:<id>`).
- **Driver endpoints:**
  - `GET /api/driver/route` returns the stops in order, with the latest status and the photo count. `lat`/`lon` are set only for lon/lat (`haversine`) plans; planar test instances say "no map coordinates". `superseded_by` is set when the plan was replanned.
  - `POST /api/driver/stops/{customer}/status` takes delivered, or failed with a reason (`not_home`, `refused`, `wrong_address`, `access_problem`, `damaged`, `other` + a note). It also takes `client_event_id`, which is unique per tenant: resending the same update returns the stored one (`duplicate: true`), so the offline queue can retry safely. Reusing the id for a different update gets a 409. The phone's clock is stored separately (`occurred_at`) from the server's `received_at`.
  - `POST /api/driver/stops/{customer}/photo` accepts JPEG, PNG or WebP, **detected from the bytes**; the declared type and file name are ignored. Limits: at most 3 MB (413) and 5 per stop. The photo is stored as `<data dir>/pod/<tenant id>/<generated id>.<ext>`, written to a temporary file then renamed. A SHA-256 is recorded.
- **Dispatcher endpoints:** `GET /api/plans/{id}/stop-reports` and `GET /api/photos/{id}` (served with `nosniff`, `no-store`). `DELETE /api/driver-links/{id}` revokes a link. Every create, revoke, report and photo writes an audit row; the actor is the link id for driver actions.
- **Reports do not change the plan.** Replanning after a failure stays a dispatcher action (`POST /api/plans/{id}/replan`), so nothing changes an active plan without a person deciding.
- **Storage:** migration 0004 adds the tables `driver_links`, `stop_events` and `pod_photos`, all tenant-owned.

## Known limits
- Photos are not re-encoded, so EXIF data (which can include GPS) is kept. Stripping it would need an image library; not done.
- A route is identified by its index in the stored plan. GA plans store routes without a fixed vehicle number, so "route 2" means the third route.
- Photos are on the local disk, not in object storage; Docker Compose needs a volume for `<data dir>/pod`.
