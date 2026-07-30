FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
COPY . .
RUN uv sync --frozen --package artifice-ocr --extra web
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "artifice_ocr.web.server:app", \
     "--host", "0.0.0.0", "--port", "8000"]
