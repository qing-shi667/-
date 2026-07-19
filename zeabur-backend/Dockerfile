FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY index.html calculator-original.html ./
COPY assets ./assets

CMD ["python", "app.py"]
