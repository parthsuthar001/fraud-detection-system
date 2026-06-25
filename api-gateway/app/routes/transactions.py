from fastapi import APIRouter, Request, HTTPException, status
from datetime import datetime, timezone
import uuid
import json
import logging

from app.schemas.transaction import TransactionRequest, TransactionResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a transaction for fraud scoring",
    description="Accepts a transaction payload, validates it, and publishes it to Kafka for async fraud analysis.",
)
async def submit_transaction(request: Request, transaction: TransactionRequest):
    """
    Ingestion endpoint — returns 202 immediately to keep latency minimal.
    Actual fraud scoring happens asynchronously in the fraud-detector service.
    """
    transaction_id = str(uuid.uuid4())
    queued_at = datetime.now(timezone.utc)

    # Build the Kafka event payload
    event = {
        "transaction_id": transaction_id,
        "queued_at": queued_at.isoformat(),
        **transaction.model_dump(),
    }

    try:
        await request.app.state.kafka_producer.publish(
            topic="transactions-raw",
            key=str(transaction.user_id),
            value=json.dumps(event),
        )
        logger.info(f"Transaction {transaction_id} queued for user {transaction.user_id}")
    except Exception as e:
        logger.error(f"Kafka publish failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transaction queue temporarily unavailable. Please retry.",
        )

    return TransactionResponse(
        transaction_id=transaction_id,
        queued_at=queued_at,
    )


@router.get(
    "/transactions/{transaction_id}",
    summary="Get fraud decision for a transaction",
)
async def get_transaction_result(transaction_id: str, request: Request):
    """Retrieve the fraud decision for a previously submitted transaction."""
    # In production: query PostgreSQL for the stored decision
    return {
        "transaction_id": transaction_id,
        "message": "Query your PostgreSQL transactions table for the fraud decision.",
    }
