package cost

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	armcostmanagement "github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/costmanagement/armcostmanagement/v2"
)

type ResourceCost struct {
	ResourceID    string
	ResourceGroup string
	Cost          float64
	Currency      string
	Period        string
}

type CostProvider interface {
	GetCost(ctx context.Context, subscriptionID string, resourceGroup string) ([]ResourceCost, error)
}

type AzureCostProvider struct {
	credential azcore.TokenCredential
}

type MockCostProvider struct {
	Costs  map[string][]ResourceCost
	Errors map[string]error
}

func NewAzureCostProvider(cred azcore.TokenCredential) *AzureCostProvider {
	return &AzureCostProvider{credential: cred}
}

func (p *AzureCostProvider) GetCost(ctx context.Context, subscriptionID string, resourceGroup string) ([]ResourceCost, error) {
	client, err := armcostmanagement.NewQueryClient(p.credential, nil)
	if err != nil {
		return nil, fmt.Errorf("create cost query client: %w", err)
	}

	scope := fmt.Sprintf("/subscriptions/%s/resourceGroups/%s", subscriptionID, resourceGroup)
	period := time.Now().UTC().Format("2006-01")
	timeframe := armcostmanagement.TimeframeTypeBillingMonthToDate
	queryType := armcostmanagement.ExportTypeActualCost
	costColumn := "PreTaxCost"
	resourceIDColumn := "ResourceId"
	currencyColumn := "Currency"

	definition := buildCostQueryDefinition(costColumn, resourceIDColumn, timeframe, queryType)

	result, err := client.Usage(ctx, scope, definition, nil)
	if err != nil {
		return nil, fmt.Errorf("cost query: %w", err)
	}

	return extractCostsFromQueryResult(result.QueryResult, resourceGroup, period, resourceIDColumn, costColumn, currencyColumn)
}

func buildCostQueryDefinition(costColumn, resourceIDColumn string, timeframe armcostmanagement.TimeframeType, queryType armcostmanagement.ExportType) armcostmanagement.QueryDefinition {
	return armcostmanagement.QueryDefinition{
		Type:      &queryType,
		Timeframe: &timeframe,
		Dataset: &armcostmanagement.QueryDataset{
			Granularity: nil,
			Aggregation: map[string]*armcostmanagement.QueryAggregation{
				"totalCost": {
					Name:     &costColumn,
					Function: ptr(armcostmanagement.FunctionTypeSum),
				},
			},
			Grouping: []*armcostmanagement.QueryGrouping{
				{Name: &resourceIDColumn, Type: ptr(armcostmanagement.QueryColumnTypeDimension)},
			},
		},
	}
}

func extractCostsFromQueryResult(result armcostmanagement.QueryResult, resourceGroup, period, resourceIDColumn, costColumn, currencyColumn string) ([]ResourceCost, error) {
	columnIndexes := map[string]int{}
	for index, column := range result.Properties.Columns {
		if column != nil && column.Name != nil {
			columnIndexes[strings.ToLower(*column.Name)] = index
		}
	}

	resourceIdx, ok := columnIndexes[strings.ToLower(resourceIDColumn)]
	if !ok {
		return nil, fmt.Errorf("resource id column not found in result")
	}
	currencyIdx := -1
	if idx, ok := columnIndexes[strings.ToLower(currencyColumn)]; ok {
		currencyIdx = idx
		// Some cost query responses expose billing currency under BillingCurrency instead of Currency.
	} else if idx, ok := columnIndexes[strings.ToLower("BillingCurrency")]; ok {
		currencyIdx = idx
	}
	costIdx := -1
	for name, index := range columnIndexes {
		if strings.Contains(name, strings.ToLower(costColumn)) || strings.Contains(name, "totalcost") {
			costIdx = index
			break
		}
	}
	if costIdx == -1 {
		return nil, fmt.Errorf("cost column not found in result")
	}

	costs := make([]ResourceCost, 0, len(result.Properties.Rows))
	for _, row := range result.Properties.Rows {
		costs = append(costs, ResourceCost{
			ResourceID:    stringCell(row, resourceIdx),
			ResourceGroup: resourceGroup,
			Cost:          floatCell(row, costIdx),
			Currency:      stringCell(row, currencyIdx),
			Period:        period,
		})
	}
	return costs, nil
}

func (m *MockCostProvider) GetCost(ctx context.Context, subscriptionID string, resourceGroup string) ([]ResourceCost, error) {
	_ = ctx
	key := subscriptionID + "|" + strings.ToLower(resourceGroup)
	if m.Errors != nil {
		if err, ok := m.Errors[key]; ok {
			return nil, err
		}
	}
	if m.Costs == nil {
		return nil, nil
	}
	items := m.Costs[key]
	clone := make([]ResourceCost, len(items))
	copy(clone, items)
	return clone, nil
}

func ptr[T any](value T) *T {
	return &value
}

func stringCell(row []interface{}, idx int) string {
	if idx < 0 || idx >= len(row) || row[idx] == nil {
		return ""
	}
	if value, ok := row[idx].(string); ok {
		return value
	}
	return fmt.Sprintf("%v", row[idx])
}

func floatCell(row []interface{}, idx int) float64 {
	if idx < 0 || idx >= len(row) || row[idx] == nil {
		return 0
	}
	switch value := row[idx].(type) {
	case float64:
		return value
	case float32:
		return float64(value)
	case int:
		return float64(value)
	case int32:
		return float64(value)
	case int64:
		return float64(value)
	default:
		return 0
	}
}
