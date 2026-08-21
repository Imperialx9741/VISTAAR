from fastapi import Depends, FastAPI, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db
from core.kafka import check_kafka_connection
from core.redis import get_redis

app = FastAPI(
    title="VISTAAR Backend",
    description="VISTAAR Ride Matching Platform Backend",
    version="0.1.0",
)


@app.get("/")
async def read_root() -> dict[str, str]:
    return {"message": "Welcome to VISTAAR Backend API"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "OK"}


@app.get("/health/db")
def db_health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Database connectivity check failed: {str(e)}"
        ) from e


@app.get("/health/redis")
async def redis_health_check(
    redis_client: Redis = Depends(get_redis),
) -> dict[str, str]:
    try:
        pong = await redis_client.ping()
        if pong:
            return {"status": "healthy", "redis": "connected"}
        raise HTTPException(status_code=503, detail="Redis PING failed")
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Redis connectivity check failed: {str(e)}"
        ) from e


@app.get("/health/kafka")
async def kafka_health_check() -> dict[str, str]:
    try:
        await check_kafka_connection()
        return {"status": "healthy", "kafka": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Kafka connectivity check failed: {str(e)}"
        ) from e
