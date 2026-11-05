# 0019: Road matrix (P4): providers, cache, flagged fallback, travel times

Date: 5 Nov 2026 (unattended session). Status: built and tested offline; **not yet run against a self-hosted OSRM** (Docker is not installed, see PROGRESS.md).

## What was built
- `backend/app/distances/`: `DistanceProvider` interface, `RoadMatrix` (km + seconds + provenance), `HaversineProvider` (straight line x detour factor at an assumed speed), `OsrmProvider` (table service), `MatrixCache` (SQLite file `matrix_cache.sqlite` in the data dir), `DistanceService` (choice of source, size limit, fallback).
- `POST /api/plans` takes `distance_source`: `straight_line` (default, behaviour unchanged), `osrm`, or `estimate`. Lon/lat instances only (422 otherwise).
- The matrix is built **before** the solver starts and is stored with the plan's instance. Every engine, the validator, the metrics and the ETAs use the same matrix, and building it is not charged to any engine's budget (invariant 4).
- The plan, the plan list, the ETA response and the audit row carry `distance_source` (provider, requested, fallback, reason, label, URL, fetch time, cache hit). The console shows it on the plan page, as a warning when it is a fallback.

## Decisions
- **Travel times:** with a road matrix, travel time = the matrix's duration converted to the instance's `time_unit`; `time_per_distance` is not used (the ETA response then shows it as `null`). Without one, nothing changes (distance x time_per_distance).
- **Fallback:** if `osrm` is requested and OSRM is not configured (`LOGIMIND_OSRM_URL` unset), not reachable, answers with an error, or cannot route a pair, the plan gets the straight-line estimate with `fallback: true` and the reason (invariant 10). It is **not** refused, because a dispatcher still needs a plan; it is never presented as road data. Fallbacks are never cached.
- **Assumptions (configurable, labelled on every plan that uses them):** detour factor 1.3 (`LOGIMIND_DETOUR_FACTOR`) and average speed 25 km/h (`LOGIMIND_FALLBACK_SPEED_KMH`). These are round planning assumptions, NOT measured for Bengaluru. They should be checked against real OSRM answers once OSRM runs (P10). For reference only (30 ordered pairs of the 6 recorded synthetic points, measured 5 Nov 2026): OSRM road distance / straight line = 1.16 to 1.66, median 1.30; OSRM's implied speed = 36.6 to 52.9 km/h, median 47.4. Too few points to calibrate anything.
- **OSRM travel times are free-flow** (the car profile has no traffic), so in a city like Bengaluru they are likely optimistic; the 47 km/h median above is far above typical city traffic speeds. Plans and ETAs say "not live traffic". Calibrating or scaling OSRM durations is left for P10 and is not done here.
- **Batching and limits:** OSRM limits locations per table request (`--max-table-size`, default 100). Up to that limit one request; above it, chunks of `max_table // 2` and one request per ordered chunk pair. The plan matrix is limited to `LOGIMIND_MATRIX_MAX_NODES` = 250 distinct points (the matrix is stored as JSON with the plan; 250 points is about 1 MB). Larger requests get 422.
- **Cache:** key = SHA-256 of (provider, server URL, profile, rounded points); whole matrices only; entries older than 30 days (`LOGIMIND_MATRIX_CACHE_DAYS`) are fetched again. Known limit: no pair-level reuse, so an urgent order re-requests the whole matrix (one request up to 100 points).
- **Identity:** an instance with a road matrix gets a different `instance_id` (the matrix digest is part of it); ids of instances without one are unchanged (tested).
- **Urgent order replans** rebuild the matrix for all points from the same requested source. If OSRM is down then, the whole replan matrix is the fallback, the plan says so, and the replan notes say that the distances changed.
- **Asymmetry:** road matrices are not symmetric (one-way streets). OR-Tools, the GA (split and local search evaluate whole routes) and the validator all index [from][to], so this is safe.

## Recorded fixture (tests run offline)
- `backend/tests/fixtures/osrm/bengaluru_6_points.json`: 11 **real** OSRM table answers for **6 synthetic points** in Bengaluru (no customer data): 9 batched requests (max_table 4), 1 single request for all 6 points, 1 for the first 5.
- Recorded once on **5 Nov 2026 (05:5x UTC)** from the public OSRM demo server `https://router.project-osrm.org` with `experiments/osrm/record_fixture.py` (1.1 s between requests, identifying User-Agent). Routing data (c) OpenStreetMap contributors, ODbL.
- Why the demo server: it was the only OSRM available (no Docker here), and a real recording is more honest than hand-made numbers. The demo server is not for production; **the product never uses it** (no default URL; `LOGIMIND_OSRM_URL` must point at a self-hosted server). The same script re-records from a self-hosted server.
- The tests check that the batched matrix equals the single-request matrix exactly, that units are converted (m to km, s to the instance unit), that unrecorded requests fail loudly, and the fallbacks (server down, unroutable pair, error answer).
