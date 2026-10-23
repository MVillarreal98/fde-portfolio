# Multi-stage: the same image that runs tests in CI is the one that ships.
# Runtime stays zero-dependency on purpose (stdlib HTTP server): the only
# package installed is the application itself.

FROM python:3.12-slim AS test

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
RUN pip install --no-cache-dir . pytest
RUN python -m pytest tests -q

FROM python:3.12-slim AS runtime

# Non-root: the operator API never needs elevated privileges.
RUN useradd --create-home --uid 10001 desk
WORKDIR /app

COPY --from=test /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=test /usr/local/bin /usr/local/bin
COPY --from=test /app/src /app/src

# Container defaults; every value stays env-overridable (config.py).
ENV SUPPORT_DESK_HOST=0.0.0.0 \
    SUPPORT_DESK_PORT=8000 \
    OLLAMA_MODEL=llama3.2:1b
EXPOSE 8000

# The service degrades gracefully when Ollama is unreachable, so a plain HTTP
# check on /api/health is the right signal — not the LLM's availability.
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)"

USER desk
ENTRYPOINT ["support-desk"]
