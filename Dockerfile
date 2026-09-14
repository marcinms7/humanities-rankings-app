FROM node:24.13.0-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY manage.py ./
COPY templates/ ./templates/
COPY research/ ./research/
COPY scripts/container_start.sh ./scripts/container_start.sh
COPY --from=frontend /build/backend/static/app ./backend/static/app
RUN python manage.py collectstatic --noinput && useradd --create-home humanities && mkdir -p /app/data /app/media && chown -R humanities:humanities /app && chmod +x scripts/container_start.sh
USER humanities
EXPOSE 8000
CMD ["./scripts/container_start.sh"]
