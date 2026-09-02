FROM node:24-slim AS web
WORKDIR /app/web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.14-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.9.13 \
    && uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt
COPY src/ src/
COPY migrations/ migrations/
COPY --from=web /app/web/dist web/dist
RUN pip install --no-cache-dir --no-deps .
RUN playwright install --with-deps chromium
ENV DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "meta_workers.main:app", "--host", "0.0.0.0", "--port", "8000"]
