package com.k8sstudy.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "payments")
public class Payment {

    @Id
    @Column(length = 64)
    private String orderId;

    @Column(nullable = false, length = 32)
    private String status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Payment() { }

    public Payment(String orderId, String status) {
        this.orderId = orderId;
        this.status = status;
        this.createdAt = Instant.now();
    }

    public String getOrderId()    { return orderId; }
    public String getStatus()     { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
