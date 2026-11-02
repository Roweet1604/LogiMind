"""Download public benchmark instances and best-known solutions from CVRPLIB.

Usage (from the repository root; needs internet, no other dependencies):
    python experiments/benchmarks/fetch_benchmarks.py                 # Solomon (56), Set A (27), 10 smallest of Set X
    python experiments/benchmarks/fetch_benchmarks.py --sets homberger --limit 5

Writes (git-ignored):  experiments/benchmarks/data/<set>/<name>.{txt|vrp,sol}
                       experiments/benchmarks/data/manifest.json   (URL, SHA-256, date per file)
Rewrites (committed):  experiments/benchmarks/bks.csv               (best-known costs with provenance)

Source: CVRPLIB, https://galgos.inf.puc-rio.br/cvrplib/ . Instances are provided
for research use; see experiments/benchmarks/SOURCES.md before redistributing.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://galgos.inf.puc-rio.br/cvrplib/index.php/en"
INDEX_URL = f"{BASE}/instances"
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
USER_AGENT = "LogiMind-capstone-benchmark-fetch/1.0 (academic project)"

# Page heading "Set <label>" -> our folder / set key, and the file extension.
SET_KEYS = {"Solomon": ("solomon", ".txt"), "Homberger": ("homberger", ".txt"),
            "A": ("A", ".vrp"), "B": ("B", ".vrp"), "P": ("P", ".vrp"), "X": ("X", ".vrp")}
DEFAULT_SETS = ["solomon", "A", "X"]
DEFAULT_LIMITS = {"X": 10}  # the 10 smallest X instances; others: whole set


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def parse_index(page: str) -> list[dict]:
    """Rows of the CVRPLIB instance table with their set and download ids."""
    out, current = [], None
    for row in re.findall(r"<tr.*?</tr>", page, re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", c))).strip()
                 for c in re.findall(r"<td.*?</td>", row, re.S)]
        if "download/instance-set/" in row:
            m = re.search(r"Set (\S+)", cells[0] if cells else "")
            label = m.group(1) if m else ""
            info = re.sub(r'">$', "", cells[1]) if len(cells) > 1 else ""
            current = {"label": label, "problem": cells[0].split()[0] if cells else "", "info": info}
            continue
        inst = re.search(r"download/instance/(\d+)", row)
        bks = re.search(r"download/bks/(\d+)", row)
        if current and inst and cells:
            n = re.sub(r"[^\d]", "", cells[1]) if len(cells) > 1 else ""
            out.append({"name": cells[0], "set_label": current["label"], "problem": current["problem"],
                        "set_info": current["info"], "n": int(n) if n else None,
                        "instance_id": inst.group(1), "bks_id": bks.group(1) if bks else None})
    return out


def conventions(set_info: str) -> tuple[str, str]:
    dist = re.search(r"Distance: (.*?)(Solution Cost:|Objective:|$)", set_info)
    routes = re.search(r"Number of Routes: (.*)$", set_info)
    return (dist.group(1).strip() if dist else ""), (routes.group(1).strip() if routes else "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", nargs="+", default=DEFAULT_SETS, choices=[k for k, _ in SET_KEYS.values()])
    ap.add_argument("--limit", type=int, default=None, help="max instances per set (smallest first)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between requests")
    args = ap.parse_args(argv)

    today = dt.date.today().isoformat()
    print(f"Reading index {INDEX_URL}")
    rows = parse_index(get(INDEX_URL).decode("utf-8", "replace"))
    manifest_path = DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    for label, (key, ext) in SET_KEYS.items():
        if key not in args.sets:
            continue
        chosen = sorted((r for r in rows if r["set_label"] == label), key=lambda r: (r["n"] or 0, r["name"]))
        limit = args.limit if args.limit is not None else DEFAULT_LIMITS.get(key)
        chosen = chosen[:limit] if limit else chosen
        print(f"Set {key}: {len(chosen)} instances")
        folder = DATA / key
        folder.mkdir(parents=True, exist_ok=True)
        for r in chosen:
            for kind, rid, suffix in (("instance", r["instance_id"], ext), ("bks", r["bks_id"], ".sol")):
                if rid is None:
                    continue
                url = f"{BASE}/download/{kind}/{rid}"
                body = get(url)
                path = folder / f"{r['name']}{suffix}"
                path.write_bytes(body)
                manifest[f"{key}/{path.name}"] = {"url": url, "sha256": hashlib.sha256(body).hexdigest(),
                                                   "retrieved_on": today, "set_info": r["set_info"],
                                                   "n_customers": r["n"], "problem": r["problem"]}
                time.sleep(args.delay)
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    write_bks(manifest)
    return 0


def write_bks(manifest: dict) -> None:
    out = []
    for rel, meta in sorted(manifest.items()):
        if not rel.endswith(".sol"):
            continue
        key, fname = rel.split("/", 1)
        sol = (DATA / rel).read_text(encoding="utf-8", errors="replace")
        cost = re.search(r"^\s*Cost\s+([\d.]+)", sol, re.M | re.I)
        n_routes = len(re.findall(r"^\s*Route\s*#", sol, re.M | re.I))
        dist, routes_rule = conventions(meta["set_info"])
        out.append({"instance": fname[:-4], "set": key, "problem": meta["problem"],
                    "n_customers": meta["n_customers"], "bks_cost": cost.group(1) if cost else "",
                    "bks_routes": n_routes, "distance_convention": dist, "routes_rule": routes_rule,
                    "source_url": meta["url"], "retrieved_on": meta["retrieved_on"]})
    path = HERE / "bks.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]) if out else ["instance"], lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {len(out)} best-known solutions to {path}")


if __name__ == "__main__":
    sys.exit(main())
