# ── 빌드 ──
# Maven 을 컨테이너 안에서 돌린다. 로컬에 Java·Maven 을 깔 필요가 없고
# 어디서 빌드하든 같은 결과가 나온다.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B clean package -DskipTests

# ── 실행 ──
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd -r -u 10001 appuser
COPY --from=build /build/target/*.jar app.jar
USER 10001

# 컨테이너 메모리 제한을 JVM 이 인식하게 한다.
# 이게 없으면 호스트 전체 메모리를 기준으로 힙을 잡아 OOMKilled 가 난다.
ENV JAVA_OPTS="-XX:MaxRAMPercentage=75 -XX:+UseContainerSupport"

EXPOSE 8080
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar app.jar"]
