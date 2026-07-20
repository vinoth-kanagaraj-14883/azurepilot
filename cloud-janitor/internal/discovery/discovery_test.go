package discovery

import (
	"context"
	"testing"
)

func TestMockDiscoverer(t *testing.T) {
	mock := &MockDiscoverer{
		Resources: []Resource{{ID: "resource-1", Name: "vm-one"}},
	}

	resources, err := mock.Discover(context.Background(), []string{"sub-1"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(resources) != 1 {
		t.Fatalf("expected 1 resource, got %d", len(resources))
	}
	if resources[0].ID != "resource-1" {
		t.Fatalf("expected resource ID resource-1, got %s", resources[0].ID)
	}
}
