FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
RUN uv sync --frozen --package artifice-graph --extra web
EXPOSE 8766
CMD ["uv", "run", "--no-sync", "uvicorn", "artifice_graph.web.server:app", \
     "--host", "0.0.0.0", "--port", "8766"]
