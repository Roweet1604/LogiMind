# Browser walk-through, 10 Nov 2026

Every feature of LogiMind tried by hand in a real browser (desktop Chrome, through the Claude in Chrome extension).
All data is synthetic. Screenshots are in this folder; the number in brackets is the file prefix.

## Set-up, and what differed from the request
- `start-dev.bat` with no arguments on the default ports **stopped with a clear message**, as designed:
  `Port 8000 is already in use by python.exe (process 39788)` and `Port 5173 ... by node.exe (process 44712)`,
  "Nothing was stopped." Those were the developer's own servers (a `uvicorn --reload --port 8000` and a Vite
  server, started 15:28), so they were left alone.
- The walk-through therefore ran `start-dev.bat --no-browser` with `API_PORT=8070`, `CONSOLE_PORT=5197`,
  `DRIVER_PORT=5198`, a throwaway database and data folder in the scratch folder (the developer's own database was
  not touched), and `LOGIMIND_WEBHOOK_ALLOW_PRIVATE=1` so webhooks could reach a local test receiver on port 8099.
  OSRM was not configured (on purpose, to see the fallback). Ollama was not running (`localhost:11434` refused).
- The API was restarted three times during the test (for the offline test, for research mode, and back).
- A second tenant, "Acme Couriers (synthetic test)", was made with `manage.py create-tenant` for the API-key
  sign-in and the isolation checks. Its key is not in any committed file.
- The signed driver link in [17] is masked on screen; both test links were revoked afterwards [33].

## Results
Worked = did what it should. Worked with problems = works, with a problem listed. Failed = did not work.
Not tested = could not be tried (reason given).

