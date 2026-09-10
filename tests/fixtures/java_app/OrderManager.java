package com.example.orders;

public interface PaymentGateway {
    boolean process(double amount);
}

public class OrderManager {
    private PaymentGateway gateway;

    public OrderManager(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public boolean executeOrder(double amount) {
        if (amount <= 0) {
            return false;
        }
        return gateway.process(amount);
    }
}
