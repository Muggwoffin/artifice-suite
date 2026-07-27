FROM python:3.12-slim
WORKDIR /app/apps/artifice-graph

COPY apps/artifice-graph .
RUN pip install --no-cache-dir -e ".[web]"

EXPOSE 8766
CMD ["python", "-m", "web.server"]
