# 0020: Docker Compose files, written but UNTESTED

Date: 5 Nov 2026 (unattended session)

## Situation
`docker --version` fails on Rohit's laptop: `docker` is not on the PATH, and `C:\Program Files\Docker\Docker\resources\bin\docker.exe` does not exist (checked 5 Nov 2026). Installing system software was not allowed in this session. As instructed, the Compose files were written and are marked **UNTESTED** everywhere (file headers, README).

## What was written
- `docker-compose.yml`: `postgres` (16-alpine, healthcheck, volume), `api` (built from `backend/Dockerfile`, Python 3.12-slim, one uvicorn worker, data volume `/data`), `console` and `driver` (Node 20 build, served by nginx 1.27 with `/api` proxied to `api`), and an optional profile `osrm` with `osrm-prepare` (extract / partition / customize, MLD) and `osrm` (`osrm-routed --max-table-size 100`), image `ghcr.io/project-osrm/osrm-backend:v5.27.1`.
- `backend/requirements-docker.txt` adds `psycopg[binary]` (PostgreSQL driver, free and open source) for the image only, so local installs are unchanged.
- `.env.example` with empty `POSTGRES_PASSWORD` and `LOGIMIND_DRIVER_LINK_SECRET` (Compose refuses to start without them; no real or default secrets anywhere).
- Checked here: the YAML parses, and every `${VAR}` in the Compose file is listed in `.env.example`. Nothing else was checked.

## Decisions
- **Superseded by decision 0021 (5 Nov 2026): Compose now has a `worker` service.** Original note: **No separate worker service.** Plans run on the API process's single solver thread and its guarded worker process (decision 0006). A separate worker container would need a shared job queue (the remaining P6 item), and an empty "worker" service would only pretend. So the API container must run exactly one uvicorn worker (the rate limiter and the copilot sessions are also in-process).
- **Ollama stays on the host** (`host.docker.internal`), because model files are large and GPU or CPU access differs per laptop.
- **OSRM extract not downloaded.** The task allowed a small city extract (about 150 MB or less) from an official free source. Geofabrik publishes no Bengaluru or Karnataka file; its smallest file containing Bengaluru is `asia/india/southern-zone-latest.osm.pbf`, **559,229,243 bytes**, Last-Modified 4 Nov 2026 (HTTP HEAD, 5 Nov 2026). BBBike has no `Bangalore` extract at `https://download.bbbike.org/osm/bbbike/Bangalore/Bangalore.osm.pbf` (HTTP 404). Without Docker the file could not be preprocessed anyway. Options for the team (blocker, team decision): (a) download the 559 MB southern zone and cut a Bengaluru bounding box with osmium-tool (free) into a small file; (b) use the whole southern zone (several GB of RAM to preprocess); (c) the BBBike custom-extract service. Whatever is used, record the URL, date and SHA-256.

## Known risks to check when Docker is available
- Alembic migrations have only run on SQLite (migration 0003 uses `batch_alter_table`, which Alembic turns into plain ALTERs on PostgreSQL).
- The OSRM image tag `v5.27.1` and the `/opt/car.lua` profile path were taken from OSRM's documentation, not tried.
- OR-Tools and the other wheels on Python 3.12-slim (the laptop uses 3.14).
- The driver PWA needs HTTPS to install on a phone; Compose serves plain HTTP on localhost only.
