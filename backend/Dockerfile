FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
RUN useradd --system --uid 10001 --create-home --home-dir /home/riskforge --shell /usr/sbin/nologin riskforge
USER riskforge
# API default; Compose ``worker`` overrides with: python -m app.worker
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
