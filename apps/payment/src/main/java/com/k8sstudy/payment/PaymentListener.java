package com.k8sstudy.payment;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * inventory.reserved 를 받아 결제를 시도한다.
 *
 * 성공 → payment.approved
 * 실패 → payment.declined  (inventory 가 받아 재고를 복원한다)
 */
@Component
public class PaymentListener {

    private static final Logger log = LoggerFactory.getLogger(PaymentListener.class);

    private final PaymentRepository payments;
    private final ProcessedEventRepository processed;
    private final KafkaTemplate<String, DomainEvent> kafka;

    /** 결제 실패를 인위적으로 만들기 위한 값. 보상 트랜잭션 실습용. */
    @Value("${app.decline-sku:}")
    private String declineSku;

    @Autowired(required = false)
    public PaymentListener(PaymentRepository payments,
                           ProcessedEventRepository processed,
                           KafkaTemplate<String, DomainEvent> kafka) {
        this.payments = payments;
        this.processed = processed;
        this.kafka = kafka;
    }

    @KafkaListener(topics = "inventory.reserved", groupId = "payment")
    @Transactional
    public void onInventoryReserved(DomainEvent event) {
        if (processed.existsById(event.eventId())) {
            log.info("중복 이벤트 무시 {}", event.eventId());
            return;
        }

        boolean approved = !event.sku().equals(declineSku);
        String status = approved ? "APPROVED" : "DECLINED";

        payments.save(new Payment(event.orderId(), status));
        processed.save(new ProcessedEvent(event.eventId()));

        String topic = approved ? "payment.approved" : "payment.declined";
        if (kafka != null) {
            kafka.send(topic, event.orderId(),
                    DomainEvent.of(topic, event.orderId(), event.sku(), event.qty()));
        }
        log.info("결제 {} orderId={} → {}", status, event.orderId(), topic);
    }
}
