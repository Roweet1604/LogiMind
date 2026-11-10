# LogiMind: final presentation script (about 15 minutes)

Every feature is marked **VERIFIED** (walked through in a real browser on 10 Nov 2026; results and screenshots in
[report/demo/README.md](report/demo/README.md)) or **NOT VERIFIED** (not tried, or only covered by automated
tests). Numbers come only from stored results: [report/evaluation.md](report/evaluation.md),
[model_card_selector.md](model_card_selector.md) and the Part 1 walk-through. All data shown is **synthetic**.

## Before the presentation (once, on the demo laptop)
1. Close other development servers (ports 8000, 5173 and 5174 must be free), then double-click `start-dev.bat`. The
   first run downloads packages (it took about 25 minutes on our connection), so do it the day before.
2. Check that the browser opens the console **signed in to "Demo Fleet (synthetic)"** with three feasible plans.
3. Have the files from `docs/demo_files/` ready (all synthetic): `orders_bad_synthetic.csv`,
   `orders_timewindows_synthetic.xlsx`, `orders_large_tight_synthetic.csv`, `proof_of_delivery_test.png`.
4. Open `docs/report/demo/` in a file viewer: every step below has a screenshot to fall back on.
5. Make a second tenant for the isolation step: `start-dev.bat tenant "Acme Couriers (synthetic test)"` (the key is
   printed once; keep it in a text file outside the repository).

## 0. Overview (60 s)
**Say:** "LogiMind plans delivery routes for a small fleet. A dispatcher imports orders, a solver builds the routes,
and an independent validator checks them before anything is called feasible. Drivers get a link to their own stop
list, and a copilot lets the dispatcher ask in plain words. The one design rule: **the language model never makes
routes.** It only turns a request into a checked command; the solvers are the source of truth, and the validator
has the final word. Everything you will see runs locally and free, and all the data is synthetic."

