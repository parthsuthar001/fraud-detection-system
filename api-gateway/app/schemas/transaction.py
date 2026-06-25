from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from enum import Enum
import uuid


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TransactionRequest(BaseModel):
    user_id: int = Field(..., description="Unique user identifier")
    amount: float = Field(..., gt=0, description="Transaction amount in USD")
    currency: str = Field(default="USD", max_length=3)
    merchant: str = Field(..., max_length=100)
    merchant_category: Optional[str] = Field(None, max_length=50)
    country: str = Field(..., max_length=50)
    ip_address: Optional[str] = Field(None)
    device_id: Optional[str] = Field(None)
    card_last4: Optional[str] = Field(None, max_length=4)

    @validator("amount")
    def round_amount(cls, v):
        return round(v, 2)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1001,
                "amount": 15000.00,
                "currency": "USD",
                "merchant": "Electronics Store",
                "merchant_category": "electronics",
                "country": "Russia",
                "ip_address": "185.220.101.1",
                "device_id": "device-abc-123",
                "card_last4": "4242",
            }
        }


class TransactionResponse(BaseModel):
    transaction_id: str
    status: str = "ACCEPTED"
    message: str = "Transaction received and queued for processing"
    queued_at: datetime


class FraudDecision(BaseModel):
    transaction_id: str
    user_id: int
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    status: TransactionStatus
    triggered_rules: list[str]
    processing_time_ms: float
    decided_at: datetime
