# Multi-stage: the app is installed once into a venv (`build`), the unit tests
# run against that exact venv (`test`), and the runtime ships only that venv —
# no pytest, no build tools. Runtime stays zero-dependency on purpose (stdlib
# HTTP server + sqlite3): the only package installed is the application itself.

FROM python:3.12-slim AS build

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir .

FROM build AS test

COPY tests ./tests
COPY data ./data
# pytest lands only in this stage's copy of the venv; runtime copies /opt/venv from `build`.
RUN /opt/venv/bin/pip install --no-cache-dir pytest \
    && /opt/venv/bin/python -m pytest tests -q -p no:cacheprovider \
    && touch /tests-passed

FROM python:3.12-slim AS runtime

# Non-root: the operator API never needs elevated privileges.
RUN useradd --create-home --uid 10001 desk && mkdir /data && chown desk /data
WORKDIR /app

# Building the runtime image requires the test stage to have passed.
COPY --from=test /tests-passed /tests-passed
COPY --from=build /opt/venv /opt/venv
COPY data ./data

# Container defaults; every value stays env-overridable (config.py, README).
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SUPPORT_DESK_HOST=0.0.0.0 \
    SUPPORT_DESK_PORT=8000 \
    SUPPORT_DESK_DB=/data/decisions.db \
    OLLAMA_MODEL=llama3.2:1b
VOLUME ["/data"]
EXPOSE 8000

# Liveness only: /api/health answers from a cached LLM state and never calls
# Ollama on the request path, so the 2 s check stays green in degraded mode
# (Ollama down or hung) — the body says "degraded" instead.
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)"

USER desk
ENTRYPOINT ["support-desk"]
