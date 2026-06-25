"""
Load Test — Fraud Detection API
================================
Simulates realistic transaction patterns including:
  - Normal transactions (70%)
  - Large amount transactions (15%)
  - High-risk country transactions (10%)
  - Rapid-fire velocity attacks (5%)

Run with:
    pip install locust
    locust -f tests/load_test.py --host=http://localhost:8000 --users 100 --spawn-rate 10
"""
from locust import HttpUser, task, between
import random
import uuid

COUNTRIES = ["India", "USA", "Germany", "UK", "France", "Canada", "Singapore"]
HIGH_RISK_COUNTRIES = ["Russia", "Iran", "North Korea"]
MERCHANTS = ["Amazon", "Flipkart", "Apple Store", "Electronics Hub", "Grocery Mart"]


class FraudDetectionUser(HttpUser):
    wait_time = between(0.1, 0.5)  # Simulate 2–10 TPS per user

    @task(70)
    def normal_transaction(self):
        """Typical low-risk transaction."""
        self.client.post(
            "/api/v1/transactions",
            json={
                "user_id": random.randint(1000, 9999),
                "amount": round(random.uniform(10, 500), 2),
                "currency": "USD",
                "merchant": random.choice(MERCHANTS),
                "merchant_category": "retail",
                "country": random.choice(COUNTRIES),
                "card_last4": str(random.randint(1000, 9999)),
            },
        )

    @task(15)
    def large_transaction(self):
        """Large amount — should trigger amount rules."""
        self.client.post(
            "/api/v1/transactions",
            json={
                "user_id": random.randint(1000, 9999),
                "amount": round(random.uniform(10_001, 60_000), 2),
                "currency": "USD",
                "merchant": "Wire Transfer Service",
                "merchant_category": "wire_transfer",
                "country": "USA",
                "card_last4": "4242",
            },
        )

    @task(10)
    def high_risk_country_transaction(self):
        """High-risk country — should trigger geo rules."""
        self.client.post(
            "/api/v1/transactions",
            json={
                "user_id": random.randint(1000, 9999),
                "amount": round(random.uniform(500, 5000), 2),
                "currency": "USD",
                "merchant": "Electronics Boutique",
                "merchant_category": "electronics",
                "country": random.choice(HIGH_RISK_COUNTRIES),
                "card_last4": "1111",
            },
        )

    @task(5)
    def velocity_attack(self):
        """Same user sending many rapid transactions — card testing simulation."""
        attacker_user_id = 99999  # Fixed ID to hit velocity limits
        self.client.post(
            "/api/v1/transactions",
            json={
                "user_id": attacker_user_id,
                "amount": round(random.uniform(1, 5), 2),
                "currency": "USD",
                "merchant": "Random Shop",
                "merchant_category": "retail",
                "country": "USA",
                "card_last4": "0000",
            },
        )
