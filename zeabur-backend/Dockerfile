FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

COPY zeabur-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY zeabur-backend/app.py .

CMD ["python", "app.py"]
