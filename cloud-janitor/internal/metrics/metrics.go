package metrics

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
)

type ResourceMetrics struct {
	ResourceID string
	MetricName string
	Average    float64
	Minimum    float64
	Maximum    float64
	IsIdle     bool
}

type MetricsProvider interface {
	GetMetrics(ctx context.Context, resource discovery.Resource, lookbackDays int) (*ResourceMetrics, error)
}

type AzureMetricsProvider struct {
	credential azcore.TokenCredential
}

type MockMetricsProvider struct {
	Metrics map[string]*ResourceMetrics
	Errors  map[string]error
}

func NewAzureMetricsProvider(cred azcore.TokenCredential) *AzureMetricsProvider {
	return &AzureMetricsProvider{credential: cred}
}

func (p *AzureMetricsProvider) GetMetrics(ctx context.Context, resource discovery.Resource, lookbackDays int) (*ResourceMetrics, error) {
	switch resource.Type {
	case "Microsoft.Compute/virtualMachines":
		return p.fetchAzureMetric(ctx, resource, lookbackDays, "Percentage CPU", "Average", func(avg, _, _ float64) bool {
			return avg < 2.0
		})
	case "Microsoft.Web/sites":
		return p.fetchAzureMetric(ctx, resource, lookbackDays, "Requests", "Total", func(avg, min, max float64) bool {
			return avg == 0 && min == 0 && max == 0
		})
	case "Microsoft.Storage/storageAccounts":
		return p.fetchAzureMetric(ctx, resource, 30, "Transactions", "Total", func(avg, min, max float64) bool {
			return avg == 0 && min == 0 && max == 0
		})
	case "Microsoft.Compute/disks":
		state := strings.EqualFold(toString(resource.Properties["diskState"]), "Unattached")
		return &ResourceMetrics{ResourceID: resource.ID, MetricName: "diskState", IsIdle: state}, nil
	case "Microsoft.Network/publicIPAddresses":
		ipConfig := resource.Properties["ipConfiguration"]
		isEmpty := ipConfig == nil
		if list, ok := ipConfig.([]interface{}); ok {
			isEmpty = len(list) == 0
		}
		if m, ok := ipConfig.(map[string]interface{}); ok {
			isEmpty = len(m) == 0
		}
		return &ResourceMetrics{ResourceID: resource.ID, MetricName: "ipConfiguration", IsIdle: isEmpty}, nil
	case "Microsoft.Network/loadBalancers":
		pools, ok := resource.Properties["backendAddressPools"].([]interface{})
		isIdle := !ok || len(pools) == 0
		return &ResourceMetrics{ResourceID: resource.ID, MetricName: "backendAddressPools", IsIdle: isIdle}, nil
	default:
		return nil, nil
	}
}

func (m *MockMetricsProvider) GetMetrics(ctx context.Context, resource discovery.Resource, lookbackDays int) (*ResourceMetrics, error) {
	_ = ctx
	_ = lookbackDays
	if m.Errors != nil {
		if err, ok := m.Errors[resource.ID]; ok {
			return nil, err
		}
	}
	if m.Metrics == nil {
		return nil, nil
	}
	if metric, ok := m.Metrics[resource.ID]; ok {
		copyMetric := *metric
		return &copyMetric, nil
	}
	return nil, nil
}

func (p *AzureMetricsProvider) fetchAzureMetric(ctx context.Context, resource discovery.Resource, lookbackDays int, metricName, aggregation string, idleFn func(float64, float64, float64) bool) (*ResourceMetrics, error) {
	client, err := armmonitor.NewMetricsClient(resource.SubscriptionID, p.credential, nil)
	if err != nil {
		return nil, fmt.Errorf("create metrics client: %w", err)
	}

	end := time.Now().UTC()
	start := end.AddDate(0, 0, -lookbackDays)
	timespan := fmt.Sprintf("%s/%s", start.Format(time.RFC3339), end.Format(time.RFC3339))
	interval := "PT1H"
	metric := metricName
	agg := aggregation

	resp, err := client.List(ctx, resource.ID, &armmonitor.MetricsClientListOptions{
		Metricnames: &metric,
		Aggregation: &agg,
		Timespan:    &timespan,
		Interval:    &interval,
	})
	if err != nil {
		return nil, fmt.Errorf("fetch %s metrics: %w", metricName, err)
	}

	average, minimum, maximum := aggregateMetricResponse(resp.Value)
	return &ResourceMetrics{
		ResourceID: resource.ID,
		MetricName: metricName,
		Average:    average,
		Minimum:    minimum,
		Maximum:    maximum,
		IsIdle:     idleFn(average, minimum, maximum),
	}, nil
}

func aggregateMetricResponse(metrics []*armmonitor.Metric) (float64, float64, float64) {
	var totalAverage float64
	var totalMinimum float64
	var totalMaximum float64
	var averageSamples float64
	var minSet bool
	var maxSet bool

	for _, metric := range metrics {
		for _, series := range metric.Timeseries {
			for _, point := range series.Data {
				if point.Average != nil {
					totalAverage += *point.Average
					averageSamples++
				}
				if point.Total != nil {
					totalAverage += *point.Total
					averageSamples++
				}
				if point.Minimum != nil {
					if !minSet || *point.Minimum < totalMinimum {
						totalMinimum = *point.Minimum
						minSet = true
					}
				}
				if point.Maximum != nil {
					if !maxSet || *point.Maximum > totalMaximum {
						totalMaximum = *point.Maximum
						maxSet = true
					}
				}
			}
		}
	}

	average := 0.0
	if averageSamples > 0 {
		average = totalAverage / averageSamples
	}
	return average, totalMinimum, totalMaximum
}

func toString(value interface{}) string {
	if value == nil {
		return ""
	}
	if s, ok := value.(string); ok {
		return s
	}
	return fmt.Sprintf("%v", value)
}
