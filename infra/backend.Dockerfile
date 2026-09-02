FROM python:3.14-slim
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install --no-cache-dir uv==0.9.13 \
    && uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/src/ src/
COPY backend/migrations/ migrations/
RUN pip install --no-cache-dir --no-deps .
RUN playwright install --with-deps chromium
ENV DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "meta_workers.main:app", "--host", "0.0.0.0", "--port", "8000"]
