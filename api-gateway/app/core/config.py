from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_TOPIC_TRANSACTIONS: str = "transactions-raw"
    KAFKA_TOPIC_FRAUD_EVENTS: str = "fraud-events"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://fraud_user:fraud_pass@postgres:5432/fraud_db"

    # App
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
