package discovery

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/resourcegraph/armresourcegraph"
)

type Resource struct {
	ID             string
	Name           string
	Type           string
	SubscriptionID string
	ResourceGroup  string
	Region         string
	Tags           map[string]string
	Properties     map[string]interface{}
	PowerState     string
	Cost           float64
	Score          int
	Band           string
	Reasons        []string
	IsExpired      bool
	IsIdle         bool
}

type Discoverer interface {
	Discover(ctx context.Context, subscriptionIDs []string) ([]Resource, error)
}

type AzureDiscoverer struct {
	credential azcore.TokenCredential
}

type MockDiscoverer struct {
	Resources []Resource
	Err       error
}

func NewAzureDiscoverer(cred azcore.TokenCredential) *AzureDiscoverer {
	return &AzureDiscoverer{credential: cred}
}

func (d *AzureDiscoverer) Discover(ctx context.Context, subscriptionIDs []string) ([]Resource, error) {
	if len(subscriptionIDs) == 0 {
		return nil, fmt.Errorf("subscriptionIDs cannot be empty")
	}

	client, err := armresourcegraph.NewClient(d.credential, nil)
	if err != nil {
		return nil, fmt.Errorf("create resource graph client: %w", err)
	}

	query := "Resources | project id, name, type, subscriptionId, resourceGroup, location, tags, properties"
	subscriptions := make([]*string, 0, len(subscriptionIDs))
	for _, subscriptionID := range subscriptionIDs {
		subID := subscriptionID
		subscriptions = append(subscriptions, &subID)
	}

	response, err := client.Resources(ctx, armresourcegraph.QueryRequest{
		Subscriptions: subscriptions,
		Query:         &query,
	}, nil)
	if err != nil {
		return nil, fmt.Errorf("resource graph query failed: %w", err)
	}

	payload, err := json.Marshal(response.Data)
	if err != nil {
		return nil, fmt.Errorf("marshal resource graph response: %w", err)
	}

	var rows []map[string]interface{}
	if err := json.Unmarshal(payload, &rows); err != nil {
		return nil, fmt.Errorf("unmarshal resource graph rows: %w", err)
	}

	resources := make([]Resource, 0, len(rows))
	for _, row := range rows {
		tags := toStringMap(row["tags"])
		owner := firstNonEmpty(tags["owner"], tags["Owner"])
		if owner != "" {
			tags["owner"] = owner
		}

		properties := toAnyMap(row["properties"])
		resources = append(resources, Resource{
			ID:             toString(row["id"]),
			Name:           toString(row["name"]),
			Type:           toString(row["type"]),
			SubscriptionID: toString(row["subscriptionId"]),
			ResourceGroup:  toString(row["resourceGroup"]),
			Region:         toString(row["location"]),
			Tags:           tags,
			Properties:     properties,
			PowerState:     extractPowerState(properties),
		})
	}

	return resources, nil
}

func (m *MockDiscoverer) Discover(ctx context.Context, subscriptionIDs []string) ([]Resource, error) {
	_ = ctx
	_ = subscriptionIDs
	if m.Err != nil {
		return nil, m.Err
	}
	cloned := make([]Resource, len(m.Resources))
	copy(cloned, m.Resources)
	return cloned, nil
}

func extractPowerState(properties map[string]interface{}) string {
	if state := nestedString(properties, "extended", "instanceView", "powerState", "displayStatus"); state != "" {
		return state
	}
	if state := nestedString(properties, "provisioningState"); state != "" {
		return state
	}
	return ""
}

func nestedString(root map[string]interface{}, keys ...string) string {
	current := interface{}(root)
	for _, key := range keys {
		m, ok := current.(map[string]interface{})
		if !ok {
			return ""
		}
		current = m[key]
	}
	return toString(current)
}

func toString(value interface{}) string {
	switch v := value.(type) {
	case string:
		return v
	case fmt.Stringer:
		return v.String()
	default:
		if value == nil {
			return ""
		}
		return strings.TrimSpace(fmt.Sprintf("%v", value))
	}
}

func toStringMap(value interface{}) map[string]string {
	result := map[string]string{}
	if value == nil {
		return result
	}
	switch v := value.(type) {
	case map[string]string:
		for key, val := range v {
			result[key] = val
		}
	case map[string]interface{}:
		for key, val := range v {
			result[key] = toString(val)
		}
	}
	return result
}

func toAnyMap(value interface{}) map[string]interface{} {
	if value == nil {
		return map[string]interface{}{}
	}
	if typed, ok := value.(map[string]interface{}); ok {
		return typed
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return map[string]interface{}{}
	}
	result := map[string]interface{}{}
	if err := json.Unmarshal(payload, &result); err != nil {
		return map[string]interface{}{}
	}
	return result
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
