FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

COPY services/presentation_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY backend /app/backend
COPY templates /app/templates
COPY services/presentation_service /app/services/presentation_service

WORKDIR /app
EXPOSE 8005

CMD ["uvicorn", "services.presentation_service.app:app", "--host", "0.0.0.0", "--port", "8005"]
