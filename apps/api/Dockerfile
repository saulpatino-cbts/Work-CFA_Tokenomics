# Build from the repository root: docker build -f apps/api/Dockerfile .
# Base images are tag-pinned, not digest-pinned: pin by digest before any marketplace submission
# (docs/marketplace.md).

FROM node:26-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

# CI builds this stage to run the web checks: docker build --target web-test ...
FROM web AS web-test
RUN npm run typecheck && npm test && npm audit --audit-level=high

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src
RUN pip install --no-cache-dir . && useradd --system --uid 10001 app
COPY --from=web /web/dist /app/web
ENV CFA_WEB_DIR=/app/web
USER 10001
EXPOSE 8080
CMD ["uvicorn", "cfa_tokenomics.main:app", "--host", "0.0.0.0", "--port", "8080"]
