FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ingest.py .
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/orders.db
CMD ["python", "ingest.py"]