package com.k8sstudy.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 멱등성 — 처리한 eventId 를 기록해 중복을 무시한다.
 *
 * Kafka 는 at-least-once 라 같은 이벤트를 두 번 받을 수 있다.
 * Stage 6 에서는 이것을 일부러 빼고 돌려 중복 결제가 나는 것을 먼저 확인한다.
 */
@Entity
@Table(name = "processed_events")
public class ProcessedEvent {

    @Id
    @Column(length = 64)
    private String eventId;

    @Column(nullable = false)
    private Instant processedAt;

    protected ProcessedEvent() { }

    public ProcessedEvent(String eventId) {
        this.eventId = eventId;
        this.processedAt = Instant.now();
    }
}
