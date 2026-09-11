"""
inventory — 재고 서비스

동작이 환경변수로 바뀐다. 이미지를 다시 빌드하지 않고 단계를 넘어간다.

  DATABASE_URL 없음  → 메모리 (Stage 4)
  DATABASE_URL 있음  → MySQL  (Stage 5~)
"""
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "dev")
GREETING = os.getenv("GREETING", "inventory service")     # ConfigMap 주입 확인용
DATABASE_URL = os.getenv("DATABASE_URL", "")              # 예: mysql+pymysql://u:p@mysql:3306/inventory

SEED = {"SKU-001": 10, "SKU-002": 3, "SKU-003": 0, "SKU-999": 5}

_memory: dict[str, int] = dict(SEED)
_engine = None
_ready = False


# ── 저장소 — 메모리와 DB 를 같은 함수로 감싼다 ──────────────
def _db_enabled() -> bool:
    return bool(DATABASE_URL)


def _init_db() -> None:
    """테이블을 만들고 초기 재고를 넣는다. 실무라면 마이그레이션 도구를 쓴다."""
    global _engine
    from sqlalchemy import create_engine, text

    _engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    with _engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS stock ("
            " sku VARCHAR(64) PRIMARY KEY,"
            " qty INT NOT NULL"
            ")"
        ))
        for sku, qty in SEED.items():
            conn.execute(
                text("INSERT IGNORE INTO stock (sku, qty) VALUES (:sku, :qty)"),
                {"sku": sku, "qty": qty},
            )


def _get_all() -> dict[str, int]:
    if not _db_enabled():
        return dict(_memory)
    from sqlalchemy import text

    with _engine.connect() as conn:
        return {r[0]: r[1] for r in conn.execute(text("SELECT sku, qty FROM stock"))}


def _adjust(sku: str, delta: int, *, require_available: bool) -> int:
    """재고를 delta 만큼 바꾸고 남은 수량을 돌려준다."""
    if not _db_enabled():
        have = _memory.get(sku)
        if have is None:
            raise HTTPException(404, f"unknown sku: {sku}")
        if require_available and have + delta < 0:
            raise HTTPException(409, f"insufficient stock: {have} < {-delta}")
        _memory[sku] = have + delta
        return _memory[sku]

    from sqlalchemy import text

    with _engine.begin() as conn:
        # 동시 주문에서 재고가 음수가 되지 않도록 행을 잠근다
        row = conn.execute(
            text("SELECT qty FROM stock WHERE sku = :sku FOR UPDATE"), {"sku": sku}
        ).first()
        if row is None:
            raise HTTPException(404, f"unknown sku: {sku}")
        have = row[0]
        if require_available and have + delta < 0:
            raise HTTPException(409, f"insufficient stock: {have} < {-delta}")
        conn.execute(
            text("UPDATE stock SET qty = :qty WHERE sku = :sku"),
            {"qty": have + delta, "sku": sku},
        )
        return have + delta


# ── 앱 ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ready
    if _db_enabled():
        _init_db()
    _ready = True
    yield


app = FastAPI(title="inventory", version=APP_VERSION, lifespan=lifespan)


class ReserveRequest(BaseModel):
    sku: str
    qty: int


# livenessProbe  : 프로세스가 살아 있는가. 실패하면 재시작
# readinessProbe : 트래픽을 받을 준비가 됐는가. 실패하면 Service 에서 제외
@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    if not _ready:
        raise HTTPException(503, "not ready")
    return {"status": "ready", "storage": "mysql" if _db_enabled() else "memory"}


@app.get("/")
async def root() -> dict:
    """어느 파드가 응답했는지 보이게 한다 — 로드밸런싱 확인용."""
    return {
        "service": "inventory",
        "version": APP_VERSION,
        "greeting": GREETING,
        "storage": "mysql" if _db_enabled() else "memory",
        "pod": socket.gethostname(),
        "now": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/stock")
async def list_stock() -> dict:
    return {"stock": _get_all(), "pod": socket.gethostname()}


@app.post("/reserve")
async def reserve(req: ReserveRequest) -> dict:
    """재고 예약. Stage 6 에서 order.created 이벤트로 호출된다."""
    remaining = _adjust(req.sku, -req.qty, require_available=True)
    return {"sku": req.sku, "reserved": req.qty, "remaining": remaining}


@app.post("/release")
async def release(req: ReserveRequest) -> dict:
    """재고 복원 — 보상 트랜잭션."""
    remaining = _adjust(req.sku, req.qty, require_available=False)
    return {"sku": req.sku, "released": req.qty, "remaining": remaining}
