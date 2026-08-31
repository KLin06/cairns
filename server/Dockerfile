FROM python:3.11-slim

# WORKDIR must be exactly one level deep (/srv) so that app/config.py's
# REPO_ROOT (two dirname() calls up from server/app/config.py) resolves to
# "/" inside the container, matching the data/datasets bind mount path in
# docker-compose.yml at /data/datasets - this keeps config.py's path
# derivation unchanged rather than special-casing it for containers.
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY db ./db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