| # | Feature | Result | Note |
| --- | --- | --- | --- |
| 1a | Demo-mode sign-in | Worked | Opened signed in to "Demo Fleet (synthetic)" with the "Demo mode" label and 3 feasible demo plans [01]. |
| 1b | Normal API-key sign-in | Worked | Sign out of the demo, wrong key refused in plain words [02], test key accepted, tenant shown, no demo plans visible [03]. |
| 2a | CSV import with bad rows | Worked | 3 of 4 rows flagged with row, column and reason (not a number, duplicate id, longitude out of range); nothing imported [04]. |
| 2b | Excel (.xlsx) import | Worked with problems | 10 orders with time windows imported [05]. Problem: the depot stayed at the planar default 50/50 for lon/lat orders. **Fixed** (depot moves to the middle of the orders, with a note) [31]. |
| 2c | Synthetic sample | Worked | 12 orders, labelled synthetic [07]. |
| 3a | Plan with OR-Tools | Worked | Feasible, 377.99, solid blue [07]. |
| 3b | Plan with GA + local search | Worked | Feasible, 377.99, dashed orange [08]. |
| 3c | Plan with the hybrid | Worked | Feasible, 377.99, dash-dot [09]. All three found the same total on this small sample. |
| 3d | engine=auto with explanation | Worked | Chose the hybrid; shows predicted regret per engine, the tree rule, and "outside the training range: 10 customers (trained on 20-80)" [06]. |
| 4a | Validator status | Worked | "feasible" badge from the validator on every plan; a plan with no solution shows "no plan" [11]. |
| 4b | Fallback-distances warning | Worked | "Fallback distances: not road data" with the reason (no OSRM configured) [06]. |
| 4c | Time windows | Worked with problems | Windows respected: 0 violations, 0 lateness, 227 min waiting (checked through the API). Problem: the plan page shows no arrival times or windows per stop; only the driver app shows the windows [18]. Not fixed (a new view, not a small bug). |
| 4d | Timeout shown as a timeout | Worked with problems | 600 tight-window orders, OR-Tools, 0.5 s: red "no plan", "timeout" badge, "Time limit reached before any solution" [11]. Problem: the replan box said "This plan is completed". **Fixed** ("without a solution"). Also seen: an instance whose windows cannot be reached is refused before solving, with every stop listed [10]. |
| 5a | Replan: vehicle breakdown | Worked | Vehicle 0 kept its 2 finished stops, 4 stops moved to vehicle 2, feasible, warm start used, 3.50 s to a validated plan, linked to its parent [12, 13]. |
| 5b | Replan: failed delivery (retry) | Worked with problems | Customer 7 revisited last, not next (retry rule) [14]. **Problem (not fixed):** the breakdown from the previous replan was not remembered: broken vehicle 0 got 6 stops again. See "Bigger problems". |
| 5c | Replan: urgent order | Worked | Order 13 inserted, 3 finished stops kept, feasible, 3.11 s [15, 16]. |
| 5d | Confirm and Cancel | Not tested | Confirm/Cancel exists only in the copilot's replan flow; the copilot needs a model (Ollama not running). The console's replan form sends directly. Unit tests only. |
| 6a | Signed driver link | Worked | Link per route, valid 12 h, shown once [17]; revoke works and the driver app then says "Link no longer valid" [33]. |
| 6b | Driver app | Worked | Token removed from the address bar; 5 stops with windows [18]. Known: the driver app says "Route 1" for the console's route 0. |
| 6c | Delivered / Failed with a reason | Worked | "Nobody home" [19, 20]; the console's Drivers panel shows both reports [23]. |
| 6d | Photo upload | Worked | "Photo saved", count 1 in the console [20, 23]. A small PNG test image was used; whether the re-encoding step ran was not checked separately. |
| 6e | Navigate link | Worked (checked, not opened) | A maps directions link with the stop's coordinates, opens in a new tab. The external maps site was not opened. |
| 6f | Offline use and sync | Worked with problems | API stopped: the report was queued ("1 update waiting to sync") [21] and synced by itself after the API came back (20 s retry) [22]. Problem: the badge still said "Online" while the server was down. **Fixed** ("Server unreachable") [32]. Chrome's own offline mode was not used this time (the server was stopped instead). |
| 7 | ETA notifications and opt-in | Worked | Through the API from the browser (there is no console screen): no contact = skipped; contact without opt-in = `skipped_no_opt_in`; opted-in contact = `sent_stub` (logged, never sent); numbers masked; ETAs say "not live traffic" and that distances are the fallback estimate [26]. |
| 8a | Copilot without a model | Worked | Plain "No local model is available", input disabled, planning still works [27]. |
| 8b | Copilot real answer | Not tested | Ollama is not installed or running. |
| 8c | Refusal to edit routes by hand | Not tested | Needs a model. Without one the API answers `kind: unavailable` and does nothing. Covered by unit tests with the fake model only. |
| 9a | Webhooks | Worked | Created (secret shown once); a new plan sent `plan.completed` to the local receiver, delivered on attempt 1 with HTTP 200 and a `LogiMind-Signature: t=...,v1=...` header. The signature value was not recomputed. |
| 9b | Audit log | Worked | `plan.create`, `plan.completed`, `webhook.create`, `webhook.delivered`, `contact.opt_in`, `notify.etas` rows. |
| 9c | Rate limit (429) | Worked | 30 quick requests: 20 answered, then 429 "rate limit exceeded for this API key" with `Retry-After: 1`. |
| 9d | Tenant isolation | Worked | Each tenant gets 404 for the other's plan, driver links, replan and webhook deliveries; neither list shows the other's plans. |
| 10a | Research: comparison tables | Worked | Same instance and budget (3 s): OR-Tools 151.52, GA 156.94, both feasible, with "one run does not establish which method is better" [28]. |
| 10b | Research: Benchmark lab | Worked with problems | Sizes 10 and 25, 1 s, 2 GA seeds: both experiments completed, aggregates per size [29]. Cosmetic: the chart's x-axis shows ticks at 14 and 18 (sizes that were not run). |
| 10c | Selector model card | Worked with problems | Not in the console: it is the document `docs/model_card_selector.md`, which the "Why this engine" text names. The Methodology page [30] does not mention the selector or the hybrid. Not fixed. |
| 11a | API docs (OpenAPI) | Worked | `/docs` loads; Authorize + "Try it out" used for the notification log [25, 26]. |
| 11b | Separate worker | Worked | `/api/health`: `worker_mode: external` with a recent heartbeat [24]; plans record the worker id and 1 attempt. |

## Small bugs fixed (tests added; no test weakened)
1. Plan "Created" times showed UTC as local time (10:08 instead of 15:38 IST): timestamps without a zone are now read as UTC (`frontend/src/lib/format.js`).
2. Lon/lat orders kept the planar default depot 50/50: the depot moves to the middle of the orders, with a visible note (`frontend/src/pages/Plans.jsx`).
3. A plan with no solution said "This plan is completed" in the replan box: now "without a solution" (`PlanDetail.jsx`).
4. Drivers page said "use the replan form below" where there is none: now "the plan's replan form" (`DriverLinks.jsx`).
5. Driver app badge said "Online" while reports could not be sent: now "Server unreachable" until a report gets through (`driver/src/App.jsx`, `lib/sync.js`).

## Bigger problems (listed, not fixed)
1. **Replans forget earlier disruptions.** A breakdown or a retry rule applies only to the replan that records it. A later replan of the new plan can give the broken vehicle stops again, and can put a retried customer next. The dispatcher must also re-enter the completed stops each time. Fixing it means carrying "unavailable vehicles" and retries along the plan chain into `apply_event` and the independent check (`backend/app/replan/`).
2. **No arrival times on the plan page.** Time windows are respected, but the console shows no planned arrival or window per stop.
3. **The selector model card is not in the console**, and Methodology does not describe the hybrid or the selector.
4. **Confirm/Cancel and the copilot's answers** cannot be shown without a local model.
5. The OSRM fallback note shows a setting name ("LOGIMIND_OSRM_URL is not set"); it is the backend's reason text.