**Show:** the Overview page (plan counts from the validator's verdicts). [01]

**Examiner:** "Why not let the LLM plan the routes?" **Answer:** "A language model can produce a route that breaks
capacity or a time window and still sound confident. Solvers search the real constraints, and the validator checks
every plan, so an infeasible plan is never shown as a success."

---

## 1. Start and sign-in (1 min) — VERIFIED
**Click:** (already open) the console; point at the "Demo mode" label. Then Account → Sign out → paste the Acme key
→ Sign in.
**Say:** "For the demo, the local server signs us in to a demo company automatically, but only on this computer. A
real customer signs in with an API key; the server stores only a hash of it. Each company only ever sees its own data."
**See:** "Demo mode" label [01]; a wrong key is refused in plain words [02]; Acme signs in with no plans [03].
**Examiner:** "Is demo mode a security hole?" **Answer:** "It is off unless the server is started by `start-dev.bat`
on 127.0.0.1, it answers only requests from this computer, and Docker never turns it on; tests check all of that."
**Fallback:** screenshots 01-03.

## 2. Importing orders (1.5 min) — VERIFIED
**Click:** Plans → Order file → `orders_bad_synthetic.csv`; then `orders_timewindows_synthetic.xlsx`.
**Say:** "Dispatchers live in spreadsheets, so we accept CSV and Excel. Every row is checked, and a bad file imports
nothing, so a typo cannot silently drop a customer."
**See:** "3 of 4 rows have problems" with row, column and reason [04]; then "10 orders ready, synthetic data", and the
depot moves to the middle of the orders with a note [05, 31].
**Examiner:** "What if half the rows are fine?" **Answer:** "We still import nothing and list every problem; a
partial plan that silently misses customers is worse than no plan."
**Fallback:** screenshots 04, 05; or "Use a synthetic sample (12 orders)".

## 3. A plan with engine Auto and the honest distance warning (2 min) — VERIFIED
**Click:** set the depot to 77.5946 / 12.9716, Engine "Auto", Distances "Road network (OSRM)", Create plan.
**Say:** "We have three engines: Google OR-Tools, our own genetic algorithm, and a hybrid. Auto picks one with a
model trained on synthetic cases and explains why. We asked for road distances, but no road server runs here, so
the plan says it fell back to an estimate instead of pretending."
**See:** validator "feasible", engine and "Why this engine" with predicted regret per engine and "outside the
training range"; the black "Fallback distances: not road data" box with its reason [06].
**Examiner:** "Is the Auto picker better than always using one engine?" **Answer:** "Not proven. On the held-out
benchmarks its mean regret was 0.49% against 0.62% for always-hybrid, but always-GA beat it on capacity-only problems
(0.31% vs 0.64%) and always-hybrid beat it at 3 s (0.51% vs 0.56%); no significance test was possible."
**Fallback:** screenshot 06.

## 4. Same orders, three engines (1 min) — VERIFIED
**Click:** Plans → "Use a synthetic sample (12 orders)" → Engine OR-Tools → Create; repeat with GA and Hybrid.
**Say:** "Each engine gets the same orders, the same distances and the same time budget, and the same validator
checks all three. On this small sample all three find 377.99."
**See:** solid blue (OR-Tools), dashed orange (GA), dash-dot (hybrid), all "feasible" [07, 08, 09].
**Examiner:** "So which engine is best?" **Answer:** "It depends on the problem; see the results section. With time
windows OR-Tools won on all 12 held-out instances at 3 s."
**Fallback:** screenshots 07-09.

## 5. Failures are shown as failures (1 min) — VERIFIED
**Click:** Plans → `orders_large_tight_synthetic.csv` → Vehicles 60, Engine OR-Tools, Time budget 0.5 → Create.
**Say:** "600 orders with 15-minute windows and half a second is not enough. The system says 'time limit reached
before any solution'; it never shows an empty or broken plan as a success."
**See:** red "no plan", "timeout" badge, "Time limit reached before any solution" [11]. (Windows that cannot be
reached at all are refused before solving, with every stop listed [10].)
**Examiner:** "What if the solver hangs?" **Answer:** "Every solve runs in a separate process that is killed at
1.5 × budget + 5 s and stored as a hard timeout; a worker that dies is replaced and the job is retried once."
**Fallback:** screenshot 11.

## 6. Replanning after a disruption (3 min) — VERIFIED
Do each replan **from the original plan** (see limitation 7).
**Click:** open the OR-Tools sample plan → Replan → Vehicle breakdown: vehicle 0, 2 stops done → Replan. Back to the
original → Failed delivery: 2 stops done on vehicles 0 and 1, a customer, "Visit again later" → Replan. Back to the
original → Urgent order: 3 stops done on vehicle 0, a new order at 80 / 20 → Replan.
**Say:** "Days do not go to plan. Stops already delivered are frozen, the current plan is the warm start, and the
new plan is validated again. A failed delivery is never retried as the very next stop."
**See:** breakdown: vehicle 0 keeps its 2 finished stops, the rest move, about 3.5 s to a validated plan, "replanned
from …" [12, 13]; failed delivery: the customer comes later in the route [14]; urgent order: inserted, finished stops
kept [15, 16].
**Examiner:** "How fast is a replan, and is it always feasible?" **Answer:** "In our synthetic experiment 96 of 96
replans were feasible with 0 frozen-stop violations; the time to a feasible plan is about the budget you give it,
because the engines use their whole budget."
**Fallback:** screenshots 12-16.
**Confirm / Cancel (copilot replans): NOT VERIFIED.** They need a local model; covered by unit tests only.

## 7. Drivers (2.5 min) — VERIFIED (desktop Chrome, not a phone)
**Click:** Drivers → choose the Excel plan → "Driver link for route 0" → open the link in a new window → Delivered on
stop 1 → Failed → "Nobody home" → Report failed → photo on stop 1 (`proof_of_delivery_test.png`). Then stop the API
window, tap Delivered on the next stop, start the API again.
**Say:** "Each driver gets a signed link to one route, valid for 12 hours, and can be revoked. The app works with a bad
connection: reports wait on the phone and are sent when the server answers. Driver reports never change the plan by
themselves."
**See:** stop list with time windows [18]; reasons [19]; "Photo saved" [20]; "Server unreachable" and "1 update waiting
to sync" [32, 21]; synced by itself after restart [22]; the console's Drivers panel shows every report [23]; a revoked
link says "Link no longer valid" [33].
**Examiner:** "Has it run on a real phone?" **Answer:** "No; we tested it in desktop Chrome only. The Navigate button
opens a maps directions link, which we checked but did not open."
**Fallback:** screenshots 17-23, 32, 33.

## 8. Customer ETA messages (30 s) — VERIFIED (through the API; no console screen)
**Click:** API docs (`/docs`) → Authorize → `GET /api/notifications` → Try it out → Execute.
**Say:** "Customers are only messaged if they opted in. The only sender is a stub that logs; nothing is ever sent,
because a real SMS service costs money."
**See:** `skipped_no_opt_in` for a customer without opt-in, `sent_stub` with a masked number for one who opted in;
ETAs labelled "not live traffic" [26].
**Examiner:** "Are the ETAs live?" **Answer:** "No, they are planned times from the route, not traffic data."
**Fallback:** screenshot 26.

## 9. Copilot (30 s) — no-model message VERIFIED; real answers NOT VERIFIED
**Click:** Copilot.
**Say:** "The copilot uses a free local model through Ollama. Its output is one checked command with no route
fields; replies are built from tool results, and any number no tool produced is blocked. On this laptop no model
is installed, so it says so plainly."
**See:** "No local model is available", input disabled [27].
**Examiner:** "How accurate is it?" **Answer:** "We do not know: it has not been measured with a real model. The
behaviour (clarify, confirm, refuse, no route edits) is tested with a deterministic fake model only."
**Fallback:** screenshot 27. Never claim the copilot answered anything.

## 10. Platform checks (1 min) — VERIFIED
**Click:** API docs page; show `/api/health` (`worker_mode: external`, heartbeat) [24, 25].
**Say:** "It is API-first: the console is just one client. Plans are solved by a separate worker process. Other
systems get signed webhooks; every action is in an audit log; each key is rate-limited; and one company can never see
another's data. Isolation is enforced in the data layer and tested by trying to break it."
**See / tell (from Part 1):** webhook delivered on attempt 1 with a signature header; 20 requests answered, then 429
with `Retry-After`; every cross-tenant request answered 404.
**Examiner:** "How do you know isolation holds?" **Answer:** "Every database query in a tenant session gets the
tenant filter, writes for another tenant are refused, and tests attack it; in the browser each cross-tenant call
returned 404."
**Fallback:** screenshots 24-26.

## 11. Research results (1.5 min) — VERIFIED (pages); numbers from stored runs
**Click:** (if the server runs with `LOGIMIND_DEV_RESEARCH_ENDPOINTS=1`) Research → Compare algorithms; Benchmark lab
[28, 29]. Then open `docs/report/evaluation.md`.
**Say:** "We compared the engines fairly: same instance, same distances, same objective and the same total time. On
24 held-out benchmark instances: with time windows OR-Tools was better than GA + local search on 12 of 12 at 3 s
(median 8.20 percentage points, Holm-adjusted p = 0.0044). On capacity-only problems GA + local search was better
on 10 of 12 at 3 s (median −1.70 pp, p = 0.0479). The hybrid was not significantly different from OR-Tools."
**Examiner:** "Why is the hybrid not better?" **Answer:** "Its 50/50 time split is untuned, and in the stored runs the
GA phase rarely improved the OR-Tools seed; we report that as a negative result."
**Fallback:** screenshots 28-29 and the report's tables. The selector model card is a document
(`docs/model_card_selector.md`), not a console page.

---

## Honest limitations (1 min) — say these out loud
1. **Hybrid:** not significantly better than OR-Tools: all 24 instances at 3 s, better on 10, tie 10, worse 4, median
   0.00 pp, Holm-adjusted p = 0.1920; at 10 s p = 1.0000 (the 10 s run is PARTIAL: 134 of 216 runs).
2. **GA on capacity-only problems:** better at 3 s (10 of 12, p = 0.0479), but not clearly at 10 s (8 better, 2 ties,
   2 worse, p = 0.5273, PARTIAL run).
3. **Time windows:** OR-Tools wins (12 of 12 at 3 s, p = 0.0044; 10 of 12 at 10 s, p = 0.0176).
4. **Selector:** not proven better than always picking the hybrid: on its own synthetic cross-validation it had
   0.52% mean regret against 0.63% for always-hybrid, but in leave-one-size-out always-hybrid was better; on the
   held-out benchmarks it was beaten by always-GA on capacity-only problems and by always-hybrid at 3 s. Trained on
   synthetic data only.
5. **Copilot:** never measured with a real model (no Ollama on our laptops); the 50-instruction evaluation set is
   still a draft.
6. **Untested:** road distances from a self-hosted OSRM (only replayed recordings in tests), Docker Compose and
   PostgreSQL. The straight-line detour factor (1.3) and speed (25 km/h) are uncalibrated guesses.
7. **Found in our own browser test:** a replan forgets earlier disruptions (a vehicle that broke down in one replan can
   get stops again in the next), and the plan page shows no arrival times per stop. Both are listed, not fixed.
8. Driver app not tried on a real phone; ETA messages are never sent (stub only); all data is synthetic, no pilot
   operator data exists.

## If something goes wrong live
- Browser does not open or is not signed in: open `http://localhost:5173/plans`; if it still asks for a key, the
  server was not started by `start-dev.bat` (demo mode off): use the Acme key.
- "The server isn't running": look at the "LogiMind API" window; press Retry in the console after it is up.
- A plan stays "queued": the "LogiMind worker" window is closed; start `start-dev.bat` again.
- `start-dev.bat` says a port is busy: close the program it names (it never closes anything itself).
- Anything else: switch to the screenshots in `docs/report/demo/` and say that you are showing a recorded run.
