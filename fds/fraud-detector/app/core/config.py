from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_TOPIC_TRANSACTIONS: str = "transactions-raw"
    KAFKA_TOPIC_FRAUD_EVENTS: str = "fraud-events"
    KAFKA_TOPIC_ALERTS: str = "alert-events"

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    DATABASE_URL: str = "postgresql+asyncpg://fraud_user:fraud_pass@postgres:5432/fraud_db"

    class Config:
        env_file = ".env"


settings = Settings()
