FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
WORKDIR /app
COPY requirements-worker.lock /app/requirements-worker.lock
RUN pip install --no-cache-dir -r requirements-worker.lock
COPY src /app/src
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini
COPY prompts /app/prompts
COPY evals /app/evals
COPY apps/web/dist /app/apps/web/dist
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
