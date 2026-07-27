FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y ffmpeg build-essential
COPY packages ./packages
COPY apps/artifice-transcribe ./apps/artifice-transcribe
CMD ["python3", "-m", "http.server", "3000"]
