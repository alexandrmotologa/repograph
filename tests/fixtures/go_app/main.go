package main

import "tests/fixtures/go_app/service"

func main() {
    svc := &service.OrderService{ID: "ORD-1"}
    svc.ProcessOrder(100.0)
}
