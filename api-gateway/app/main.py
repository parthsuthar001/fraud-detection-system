from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import json
import logging

from app.routes import transactions, health
from app.core.kafka_producer import KafkaProducerClient
from app.core.websocket_manager import ConnectionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting API Gateway...")
    app.state.kafka_producer = KafkaProducerClient()
    await app.state.kafka_producer.start()
    yield
    # Shutdown
    logger.info("Shutting down API Gateway...")
    await app.state.kafka_producer.stop()


app = FastAPI(
    title="Fraud Detection API Gateway",
    description="Real-time transaction ingestion and fraud alerting system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api/v1", tags=["Transactions"])
app.include_router(health.router, prefix="/api/v1", tags=["Health"])


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time fraud alerts."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; alerts are pushed from Kafka consumer
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from alerts WebSocket")
