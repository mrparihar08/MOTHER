FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/dora-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/dora /app/backend/dora
COPY services/dora-service/app.py /app/app.py

ENV PORT=8001
EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
