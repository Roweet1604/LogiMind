"""The Hugging Face Space folder holds only what the API needs; app.py runs the public demo (decisions 0044, 0045)."""
import ast
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
    assert names == ["README.md", "alembic.ini", "app", "app.py", "migrations", "requirements.txt"]
    assert not (out / "app" / "stale.py").exists()
    files = [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()]
    assert (out / "app" / "main.py").exists() and (out / "app" / "selector" / "data" / "training_cases.csv").exists()
    for f in files:
        assert not re.search(r"(^|/)(tests|experiments|__pycache__)(/|$)|\.pyc$|(^|/)\.env", f), f
    reqs = (out / "requirements.txt").read_text().splitlines()
    assert "fastapi==0.162.2" in reqs and any(r.startswith("ortools==") for r in reqs)
    assert not any(r.startswith(("pytest", "ruff")) for r in reqs)
    # The Space build pins gradio and spaces itself; a second pin made the first build fail (decision 0045).
    assert "gradio" in reqs and "spaces" in reqs


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


def test_space_app_and_readme_match_the_space_settings():
    src = (SPACE / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    first = tree.body[1]  # after the docstring
    assert isinstance(first, ast.Import) and first.names[0].name == "spaces"  # ZeroGPU: import spaces first
    gpu = [f for f in tree.body if isinstance(f, ast.FunctionDef)
           and any("spaces.GPU" in ast.unparse(d) for d in f.decorator_list)]
    assert gpu, "ZeroGPU needs one @spaces.GPU function"
    for setting in ('"LOGIMIND_DEMO_MODE": "1"', '"LOGIMIND_PUBLIC_DEMO": "1"', '"LOGIMIND_WORKER": "inline"',
                    '"ROUTEOPT_DATA_DIR": "/tmp/', '"FRONTEND_URL": "https://logi-mind-ten.vercel.app"'):
        assert setting in src
    assert 'host="0.0.0.0"' in src and '"7860"' in src
    front = (SPACE / "README.md").read_text(encoding="utf-8").split("---")[1]
    for line in ("sdk: gradio", "sdk_version: 6.32.0", "app_file: app.py"):
        assert line in front
