# Benchmark sources, licence and conversion

## Source
All instances and best-known solutions (BKS) come from **CVRPLIB**, https://galgos.inf.puc-rio.br/cvrplib/ (instance index: https://galgos.inf.puc-rio.br/cvrplib/index.php/en/instances). Retrieved on 2 Nov 2026 with `fetch_benchmarks.py`. `bks.csv` records, per instance, the exact download URL of the solution file and the retrieval date. `data/manifest.json` (local only) also records the SHA-256 of every downloaded file.

| Set | Problem | Original authors | Downloaded |
| --- | --- | --- | --- |
| Solomon | VRPTW, 100 customers | Solomon (1987) | all 56 |
| A | CVRP, 31 to 79 customers | Augerat et al. (1995) | all 27 |
| X | CVRP, 100 to 1000 customers | Uchoa et al. (2017) | the 10 smallest (100 to 142 customers) |
| Homberger (Gehring-Homberger) | VRPTW, 200 to 1000 customers | Homberger et al. (2005) | not yet (`--sets homberger --limit N`); same file format as Solomon, same parser |

## Licence and redistribution
CVRPLIB's terms of use say its instances and datasets "are provided for research use" and that redistribution may be subject to further terms. So this repository does **not** store the instance or solution files. Every teammate downloads them with the script (`data/` is git-ignored). Only `bks.csv` (published numbers with their source) is committed. Cite the original authors of each set in the report.

## Conversion (CVRPLIB conventions, applied by `backend/app/benchmarks/`)
- **Solomon / Homberger:** metric `euclidean_trunc1` (Euclidean distance truncated to one decimal), travel time = distance, objective = total distance (fixed vehicle cost 0), at most the vehicle number in the file. Service must start within [ready, due]; routes leave at the depot's ready time and must return by its due time.
- **A (and B, P):** metric `euclidean_nint` (TSPLIB EUC_2D, rounded to the nearest integer); objective = total distance; number of routes fixed to the k in the name.
- **X:** like A, but the number of routes is free, so the fleet limit is set to one vehicle per customer.
- Customers are renumbered 1..n in file order without the depot, which is the numbering CVRPLIB's `.sol` files use.

## Check
`backend/tests/test_benchmarks.py` loads every downloaded instance and its BKS routes. It requires each BKS to pass our independent validator and requires our recomputed distance to equal the published cost. On 2 Nov 2026, all 93 passed with a difference of 0.0.

Note: CVRPLIB's VRPTW BKS minimise total distance. Older literature (and the SINTEF tables) first minimise the number of vehicles, then distance. Our gaps use CVRPLIB's distance-only values; say so when quoting them.
