# LogiMind API on a Hugging Face Space (Docker SDK, free CPU; decision 0044). Public demo with SYNTHETIC data only.
# Build context = this folder after `python backend/scripts/build_hf_space.py` has copied the backend into it.
# SQLite on the container disk: it starts empty on every restart and the demo tenant is seeded again at start-up.
FROM python:3.14.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Spaces run the container as UID 1000; the app and its data directory belong to that user.
RUN useradd --create-home --uid 1000 user && mkdir -p /home/user/data && chown user /home/user/data
WORKDIR /home/user/app

COPY --chown=user requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user alembic.ini ./
COPY --chown=user migrations ./migrations
COPY --chown=user app ./app

USER user
# Defaults for the public demo; Space "Variables" with the same names override them (FRONTEND_URL in particular).
ENV HOME=/home/user \
    LOGIMIND_DEMO_MODE=1 \
    LOGIMIND_PUBLIC_DEMO=1 \
    LOGIMIND_WORKER=inline \
    ROUTEOPT_DATA_DIR=/home/user/data \
    FRONTEND_URL=https://logi-mind-ten.vercel.app

EXPOSE 7860
# One uvicorn worker on purpose: solver jobs, the rate limiter and copilot sessions live in this process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
