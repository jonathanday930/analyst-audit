# syntax=docker/dockerfile:1
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
COPY backend/pyproject.toml ./
COPY backend/src ./src
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
RUN pip install --no-cache-dir .
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
