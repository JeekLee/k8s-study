# 멀티 스테이지 — 빌드 도구를 최종 이미지에 남기지 않는다
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
WORKDIR /app

# root 로 실행하지 않는다 — 컨테이너 보안의 기본
RUN useradd -r -u 10001 appuser
COPY --from=builder /install /usr/local
COPY main.py .
USER 10001

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
