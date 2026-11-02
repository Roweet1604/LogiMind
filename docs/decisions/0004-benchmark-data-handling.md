# 0004: Benchmark data is downloaded, not committed

Date: 2 Nov 2026. Status: accepted (P1).

## Decision
- Instances and BKS solution files are downloaded from CVRPLIB by `experiments/benchmarks/fetch_benchmarks.py` into the git-ignored `experiments/benchmarks/data/`, with URL, SHA-256 and date in `data/manifest.json`.
- Only `experiments/benchmarks/bks.csv` (instance, set, cost, routes, conventions, source URL, retrieval date) and `SOURCES.md` are committed.
- Default download: all Solomon, all Set A, the 10 smallest Set X instances. Gehring-Homberger is supported by the same parser but not downloaded yet ("if time allows" in the plan).
- Unit tests use small made-up files in the official formats, so the suite runs offline. Tests that need the real files skip when they are absent.
- SINTEF's VRPTW pages refused automated access (HTTP 403), so CVRPLIB is the single source.

## Why
CVRPLIB provides its data "for research use" and warns that redistribution may carry extra terms. Downloading on demand respects that and keeps the repository small, while the committed BKS table keeps every quoted value traceable.
