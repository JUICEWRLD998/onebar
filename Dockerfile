# Stage 1: build the web UI. `npm run data` turns eval/TABLE.md into src/data/eval.json (not committed).
FROM node:22-slim AS web
WORKDIR /src
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci
COPY web web
COPY eval eval
RUN cd web && npm run data && npm run build

# Stage 2: API + worker + email poller + embedded Temporal dev server in one container.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*
# Temporal CLI (linux amd64), used as the SQLite-backed dev server. See DECISIONS.md "Temporal target".
RUN curl -fsSL "https://temporal.download/cli/archive/latest?platform=linux&arch=amd64" -o /tmp/t.tgz \
    && tar -xzf /tmp/t.tgz -C /usr/local/bin temporal && rm /tmp/t.tgz && temporal --version
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY onebar onebar
COPY eval eval
RUN pip install --no-cache-dir ".[model,temporal,web]"
COPY --from=web /src/web/dist web/dist
COPY data/spend.json seed/spend.json
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/start.sh"]
