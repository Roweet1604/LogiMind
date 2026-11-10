# Limitations: what is UNTESTED, NOT VERIFIED or not built

Last checked: 5 Nov 2026; browser findings added 10 Nov 2026 (docs/report/demo/README.md). Words: **UNTESTED** = written but never run; **NOT VERIFIED** = runs in automated tests, but not checked in the real setting; **NOT RUN** = no measurement exists. Do not present any item below as working or measured.

## UNTESTED (never run)
- **Docker Compose** (`docker-compose.yml`, `backend/Dockerfile`, `frontend/` and `driver/` Dockerfiles and nginx configs, `.env.example`): Docker is not installed on the development laptop (decision 0020). This includes the `worker` service, PostgreSQL, the volumes, the nginx `/api` proxy and the one-command start.
- **PostgreSQL**: all database code and the 6 migrations have only run on SQLite. The queue's lock row is designed for PostgreSQL row locks but was not tried on it.
- **Self-hosted OSRM**: the `osrm` Compose profile, the image tag `v5.27.1`, the preprocessing steps. No map extract was downloaded (smallest official file with Bengaluru: 559 MB; decision 0020).

## NOT RUN (no numbers exist)
- **Copilot with a real model**: Ollama is not installed. The 50-item evaluation set is a DRAFT awaiting team review. No intent accuracy, latency or failure rate exists for any model.
- **10 s budgets on the held-out benchmark set**: only 3 s was run there (compute cap). 10 s results exist only on the P3 set, which overlaps the OR-Tools tuning instances (biased).
- **Calibration of the straight-line estimate** (detour factor 1.3, 25 km/h): both are assumptions.
- **Gehring-Homberger** (large VRPTW) benchmarks: not downloaded.
- **Pilot or operator data**: none. All "real-world-like" data is synthetic and labelled so.

## NOT VERIFIED (tests pass, but not checked for real)
- **Road distances end to end**: tests replay real OSRM answers recorded once for 6 synthetic points; the app never talked to an OSRM server. OSRM durations are free-flow (no traffic) and probably optimistic for Bengaluru.
- **Driver PWA on a phone**: checked in desktop Chrome only; not installed on a phone; camera capture and the photo re-encoding (EXIF stripping) never ran in a browser; the maps deep link was not opened.
- **Ops console in a browser**: verified sign-in, CSV import (with errors and valid), plan creation with the fallback warning, all three replan forms (urgent order, vehicle breakdown, failed delivery; the last two on 5 Nov 2026 with a separate worker process), Drivers panel, copilot "no model" message. NOT checked in a browser: `.xlsx` import, the copilot answering, the research pages since the queue change, the Drivers panel since the queue change.
- **Worker in production shape**: tested with SQLite, two real worker processes on one laptop, a hard kill and a restart. Not tested: several workers on PostgreSQL, a long-running worker for days, the console warning when no worker runs (it does not exist yet).
- **Webhooks to real receivers**: only a fake sender in tests.
- **ETA messages**: only a stub sender that logs; no SMS or e-mail provider exists (zero-cost rule).

## Known design limits (built this way on purpose, or not yet fixed)
- **Replans forget earlier disruptions** (found in the browser walk-through, 10 Nov 2026): a breakdown or a retry rule applies only to the replan that records it. A later replan of the new plan can give the broken vehicle stops again and can put a retried customer next; completed stops must be re-entered each time. For the demo, replan from the original plan.
- **No arrival times on the console's plan page**: time windows are respected (validator), but planned arrival and window per stop are shown only in the driver app and the API.
- **Selector model card** is a document (`docs/model_card_selector.md`), not a console page; the Methodology page does not describe the hybrid or the selector.
- **Engine picker**: trained and evaluated on synthetic data; not a proven improvement over always using the hybrid (model card).
- **Hybrid**: the 50/50 split between OR-Tools and the GA is untuned; the hybrid is not a clear win over OR-Tools (P3 and the held-out set, see report).
- **GA and frozen stops**: the GA cannot keep completed stops; replans with frozen stops must use OR-Tools.
- **Replanning**: the failed attempt's own travel is not modelled. A retried delivery is no longer planned as the very next stop (fixed 5 Nov 2026, decision 0023), but there is no minimum time delay, and the GA is refused for retries. The replanning experiment used 6 synthetic instances and one seed, and ran before the retry rule.
- **Queue**: CLI experiment scripts run outside the queue (run them when no worker is busy); polling every 0.5 s; a crashed job's solve may run twice (the result is written once).
- **Copilot sessions** live in the API process memory (lost on restart); chat requests block until the solver finishes.
- **Webhook SSRF guard** does not resolve host names. **Rate limiter** is per process.
- **Photos**: no offline photo queue; the server does not strip EXIF itself.
- **ETAs** are planned times; they are not updated from driver progress.
- **Driver links** need `LOGIMIND_DRIVER_LINK_SECRET`, or they stop working on restart; a real deployment needs HTTPS.
- **Road matrix** cache keeps whole matrices only; at most 250 distinct points per plan.
- **Benchmarks** run on one laptop; wall-clock results depend on the machine.
