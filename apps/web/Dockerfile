# ── 빌드 ──
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── 실행 ──
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 10001 app && adduser -u 10001 -G app -D app

# standalone 출력은 실행에 필요한 것만 담겨 있다 — 이미지가 훨씬 작다
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER 10001
EXPOSE 3000
CMD ["node", "server.js"]
