"""
notification — 모든 도메인 이벤트를 구독해 알림을 남긴다.

저장소가 없다. 순수 컨슈머라 Kafka 소비 패턴을 관찰하기 가장 좋다.
컨슈머 그룹·파티션·리밸런싱 실습은 이 서비스로 한다.
"""
import asyncio
import json
import os
import socket
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

APP_VERSION = os.getenv("APP_VERSION", "dev")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "")
TOPICS = os.getenv(
    "TOPICS",
    "order.created,inventory.reserved,inventory.rejected,"
    "inventory.released,payment.approved,payment.declined",
).split(",")

# 최근 이벤트를 메모리에 들고 있다가 /events 로 보여준다
_recent: deque = deque(maxlen=200)
_consumer_task: asyncio.Task | None = None


async def _consume() -> None:
    """Kafka 가 설정돼 있을 때만 동작한다. Stage 4·5 에서는 그냥 대기."""
    if not KAFKA_BOOTSTRAP:
        return
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=os.getenv("GROUP_ID", "notification"),
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode()),
    )
    await consumer.start()
    try:
        async for msg in consumer:
            _recent.append(
                {
                    "topic": msg.topic,
                    "partition": msg.partition,
                    "offset": msg.offset,
                    "value": msg.value,
                    "receivedAt": datetime.now(timezone.utc).isoformat(),
                    "pod": socket.gethostname(),
                }
            )
            print(f"[알림] {msg.topic} p{msg.partition} @{msg.offset} {msg.value}", flush=True)
    finally:
        await consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_task
    _consumer_task = asyncio.create_task(_consume())
    yield
    if _consumer_task:
        _consumer_task.cancel()


app = FastAPI(title="notification", version=APP_VERSION, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    return {"status": "ready", "kafka": bool(KAFKA_BOOTSTRAP)}


@app.get("/")
async def root() -> dict:
    return {
        "service": "notification",
        "version": APP_VERSION,
        "pod": socket.gethostname(),
        "kafka": KAFKA_BOOTSTRAP or "(미설정)",
        "topics": TOPICS,
        "received": len(_recent),
    }


@app.get("/events")
async def events(limit: int = 50) -> dict:
    """받은 이벤트를 최신순으로. 파티션·오프셋이 보이므로 리밸런싱 관찰에 쓴다."""
    items = list(_recent)[-limit:]
    items.reverse()
    return {"count": len(items), "events": items, "pod": socket.gethostname()}
