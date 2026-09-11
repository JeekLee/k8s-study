package com.k8sstudy.order;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 주문. 상태는 이벤트를 받아 바뀐다.
 *
 *   PENDING ──inventory.reserved──▶ RESERVED ──payment.approved──▶ CONFIRMED
 *      └──inventory.rejected──▶ CANCELLED
 *                 RESERVED ──payment.declined──▶ CANCELLED (재고 복원 유발)
 */
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @Column(length = 64)
    private String id;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false)
    private int qty;

    @Column(nullable = false, length = 32)
    private String status;

    @Column(nullable = false)
    private Instant createdAt;

    private Instant updatedAt;

    protected Order() { }

    public Order(String id, String sku, int qty) {
        this.id = id;
        this.sku = sku;
        this.qty = qty;
        this.status = "PENDING";
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    public void markStatus(String next) {
        this.status = next;
        this.updatedAt = Instant.now();
    }

    public String getId()          { return id; }
    public String getSku()         { return sku; }
    public int getQty()            { return qty; }
    public String getStatus()      { return status; }
    public Instant getCreatedAt()  { return createdAt; }
    public Instant getUpdatedAt()  { return updatedAt; }
}
