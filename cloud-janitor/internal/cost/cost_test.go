package cost

import (
	"context"
	"testing"

	armcostmanagement "github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/costmanagement/armcostmanagement/v2"
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

func TestBuildCostQueryDefinition_DoesNotGroupByCurrency(t *testing.T) {
	costColumn := "PreTaxCost"
	resourceIDColumn := "ResourceId"
	timeframe := armcostmanagement.TimeframeTypeBillingMonthToDate
	queryType := armcostmanagement.ExportTypeActualCost

	definition := buildCostQueryDefinition(costColumn, resourceIDColumn, timeframe, queryType)
	if definition.Dataset == nil {
		t.Fatal("expected dataset to be set")
	}
	if len(definition.Dataset.Grouping) != 1 {
		t.Fatalf("expected 1 grouping, got %d", len(definition.Dataset.Grouping))
	}
	if definition.Dataset.Grouping[0] == nil || definition.Dataset.Grouping[0].Name == nil {
		t.Fatal("expected grouping name to be set")
	}
	if got := *definition.Dataset.Grouping[0].Name; got != resourceIDColumn {
		t.Fatalf("expected grouping %q, got %q", resourceIDColumn, got)
	}
}

func TestExtractCostsFromQueryResult_CurrencyHandling(t *testing.T) {
	t.Run("currency column present", func(t *testing.T) {
		result := armcostmanagement.QueryResult{
			Properties: &armcostmanagement.QueryProperties{
				Columns: []*armcostmanagement.QueryColumn{
					{Name: ptr("ResourceId")},
					{Name: ptr("PreTaxCost")},
					{Name: ptr("Currency")},
				},
				Rows: [][]any{{"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1", 12.5, "USD"}},
			},
		}

		costs, err := extractCostsFromQueryResult(result, "rg", "2026-07", "ResourceId", "PreTaxCost", "Currency")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(costs) != 1 {
			t.Fatalf("expected 1 cost entry, got %d", len(costs))
		}
		if costs[0].Currency != "USD" {
			t.Fatalf("expected currency USD, got %q", costs[0].Currency)
		}
	})

	t.Run("currency column absent", func(t *testing.T) {
		result := armcostmanagement.QueryResult{
			Properties: &armcostmanagement.QueryProperties{
				Columns: []*armcostmanagement.QueryColumn{
					{Name: ptr("ResourceId")},
					{Name: ptr("PreTaxCost")},
				},
				Rows: [][]any{{"/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1", 12.5}},
			},
		}

		costs, err := extractCostsFromQueryResult(result, "rg", "2026-07", "ResourceId", "PreTaxCost", "Currency")
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(costs) != 1 {
			t.Fatalf("expected 1 cost entry, got %d", len(costs))
		}
		if costs[0].Currency != "" {
			t.Fatalf("expected empty currency when column missing, got %q", costs[0].Currency)
		}
	})

	t.Run("resource id column absent", func(t *testing.T) {
		result := armcostmanagement.QueryResult{
			Properties: &armcostmanagement.QueryProperties{
				Columns: []*armcostmanagement.QueryColumn{
					{Name: ptr("PreTaxCost")},
					{Name: ptr("Currency")},
				},
				Rows: [][]any{{12.5, "USD"}},
			},
		}

		_, err := extractCostsFromQueryResult(result, "rg", "2026-07", "ResourceId", "PreTaxCost", "Currency")
		if err == nil {
			t.Fatal("expected error when resource id column is missing")
		}
	})
}
