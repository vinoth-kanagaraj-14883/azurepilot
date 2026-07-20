package cost

import (
	"context"
	"testing"
)

func TestMockCostProvider(t *testing.T) {
	provider := &MockCostProvider{
		Costs: map[string][]ResourceCost{
			"sub-1|rg-1": {{ResourceID: "res-1", ResourceGroup: "rg-1", Cost: 123.45, Currency: "USD", Period: "2026-07"}},
		},
	}

	costs, err := provider.GetCost(context.Background(), "sub-1", "rg-1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(costs) != 1 {
		t.Fatalf("expected 1 cost entry, got %d", len(costs))
	}
	if costs[0].Cost != 123.45 {
		t.Fatalf("expected cost 123.45, got %v", costs[0].Cost)
	}
}
