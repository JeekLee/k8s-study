package com.k8sstudy.payment;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentController {

    private final PaymentRepository repository;

    @Value("${app.version:dev}")
    private String appVersion;

    public PaymentController(PaymentRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/")
    public Map<String, Object> root() {
        return Map.of("service", "payment", "version", appVersion, "pod", hostname());
    }

    @GetMapping("/payments")
    public List<Payment> list() {
        return repository.findAll();
    }

    private static String hostname() {
        try {
            return InetAddress.getLocalHost().getHostName();
        } catch (UnknownHostException e) {
            return "unknown";
        }
    }
}
