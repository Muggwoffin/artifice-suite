FROM python:3.12-slim
WORKDIR /app/apps/artifice-ocr

COPY apps/artifice-ocr .
RUN pip install --no-cache-dir -e ".[web]"

EXPOSE 8000
CMD ["uvicorn", "artifice_ocr.web.server:app", "--host", "0.0.0.0", "--port", "8000"]
