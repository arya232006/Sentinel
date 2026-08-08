# Backend: FastAPI + the LangGraph audit engine, and the target harness it
# attacks. One process, one worker - see the CMD note at the bottom.
FROM python:3.12-slim

# chromadb drags in onnxruntime and numpy. Wheels exist for linux/amd64 on 3.12,
# but the toolchain has to be here in case pip falls back to a source build, and
# curl is what HEALTHCHECK uses.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer on its own, keyed only on pyproject.toml, so editing a node
# does not reinstall chromadb and torch-sized transitive deps on every build.
# The stub package is enough for an editable install to resolve; the real source
# lands in the next layer and overwrites it.
COPY pyproject.toml ./
RUN mkdir -p sentinel && touch sentinel/__init__.py \
    && pip install --no-cache-dir -e .

COPY sentinel/ ./sentinel/
COPY scripts/ ./scripts/

# Runtime state (SQLite, checkpoints, the Chroma store) goes to a mounted
# volume, not into the container's writable layer where a redeploy would drop it.
RUN useradd --create-home --uid 10001 sentinel \
    && mkdir -p /data \
    && chown -R sentinel:sentinel /data /app
USER sentinel

ENV SENTINEL_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# /healthz, not /health: a probe should not need the API token, and should not
# be handed model ids and budget caps either.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# --workers 1 is load-bearing and must not be raised. Live runs are held in a
# per-process dict (sentinel/api/events.py), each one occupying a thread parked
# on a threading.Event until POST /runs/{id}/resume releases it, and every SSE
# subscriber reads a queue owned by that same process. A second worker would own
# a disjoint set of runs, so a resume or an event stream would routinely arrive
# at a process that has never heard of the run. Scaling this service out means
# moving run state to a shared store first.
CMD ["uvicorn", "sentinel.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-keep-alive", "75"]
