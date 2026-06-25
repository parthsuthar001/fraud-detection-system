# 🛡️ Real-Time Fraud Detection System

> A production-grade distributed system that scores transactions for fraud risk in **< 50ms** using Kafka, Redis, FastAPI, and PostgreSQL.

[![CI](https://github.com/parthsuthar001/fraud-detection-system/actions/workflows/ci.yml/badge.svg)](https://github.com/parthsuthar001/fraud-detection-system/actions)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)
![Kafka](https://img.shields.io/badge/Kafka-7.5-orange)
![Redis](https://img.shields.io/badge/Redis-7.2-red)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)

---

## 🏗️ Architecture

```
Transaction Client
       │
       ▼ POST /transactions (202 Accepted)
┌─────────────────┐
│   API Gateway   │  FastAPI — validates & publishes to Kafka
│   (port 8000)   │
└────────┬────────┘
         │  Kafka: transactions-raw
         ▼
┌─────────────────────────────────────────┐
│         Fraud Detector (×2 workers)     │
│                                          │
│  ┌─────────────┐    ┌─────────────────┐ │
│  │ Rule Engine │◄──►│  Redis (Sliding │ │
│  │  9 rules    │    │  Window Cache)  │ │
│  └──────┬──────┘    └─────────────────┘ │
│         │                               │
│         ▼                               │
│   Risk Score (0–100) → APPROVE/BLOCK   │
└────────┬────────────────────────────────┘
         │  Kafka: fraud-events
    ┌────┴────────────────────┐
    │                         │
    ▼                         ▼
┌──────────┐          ┌──────────────────┐
│PostgreSQL│          │  Alert Service   │
│ (storage)│          │  WebSocket push  │
└──────────┘          └──────────────────┘
```

---

## ⚡ Engineering Patterns

### 1. Redis Sliding Window (Velocity Checks)
Detects card-testing attacks — fraudsters making rapid micro-transactions to verify stolen cards.

```python
# Uses Redis Sorted Sets for O(log N) sliding window
ZADD velocity:1001:60s  {tx_id: timestamp}   # Add
ZREMRANGEBYSCORE ...    # Prune expired
ZCARD ...               # Count in window
```

### 2. Idempotency / De-duplication
Kafka guarantees **at-least-once** delivery. We prevent double-scoring with Redis SET NX:

```python
# Atomic: set key only if it doesn't exist
await redis.set(f"dedup:{tx_id}", "1", ex=300, nx=True)
# Returns None if key existed → duplicate → skip
```

### 3. Circuit Breaker (Graceful Degradation)
If Kafka becomes unreachable, the API fails fast instead of hanging:

```
CLOSED → normal operation
  ↓ (5 consecutive failures)
OPEN   → reject calls immediately (30s)
  ↓ (timeout expires)
HALF_OPEN → allow one test call
  ↓ (success)
CLOSED again
```

### 4. Real-Time WebSocket Alerts
High-risk decisions (score > 80) are broadcast to connected dashboard clients via FastAPI WebSockets — zero polling needed.

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local dev)

### Run the full stack

```bash
git clone https://github.com/parthsuthar001/fraud-detection-system.git
cd fraud-detection-system

docker-compose up --build
```

That's it. All 7 services start with correct dependency ordering.

### Verify it's working

```bash
# Submit a test transaction
curl -X POST http://localhost:8000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1001,
    "amount": 55000,
    "merchant": "Crypto Exchange",
    "merchant_category": "crypto",
    "country": "Russia",
    "card_last4": "4242"
  }'

# Expected: 202 Accepted with transaction_id
# Fraud detector will score this ~95/100 → BLOCK
```

### Generate a transaction stream

```bash
pip install httpx
python scripts/generate_transactions.py --rate 10 --scenario mixed
```

---

## 🔍 Fraud Rules Engine

| Rule | Trigger | Score Delta |
|------|---------|------------|
| Large Transaction | amount > $50,000 | +40 |
| Large Transaction | amount > $10,000 | +20 |
| High-Risk Country | Russia, Iran, North Korea… | +30 |
| New Country | Country not in user history | +20 |
| Velocity (high) | 5+ transactions in 60s | +35 |
| Velocity (medium) | 3+ transactions in 60s | +15 |
| Velocity (10min) | 10+ transactions in 10min | +25 |
| Impossible Travel | Different country < 20 min | +40 |
| Night Activity | 1 AM – 5 AM UTC | +10 |
| New Account | Account < 7 days + amount > $1,000 | +20 |
| High-Risk Merchant | crypto, gambling, wire_transfer… | +15 |

**Score → Decision mapping:**

| Score | Risk Level | Action |
|-------|-----------|--------|
| 0–30  | LOW       | APPROVE |
| 31–60 | MEDIUM    | REVIEW |
| 61–80 | HIGH      | BLOCK |
| 81–100| CRITICAL  | BLOCK |

---

## 📊 API Reference

### POST `/api/v1/transactions`
Submit a transaction for fraud scoring.

**Request:**
```json
{
  "user_id": 1001,
  "amount": 15000.00,
  "currency": "USD",
  "merchant": "Electronics Store",
  "merchant_category": "electronics",
  "country": "Russia",
  "ip_address": "185.220.101.1",
  "card_last4": "4242"
}
```

**Response (202 Accepted):**
```json
{
  "transaction_id": "3f4a1b2c-...",
  "status": "ACCEPTED",
  "message": "Transaction received and queued for processing",
  "queued_at": "2024-01-15T10:30:00Z"
}
```

### GET `/api/v1/health`
Service health check.

### WebSocket `/ws/alerts`
Connect to receive real-time fraud alerts:
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/alerts");
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

---

## 🧪 Running Tests

```bash
cd fraud-detector
pip install -r requirements.txt pytest pytest-asyncio

pytest tests/ -v --cov=app
```

**Test coverage includes:**
- Large transaction thresholds
- High-risk country detection
- Velocity window edge cases
- Impossible travel calculation
- Full pipeline scoring

### Load Testing

```bash
pip install locust
locust -f tests/load_test.py --host=http://localhost:8000 --users 100 --spawn-rate 10
```

---

## 🗂️ Project Structure

```
fraud-detection-system/
├── .github/workflows/         # CI/CD — lint + tests on every push
│   └── ci.yml
│
├── api-gateway/               # FastAPI transaction ingestion
│   ├── app/
│   │   ├── main.py            # App entrypoint + WebSocket
│   │   ├── routes/            # HTTP route handlers
│   │   ├── schemas/           # Pydantic request/response models
│   │   └── core/              # Kafka producer, circuit breaker, config
│   ├── Dockerfile
│   └── requirements.txt
│
├── fraud-detector/            # Kafka consumer + rule engine
│   ├── app/
│   │   ├── consumers/         # Kafka consumer worker
│   │   ├── rules/             # Engine + Redis velocity tracker
│   │   └── db/                # PostgreSQL repository
│   ├── tests/
│   │   └── test_rules_engine.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── alert-service/             # Fraud event consumer + notifications
├── analytics-service/         # Dashboard API (fraud stats)
│
├── scripts/
│   └── generate_transactions.py   # Demo transaction generator
│
├── tests/
│   └── load_test.py           # Locust load test
│
├── docker-compose.yml         # Full stack orchestration
└── README.md
```

---

## 🏭 Production Considerations

| Concern | Solution |
|---------|---------|
| Duplicate processing | Redis SET NX idempotency key |
| Kafka consumer failure | Manual offset commit after success |
| Redis outage | Circuit breaker → fallback to basic rules |
| DB slowness | Async asyncpg pool, non-blocking writes |
| Scale fraud workers | `deploy.replicas: 2` in docker-compose (same consumer group → Kafka distributes partitions) |

---

## 📈 Benchmarks

Tested on a MacBook Pro M2, local Docker:

| Metric | Result |
|--------|--------|
| P50 latency (API → 202) | ~8ms |
| P95 latency (API → 202) | ~22ms |
| Rule engine evaluation | ~0.3ms |
| Redis velocity check | ~1.2ms |
| End-to-end (API → DB write) | ~45ms |
| Max throughput | ~1,200 TPS |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| API Gateway | FastAPI 0.111, Uvicorn |
| Message Broker | Apache Kafka (Confluent 7.5) |
| Cache / State | Redis 7.2 (Sorted Sets) |
| Database | PostgreSQL 16 (asyncpg) |
| Containerization | Docker Compose |
| CI/CD | GitHub Actions |
| Load Testing | Locust |
| Testing | pytest, pytest-asyncio |



## 🤖 ML Scoring Layer (XGBoost)

### Train the model
```bash
cd fraud-detector
pip install -r requirements.txt
python -m app.ml.trainer
```

Output: `models/fraud_model.json` (~50 KB, XGBoost native format)

### How it works

The system uses a **hybrid scoring** approach:

```
Rule Engine Score  ──┐
                     ├─► Blended Score = 0.65 × ML + 0.35 × Rules
XGBoost ML Score  ──┘
```

**14 features fed to XGBoost:**

| Feature | Description |
|---------|-------------|
| `amount`, `amount_log` | Raw and log-scaled amount |
| `is_large_tx` | Flag for amount > $10,000 |
| `tx_count_60s`, `tx_count_10min` | Velocity from Redis sliding windows |
| `is_high_risk_country` | Country in HIGH_RISK set |
| `is_new_country` | Country not in user's history |
| `impossible_travel` | Different country within 20 min |
| `hour_of_day`, `is_night` | Time-based features |
| `is_high_risk_merchant` | Merchant category risk |
| `account_age_days`, `is_new_account` | Account tenure |
| `rule_score` | Rules engine output as a feature |

**Graceful degradation**: if the model file doesn't exist at startup, the service automatically falls back to rules-only scoring — no crashes.

---

## 📊 Grafana Dashboard

After `docker-compose up`, open **http://localhost:3000**

- Username: `admin`
- Password: `fraud123`

The **Fraud Detection — Live Dashboard** auto-loads with:

| Panel | Metric |
|-------|--------|
| Transactions/sec | `rate(fraud_transactions_total[1m])` |
| Block rate % | Blocked / Total ratio |
| P95 latency | 95th percentile processing time |
| ML scoring active % | % of transactions scored by XGBoost |
| Decision timeline | APPROVE / BLOCK / REVIEW over time |
| Risk score histogram | Distribution of 0–100 scores |
| Top triggered rules | Which rules fire most often |
| ML probability distribution | Raw XGBoost output over time |
| Latency percentiles | P50 / P95 / P99 |

Prometheus scrapes metrics every **5 seconds**.
Data is retained for **15 days** by default.

---

## 🏃 Full Stack Startup Order

```bash
docker-compose up --build
```

Services start in this order (health-checked):
1. Zookeeper → Kafka → Redis → PostgreSQL
2. API Gateway, Fraud Detector ×2, Alert Service, Analytics Service
3. Prometheus, Grafana, Redis Exporter, Postgres Exporter

**Access points after startup:**

| Service | URL |
|---------|-----|
| API Gateway | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Grafana Dashboard | http://localhost:3000 |
| Prometheus | http://localhost:9091 |
| Fraud metrics | http://localhost:9090/metrics |

