"""LogiMind API on a Hugging Face Space with the Gradio SDK and ZeroGPU hardware (decision 0045).

The Space runs `python app.py` and expects a web server on port 7860. This starts the LogiMind FastAPI app there with
uvicorn (one process, inline worker). No Gradio UI is used. ZeroGPU only starts a Space that imports `spaces` and
defines at least one @spaces.GPU function, so a trivial one is defined; the solvers never use a GPU (CPU only).

Public demo with SYNTHETIC data only: SQLite in /tmp (empty after every restart), demo tenant seeded at start-up.
"""
import spaces  # noqa: I001  (ZeroGPU wants `spaces` imported before anything else)

import os
from pathlib import Path

# Settings for the public demo; Space variables with the same names win.
DEFAULTS = {
    "LOGIMIND_DEMO_MODE": "1",
    "LOGIMIND_PUBLIC_DEMO": "1",
    "LOGIMIND_WORKER": "inline",
    "ROUTEOPT_DATA_DIR": "/tmp/logimind-data",
    "FRONTEND_URL": "https://logi-mind-ten.vercel.app",
}
for name, value in DEFAULTS.items():
    if not os.environ.get(name):
        os.environ[name] = value
os.environ.pop("LOGIMIND_DATABASE_URL", None)  # SQLite in the data directory, never another database here
Path(os.environ["ROUTEOPT_DATA_DIR"]).mkdir(parents=True, exist_ok=True)


@spaces.GPU(duration=1)
def zero_gpu_placeholder() -> str:
    """Never called by LogiMind; it exists only so ZeroGPU accepts the Space."""
    return "ok"


def report_zero_gpu_startup() -> None:
    """Tell ZeroGPU that start-up is done. `spaces` does this in a hook on gradio's Blocks.launch(), which this app
    never calls (uvicorn serves FastAPI directly); without it the Space stops with "No @spaces.GPU function detected
    during startup" (third build, 13 Nov 2026). Same steps as spaces 0.51.3's hook (spaces/zero/__init__.py: pack,
    then the startup report when a @spaces.GPU function exists). Does nothing off ZeroGPU (e.g. locally)."""
    from spaces.config import Config
    if not Config.zero_gpu:
        print("ZeroGPU not active here: no startup report needed", flush=True)
        return
    from spaces.zero import client, decorator
    from spaces.zero import torch as zero_torch
    zero_torch.pack()  # no CUDA tensors here: returns 0
    if not decorator.decorated_cache:
        raise RuntimeError("no @spaces.GPU function registered")
    client.startup_report()
    print("ZeroGPU startup report sent", flush=True)


if __name__ == "__main__":
    import uvicorn
    from app.main import app  # creates the database, seeds the demo tenant, starts the inline worker

    report_zero_gpu_startup()

    # One worker on purpose: solver jobs, the rate limiter and copilot sessions live in this process.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")), workers=1, proxy_headers=True)
