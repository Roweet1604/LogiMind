"""The Hugging Face Space folder holds only what the API needs, and the image runs the public demo (decision 0044)."""
import importlib.util
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SPACE = BACKEND.parent / "hf-space"
_spec = importlib.util.spec_from_file_location("build_hf_space", BACKEND / "scripts" / "build_hf_space.py")
build_hf_space = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_hf_space)


def test_space_folder_contains_only_the_runtime(tmp_path):
    out = tmp_path / "space"
    (out / "app").mkdir(parents=True)
    (out / "app" / "stale.py").write_text("x = 1\n")  # left from an earlier build: must disappear
    names = build_hf_space.build(out)
    assert names == [".dockerignore", "Dockerfile", "README.md", "alembic.ini", "app", "migrations",
                     "requirements.txt"]
    assert not (out / "app" / "stale.py").exists()
    files = [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()]
    assert (out / "app" / "main.py").exists() and (out / "app" / "selector" / "data" / "training_cases.csv").exists()
    for f in files:
        assert not re.search(r"(^|/)(tests|experiments|__pycache__)(/|$)|\.pyc$|(^|/)\.env", f), f
    reqs = (out / "requirements.txt").read_text()
    assert "fastapi==" in reqs and "ortools==" in reqs
    assert "pytest" not in reqs and "ruff" not in reqs


def test_build_refuses_a_dotenv_in_the_folder(tmp_path):
    out = tmp_path / "space"
    out.mkdir()
    (out / ".env").write_text("SECRET=x\n")
    try:
        build_hf_space.build(out)
    except SystemExit as e:
        assert ".env" in str(e)
    else:
        raise AssertionError("a .env file in the Space folder must stop the build")


def test_dockerfile_and_readme_match_the_space_settings():
    docker = (SPACE / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]' in docker
    assert "USER user" in docker and "--uid 1000" in docker
    for setting in ("LOGIMIND_DEMO_MODE=1", "LOGIMIND_PUBLIC_DEMO=1", "LOGIMIND_WORKER=inline",
                    "FRONTEND_URL=https://logi-mind-ten.vercel.app"):
        assert setting in docker
    assert "LOGIMIND_DATABASE_URL" not in docker  # SQLite in the data dir only
    front = (SPACE / "README.md").read_text(encoding="utf-8").split("---")[1]
    assert "sdk: docker" in front and "app_port: 7860" in front
    assert ".env" in (SPACE / ".dockerignore").read_text()
