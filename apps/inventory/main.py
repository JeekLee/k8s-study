"""
inventory — 재고 서비스

Stage 4 에서는 메모리에만 저장한다. Stage 5 에서 MySQL 로 바꾼다.
쿠버네티스 학습이 목적이므로 앱 자체는 최소로 유지한다.
"""
import os
import socket
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "dev")
GREETING = os.getenv("GREETING", "inventory service")   # ConfigMap 주입 확인용

app = FastAPI(title="inventory", version=APP_VERSION)

# Stage 5 에서 MySQL 로 대체된다
_stock: dict[str, int] = {"SKU-001": 10, "SKU-002": 3, "SKU-003": 0}
_ready = False


class ReserveRequest(BaseModel):
    sku: str
    qty: int


@app.on_event("startup")
async def _startup() -> None:
    """기동 직후 바로 준비되지는 않는다는 것을 보여주기 위한 지연."""
    global _ready
    _ready = True


# ── 상태 확인 엔드포인트 ─────────────────────────────────
# livenessProbe  : 프로세스가 살아 있는가. 실패하면 재시작
# readinessProbe : 트래픽을 받을 준비가 됐는가. 실패하면 Service 에서 제외
@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    if not _ready:
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ready"}


# ── 업무 엔드포인트 ──────────────────────────────────────
@app.get("/")
async def root() -> dict:
    """어느 파드가 응답했는지 보이게 한다 — 로드밸런싱 확인용."""
    return {
        "service": "inventory",
        "version": APP_VERSION,
        "greeting": GREETING,
        "pod": socket.gethostname(),
        "now": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/stock")
async def list_stock() -> dict:
    return {"stock": _stock, "pod": socket.gethostname()}


@app.post("/reserve")
async def reserve(req: ReserveRequest) -> dict:
    """재고 예약. Stage 6 에서 order.created 이벤트로 호출된다."""
    have = _stock.get(req.sku)
    if have is None:
        raise HTTPException(status_code=404, detail=f"unknown sku: {req.sku}")
    if have < req.qty:
        raise HTTPException(status_code=409, detail=f"insufficient stock: {have} < {req.qty}")
    _stock[req.sku] = have - req.qty
    return {"sku": req.sku, "reserved": req.qty, "remaining": _stock[req.sku]}


@app.post("/release")
async def release(req: ReserveRequest) -> dict:
    """재고 복원 — 보상 트랜잭션."""
    _stock[req.sku] = _stock.get(req.sku, 0) + req.qty
    return {"sku": req.sku, "released": req.qty, "remaining": _stock[req.sku]}
