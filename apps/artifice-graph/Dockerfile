# ---- builder ----
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app

# Layer 1 — dependency resolution (cached unless lock, a pyproject.toml, or packages/ changes)
COPY pyproject.toml uv.lock ./
COPY apps/artifice-ocr/pyproject.toml        apps/artifice-ocr/
COPY apps/artifice-draft/pyproject.toml      apps/artifice-draft/
COPY apps/artifice-graph/pyproject.toml      apps/artifice-graph/
COPY apps/artifice-transcribe/pyproject.toml apps/artifice-transcribe/
COPY packages/ packages/
RUN uv sync --locked --no-install-project --package artifice-graph --extra web

# Layer 2 — full source + project install
COPY . .
RUN uv sync --locked --package artifice-graph --extra web

# ---- runtime ----
FROM python:3.12-slim AS runtime
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app
# --chown is load-bearing here, unlike in the other three images. graph resolves
# its data directories CWD-relative (config.py:47,56,69,72 — "data/input_ocr",
# "data/output", ...) and creates them on first request, so a root-owned /app
# gives a non-root process PermissionError and a 500. ocr, draft and transcribe
# write to ~/.artifice_* and platformdirs instead, which useradd already owns.
COPY --from=builder --chown=appuser:appuser /app /app

EXPOSE 8766
USER appuser
CMD ["uv", "run", "--no-sync", "uvicorn", "artifice_graph.web.server:app", \
     "--host", "0.0.0.0", "--port", "8766"]
