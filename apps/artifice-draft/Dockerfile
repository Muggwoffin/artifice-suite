FROM python:3.12-slim
WORKDIR /app/apps/artifice-draft

COPY apps/artifice-draft .
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart beautifulsoup4 readability-lxml

EXPOSE 8000
CMD ["uvicorn", "artifice_draft.web.server:app", "--host", "0.0.0.0", "--port", "8000"]
