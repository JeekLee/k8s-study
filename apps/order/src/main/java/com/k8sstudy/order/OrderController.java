package com.k8sstudy.order;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderRepository repository;
    private final EventPublisher publisher;

    @Value("${app.version:dev}")
    private String appVersion;

    public OrderController(OrderRepository repository, EventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    /** 어느 파드가 응답했는지 보이게 한다 — 로드밸런싱 확인용. */
    @GetMapping("/")
    public Map<String, Object> root() {
        return Map.of(
                "service", "order",
                "version", appVersion,
                "pod", hostname()
        );
    }

    @GetMapping("/orders")
    public List<Order> list() {
        return repository.findAll();
    }

    @GetMapping("/orders/{id}")
    public ResponseEntity<Order> get(@PathVariable String id) {
        return repository.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    public record CreateOrder(String sku, int qty) { }

    /**
     * 주문 생성. PENDING 으로 저장하고 order.created 를 발행한다.
     * 이후 상태 변경은 전부 이벤트로 이뤄진다.
     */
    @PostMapping("/orders")
    public ResponseEntity<Order> create(@RequestBody CreateOrder req) {
        Order order = new Order(UUID.randomUUID().toString(), req.sku(), req.qty());
        repository.save(order);
        publisher.publish("order.created",
                DomainEvent.of("order.created", order.getId(), order.getSku(), order.getQty()));
        return ResponseEntity.status(HttpStatus.CREATED).body(order);
    }

    private static String hostname() {
        try {
            return InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException e) {
            return "unknown";
        }
    }
}
