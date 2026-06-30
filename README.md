#  Real-Time Fraud Detection System

![CI](https://github.com/parthsuthar001/fraud-detection-system/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)
![Kafka](https://img.shields.io/badge/Kafka-7.5-black)
![Redis](https://img.shields.io/badge/Redis-7.2-red)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![XGBoost](https://img.shields.io/badge/XGBoost-2.0-success)

A distributed fraud detection platform built with **FastAPI, Kafka, Redis, PostgreSQL, and XGBoost**.

Transactions are accepted asynchronously, enriched with cached state, evaluated using deterministic fraud rules and an optional machine learning model, then stored and published for downstream consumers.

---

# Features

* Event-driven architecture using Kafka
* FastAPI API Gateway
* Redis sliding-window velocity detection
* Rule-based fraud engine
* Optional XGBoost fraud scoring
* PostgreSQL persistence
* WebSocket fraud alerts
* Prometheus metrics
* Grafana dashboards
* Docker Compose deployment
* GitHub Actions CI

---

# Architecture

```text
Transaction Client
       │
       ▼
 API Gateway (FastAPI)
       │
       ▼
Kafka Topic (transactions-raw)
       │
       ▼
Fraud Detector Workers
 ├── Rule Engine
 ├── XGBoost Model
 ├── Redis
 └── PostgreSQL
       │
       ▼
Kafka Topic (fraud-events)
       │
 ┌─────┴─────────────┐
 ▼                   ▼
Alert Service   Analytics Service
```

---

# Technology Stack

| Layer            | Technology           |
| ---------------- | -------------------- |
| API              | FastAPI              |
| Messaging        | Apache Kafka         |
| Cache            | Redis                |
| Database         | PostgreSQL           |
| ML               | XGBoost              |
| Monitoring       | Prometheus + Grafana |
| Testing          | pytest               |
| CI/CD            | GitHub Actions       |
| Containerization | Docker Compose       |

---

# Project Structure

```text
fraud-detection-system/
│
├── api-gateway/
├── fraud-detector/
├── alert-service/
├── analytics-service/
├── monitoring/
├── scripts/
├── tests/
├── .github/workflows/
└── docker-compose.yml
```

---

# Getting Started

Clone the repository.

```bash
git clone https://github.com/parthsuthar001/fraud-detection-system.git

cd fraud-detection-system
```

Start every service.

```bash
docker-compose up --build
```

---

# Available Services

| Service    | URL                        |
| ---------- | -------------------------- |
| API        | http://localhost:8000      |
| Swagger    | http://localhost:8000/docs |
| Grafana    | http://localhost:3000      |
| Prometheus | http://localhost:9091      |

Grafana credentials

```
Username: admin

Password: fraud123
```

---

# Example Request

```bash
curl -X POST http://localhost:8000/api/v1/transactions \
-H "Content-Type: application/json" \
-d '{
  "user_id":1001,
  "amount":55000,
  "merchant":"Crypto Exchange",
  "merchant_category":"crypto",
  "country":"Russia",
  "card_last4":"4242"
}'
```

The API immediately returns

```
202 Accepted
```

The fraud detector processes the transaction asynchronously and publishes the result after scoring.

---

# Fraud Rules

| Rule               |     Score |
| ------------------ | --------: |
| Amount > $50,000   |       +40 |
| Amount > $10,000   |       +20 |
| High-risk Country  |       +30 |
| New Country        |       +20 |
| Velocity (60 s)    | +15 / +35 |
| Velocity (10 min)  |       +25 |
| Impossible Travel  |       +40 |
| Night Activity     |       +10 |
| New Account        |       +20 |
| High-risk Merchant |       +15 |

Risk Levels

|  Score | Decision |
| -----: | -------- |
|   0–30 | APPROVE  |
|  31–60 | REVIEW   |
| 61–100 | BLOCK    |

---

# Machine Learning

The detector supports hybrid scoring.

```
Rule Engine
      │
      ├────► Final Score
      │
XGBoost Model
```

Fourteen engineered features are extracted from each transaction, including

* amount
* transaction velocity
* geographic history
* merchant category
* account age
* time-based features
* rule engine score

If no trained model is available, the detector automatically falls back to rule-based scoring.

---

# Running Tests

```bash
cd fraud-detector

pytest tests/ -v --cov=app
```

GitHub Actions automatically runs

* Ruff linting
* Unit tests
* Coverage

on every push and pull request.

---

# Load Testing

```bash
locust -f tests/load_test.py \
--host=http://localhost:8000 \
--users 100 \
--spawn-rate 10
```

---

# Design Highlights

## Redis Sliding Window

Tracks transaction velocity using Redis Sorted Sets for efficient rolling-window calculations.

## Kafka Consumer Groups

Multiple fraud detector workers process transactions in parallel while preserving message ordering within partitions.

## Idempotency

Duplicate Kafka messages are ignored using Redis `SET NX`.

## Circuit Breaker

The API Gateway stops publishing when Kafka becomes unavailable and resumes automatically after recovery.

## Manual Offset Commits

Kafka offsets are committed only after successful processing to avoid message loss.

---

# Monitoring

The project exposes Prometheus metrics and includes a pre-configured Grafana dashboard displaying

* transaction throughput
* fraud decisions
* latency
* rule activity
* ML scoring
* processing metrics

---

# Future Improvements

* Online model retraining
* Kubernetes deployment
* OpenTelemetry tracing
* Feature store
* Authentication and authorization
* Multi-region Kafka clusters

---

# License

MIT
