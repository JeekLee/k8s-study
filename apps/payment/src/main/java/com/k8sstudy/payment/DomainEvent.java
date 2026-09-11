package com.k8sstudy.payment;

import java.time.Instant;
import java.util.UUID;

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
                UUID.randomUUID().toString(), type, orderId, sku, qty,
                Instant.now().toString());
    }
}
