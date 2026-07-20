package metrics

import (
	"context"
	"testing"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
)

func TestMockMetricsProviderVM(t *testing.T) {
	provider := &MockMetricsProvider{
		Metrics: map[string]*ResourceMetrics{
			"vm-1": {
				ResourceID: "vm-1",
				MetricName: "Percentage CPU",
				Average:    1.5,
				IsIdle:     true,
			},
		},
	}

	metric, err := provider.GetMetrics(context.Background(), discovery.Resource{ID: "vm-1", Type: "Microsoft.Compute/virtualMachines"}, 7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if metric == nil || !metric.IsIdle {
		t.Fatalf("expected VM metric to be idle")
	}
}

func TestMockMetricsProviderStorage(t *testing.T) {
	provider := &MockMetricsProvider{
		Metrics: map[string]*ResourceMetrics{
			"st-1": {
				ResourceID: "st-1",
				MetricName: "Transactions",
				Average:    0,
				IsIdle:     true,
			},
		},
	}

	metric, err := provider.GetMetrics(context.Background(), discovery.Resource{ID: "st-1", Type: "Microsoft.Storage/storageAccounts"}, 30)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if metric == nil || !metric.IsIdle {
		t.Fatalf("expected storage metric to be idle")
	}
}
