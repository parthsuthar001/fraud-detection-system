#!/usr/bin/env python3
"""
Transaction Generator
=====================
Generates realistic transaction streams for local development and demos.

Usage:
    python scripts/generate_transactions.py --rate 10 --scenario normal
    python scripts/generate_transactions.py --rate 5  --scenario attack
    python scripts/generate_transactions.py --rate 2  --scenario mixed
"""
import argparse
import asyncio
import httpx
import random
import time
import uuid
from datetime import datetime

API_URL = "http://localhost:8000/api/v1/transactions"

SCENARIOS = {
    "normal": {
        "user_ids": list(range(1001, 1020)),
        "amounts": (10, 800),
        "countries": ["India", "USA", "Germany", "Canada", "Singapore"],
        "merchants": ["Amazon", "Flipkart", "Zomato", "Apple Store"],
        "categories": ["retail", "food", "electronics"],
    },
    "attack": {
        "user_ids": [99999],  # Single attacker
        "amounts": (1, 10),   # Micro-transactions = card testing
        "countries": ["Russia", "Iran"],
        "merchants": ["Crypto Exchange"],
        "categories": ["crypto"],
    },
    "mixed": None,  # Handled specially below
}


def make_transaction(scenario_name: str) -> dict:
    if scenario_name == "attack":
        s = SCENARIOS["attack"]
    elif scenario_name == "mixed":
        # 80% normal, 20% suspicious
        s = SCENARIOS["normal"] if random.random() < 0.8 else SCENARIOS["attack"]
    else:
        s = SCENARIOS["normal"]

    return {
        "user_id": random.choice(s["user_ids"]),
        "amount": round(random.uniform(*s["amounts"]), 2),
        "currency": "USD",
        "merchant": random.choice(s["merchants"]),
        "merchant_category": random.choice(s["categories"]),
        "country": random.choice(s["countries"]),
        "card_last4": str(random.randint(1000, 9999)),
        "device_id": f"device-{uuid.uuid4().hex[:8]}",
    }


async def generate(rate: int, scenario: str, count: int = None):
    interval = 1.0 / rate
    sent = 0

    async with httpx.AsyncClient(timeout=5.0) as client:
        print(f"Generating {rate} TPS — scenario: {scenario}  (Ctrl+C to stop)")
        while True:
            tx = make_transaction(scenario)
            start = time.perf_counter()
            try:
                r = await client.post(API_URL, json=tx)
                elapsed = (time.perf_counter() - start) * 1000
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"user={tx['user_id']} amount=${tx['amount']:>8.2f} "
                    f"country={tx['country']:<12} "
                    f"→ {r.status_code} ({elapsed:.0f}ms)"
                )
            except Exception as e:
                print(f"Error: {e}")

            sent += 1
            if count and sent >= count:
                break

            await asyncio.sleep(max(0, interval - (time.perf_counter() - start)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fraud detection transaction generator")
    parser.add_argument("--rate", type=int, default=5, help="Transactions per second")
    parser.add_argument(
        "--scenario",
        choices=["normal", "attack", "mixed"],
        default="mixed",
    )
    parser.add_argument("--count", type=int, default=None, help="Stop after N transactions")
    args = parser.parse_args()

    asyncio.run(generate(args.rate, args.scenario, args.count))
