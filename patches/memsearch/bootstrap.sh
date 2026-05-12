#!/usr/bin/env bash
# Per-machine memsearch bootstrap. Idempotent. Run once per machine after
# dotagents install. Requires: docker (running), uv.
#
#   1. Install the memsearch python pkg (`uv tool install`) so apply.sh
#      can flush-patch its MilvusStore.upsert (see patches/memsearch/apply.sh).
#   2. Write ~/.memsearch/standalone/docker-compose.yml with relative
#      volume paths (sudo-safe; no env-var indirection).
#   3. Start the Milvus standalone stack (etcd + Milvus).
#
# Not committed to dotagents settings.json because the compose file is a
# bootstrap-once recipe — see commit 5480888.
set -euo pipefail

STANDALONE_DIR="$HOME/.memsearch/standalone"
COMPOSE_FILE="$STANDALONE_DIR/docker-compose.yml"

# --- (1) memsearch python pkg ---
if ! command -v uv >/dev/null 2>&1; then
  echo "[memsearch-bootstrap] uv not found — install from https://docs.astral.sh/uv/ first" >&2
  exit 1
fi

if ! uv tool list 2>/dev/null | grep -q '^memsearch '; then
  echo "[memsearch-bootstrap] installing memsearch via uv..."
  uv tool install memsearch
else
  echo "[memsearch-bootstrap] memsearch already installed via uv"
fi

# --- (2) Milvus standalone compose ---
mkdir -p "$STANDALONE_DIR/etcd" "$STANDALONE_DIR/milvus"

if [ ! -f "$COMPOSE_FILE" ]; then
  cat >"$COMPOSE_FILE" <<'YAML'
services:
  etcd:
    container_name: milvus-etcd
    image: quay.io/coreos/etcd:v3.5.25
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
      ETCD_SNAPSHOT_COUNT: "50000"
    volumes:
      - ./etcd:/etcd
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  standalone:
    container_name: milvus-standalone
    image: milvusdb/milvus:v2.6.15
    command: ["milvus", "run", "standalone"]
    security_opt:
      - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      COMMON_STORAGETYPE: local
      MQ_TYPE: rocksmq
    volumes:
      - ./milvus:/var/lib/milvus
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - etcd
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 3
    restart: unless-stopped
YAML
  echo "[memsearch-bootstrap] wrote $COMPOSE_FILE"
else
  echo "[memsearch-bootstrap] $COMPOSE_FILE already exists"
fi

# --- (3) Bring up the stack ---
if ! docker info >/dev/null 2>&1; then
  echo "[memsearch-bootstrap] docker daemon not running — start Docker and re-run" >&2
  exit 1
fi

if [ "$(docker ps -q -f name=milvus-standalone)" = "" ]; then
  echo "[memsearch-bootstrap] starting Milvus stack..."
  (cd "$STANDALONE_DIR" && docker compose up -d)
else
  echo "[memsearch-bootstrap] Milvus already running"
fi

echo "[memsearch-bootstrap] done. Restart Claude Code to apply hook patches."
