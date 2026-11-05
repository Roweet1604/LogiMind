# LogiMind API image. UNTESTED (no Docker on the development laptop; decision 0020).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt
COPY . .
RUN useradd --create-home logimind && mkdir -p /data && chown logimind /data
USER logimind
EXPOSE 8000
# One uvicorn worker on purpose: solver jobs, the rate limiter and copilot sessions live in this process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
