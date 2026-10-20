FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
EXPOSE 8000
# One worker with threads keeps in-memory rate limits and the analysis store accurate.
# For more workers or instances, set RATELIMIT_STORAGE_URI to Redis.
RUN useradd -m appuser
USER appuser
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "1", "--threads", "8", "--timeout", "300", "app:app"]
