FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create models directory (model mounted via volume)
RUN mkdir -p models

# Start both the metrics HTTP server and the Kafka consumer
CMD ["python", "-m", "app.consumers.fraud_consumer"]
