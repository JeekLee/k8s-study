package com.k8sstudy.order;

import java.time.Instant;
import java.util.UUID;

/**
 * 모든 이벤트의 공통 형태.
 *
 * eventId 는 컨슈머가 중복을 걸러내는 열쇠다.
 * Kafka 는 at-least-once 이므로 같은 이벤트를 두 번 받을 수 있다.
 */
public record DomainEvent(
        String eventId,
        String type,
        String orderId,
        String sku,
        int qty,
        String occurredAt
) {
    public static DomainEvent of(String type, String orderId, String sku, int qty) {
        return new DomainEvent(
                UUID.randomUUID().toString(),
                type,
                orderId,
                sku,
                qty,
                Instant.now().toString()
        );
    }
}
