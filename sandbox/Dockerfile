FROM python:3.14-slim

RUN useradd --create-home --uid 10001 worker
RUN mkdir /workspace && chown worker:worker /workspace
USER worker
WORKDIR /workspace
CMD ["sleep", "infinity"]
