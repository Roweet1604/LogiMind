"""Fill the Hugging Face Space folder with what the API needs to run (decisions 0044, 0045).

    python backend/scripts/build_hf_space.py                     # into hf-space/ (copies git-ignored there)
    python backend/scripts/build_hf_space.py --out <folder>   # elsewhere; also copies README.md and app.py

Copies backend/app, backend/migrations, backend/alembic.ini and requirements.txt without the test and lint tools,
plus gradio and spaces (the Space uses the Gradio SDK with ZeroGPU; decision 0045). Upload the folder with
    hf.exe upload Rohti/logimind hf-space . --repo-type=space
Never copies tests, .env files, caches, experiments or results; stops if a .env file would end up in the folder.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SPACE = BACKEND.parent / "hf-space"
SPACE_FILES = ("README.md", "app.py")  # kept in hf-space/ itself
COPIED = ("app", "migrations", "alembic.ini", "requirements.txt")  # generated; replaced on every run
DEV_ONLY = ("pytest", "ruff")  # not needed to run the API
# Listed WITHOUT versions: the Gradio SDK build installs gradio==<sdk_version in README.md> and its own spaces pin
# in the same pip call, and a second pin conflicts (first Space build: spaces==0.51.3 vs 0.52.0).
SPACE_EXTRA = ("gradio", "spaces")
# Our pins that the Space's gradio[oauth,mcp]==6.32.0 does not allow, replaced for the Space only (second build:
# gradio[mcp] needs pydantic>=2.11.10,<=2.12.5). Checked with `uv pip compile` for Python 3.12 on Linux, together with
# the Space's own pins; the backend suite passes with them (decision 0045).
SPACE_OVERRIDES = {"pydantic": "pydantic==2.12.5"}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".ruff_cache", ".env", ".env.*")


def runtime_requirements(text: str) -> str:
    keep = []
    for line in text.splitlines():
        name = line.split("==")[0].strip().lower()
        if name not in DEV_ONLY:
            keep.append(SPACE_OVERRIDES.get(name, line))
    return "\n".join(keep + ["# Hugging Face Space (Gradio SDK + ZeroGPU, decision 0045)", *SPACE_EXTRA]) + "\n"


def build(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    for name in COPIED:  # remove the previous copy so deleted backend files do not linger
        target = out / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    if out.resolve() != SPACE.resolve():
        for name in SPACE_FILES:
            shutil.copy2(SPACE / name, out / name)
    shutil.copytree(BACKEND / "app", out / "app", ignore=IGNORE)
    shutil.copytree(BACKEND / "migrations", out / "migrations", ignore=IGNORE)
    shutil.copy2(BACKEND / "alembic.ini", out / "alembic.ini")
    (out / "requirements.txt").write_text(
        runtime_requirements((BACKEND / "requirements.txt").read_text(encoding="utf-8")), encoding="utf-8")
    leaked = [p for p in out.rglob(".env*") if ".git" not in p.parts]
    if leaked:
        raise SystemExit(f"refusing: .env files in {out}: {[str(p) for p in leaked]}")
    return sorted(p.relative_to(out).as_posix() for p in out.iterdir() if p.name != ".git")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=SPACE, help="folder to fill (default: hf-space/)")
    args = ap.parse_args(argv)
    names = build(args.out)
    print(f"{args.out}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
