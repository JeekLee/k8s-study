package com.k8sstudy.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * 이벤트 발행.
 *
 * Kafka 가 없어도 뜬다 — Stage 4·5 에서는 Kafka 를 아직 올리지 않기 때문이다.
 * 그때는 로그로만 남고, Stage 6 에서 브로커를 붙이면 실제로 발행된다.
 */
@Component
public class EventPublisher {

    private static final Logger log = LoggerFactory.getLogger(EventPublisher.class);

    private final KafkaTemplate<String, DomainEvent> kafka;

    @Autowired(required = false)
    public EventPublisher(KafkaTemplate<String, DomainEvent> kafka) {
        this.kafka = kafka;
    }

    public void publish(String topic, DomainEvent event) {
        if (kafka == null) {
            log.info("[kafka 없음] {} → {}", topic, event);
            return;
        }
        kafka.send(topic, event.orderId(), event);
        log.info("발행 {} → {}", topic, event.eventId());
    }
}
