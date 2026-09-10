package service

type OrderService struct {
    ID string
}

func (s *OrderService) ProcessOrder(amount float64) bool {
    if amount <= 0 {
        return false
    }
    return true
}
