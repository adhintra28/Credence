FROM python:3.11-slim

WORKDIR /app

# Runtime deps only (the portal runs from source; no editable install needed).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN rm -rf /root/.cache/pip

COPY . .

EXPOSE 5000 8000

# Web portal (Flask) on $PORT — paas-friendly env; API stays at :8000 via
# `uvicorn src.serving.api:app --host 0.0.0.0 --port 8000`.
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} frontend.app:app"]
