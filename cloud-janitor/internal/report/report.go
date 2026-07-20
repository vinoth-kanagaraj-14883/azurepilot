package report

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
)

type BandSummary struct {
	Healthy          int `json:"healthy"`
	Warning          int `json:"warning"`
	CleanupCandidate int `json:"cleanupCandidate"`
	DeleteCandidate  int `json:"deleteCandidate"`
}

type WasteByOwner struct {
	Owner         string  `json:"owner"`
	TotalCost     float64 `json:"totalCost"`
	ResourceCount int     `json:"resourceCount"`
}

type Report struct {
	DryRun                  bool                 `json:"dryRun"`
	GeneratedAt             time.Time            `json:"generatedAt"`
	SubscriptionIDs         []string             `json:"subscriptionIds"`
	TotalResources          int                  `json:"totalResources"`
	BandSummary             BandSummary          `json:"bandSummary"`
	EstimatedMonthlySavings float64              `json:"estimatedMonthlySavings"`
	TopWasteByOwner         []WasteByOwner       `json:"topWasteByOwner"`
	Resources               []discovery.Resource `json:"resources"`
	HumanSummary            string               `json:"humanSummary"`
}

func Generate(resources []discovery.Resource, subscriptionIDs []string) *Report {
	summary := BandSummary{}
	ownerTotals := map[string]*WasteByOwner{}
	estimatedSavings := 0.0

	for _, resource := range resources {
		switch resource.Band {
		case "Healthy":
			summary.Healthy++
		case "Warning":
			summary.Warning++
		case "Cleanup Candidate":
			summary.CleanupCandidate++
			estimatedSavings += resource.Cost
		case "Delete Candidate":
			summary.DeleteCandidate++
			estimatedSavings += resource.Cost
		}

		if resource.Band == "Healthy" || resource.Cost <= 0 {
			continue
		}
		owner := ownerFromTags(resource.Tags)
		if _, ok := ownerTotals[owner]; !ok {
			ownerTotals[owner] = &WasteByOwner{Owner: owner}
		}
		ownerTotals[owner].TotalCost += resource.Cost
		ownerTotals[owner].ResourceCount++
	}

	owners := make([]WasteByOwner, 0, len(ownerTotals))
	for _, owner := range ownerTotals {
		owners = append(owners, *owner)
	}
	sort.Slice(owners, func(i, j int) bool {
		if owners[i].TotalCost == owners[j].TotalCost {
			return owners[i].Owner < owners[j].Owner
		}
		return owners[i].TotalCost > owners[j].TotalCost
	})
	if len(owners) > 5 {
		owners = owners[:5]
	}

	report := &Report{
		DryRun:                  true,
		GeneratedAt:             time.Now().UTC(),
		SubscriptionIDs:         append([]string(nil), subscriptionIDs...),
		TotalResources:          len(resources),
		BandSummary:             summary,
		EstimatedMonthlySavings: estimatedSavings,
		TopWasteByOwner:         owners,
		Resources:               append([]discovery.Resource(nil), resources...),
	}
	report.HumanSummary = buildHumanSummary(report)
	return report
}

func Save(report *Report, outputDir string) (string, error) {
	if outputDir == "" {
		outputDir = "output"
	}
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return "", fmt.Errorf("create output directory: %w", err)
	}
	path := filepath.Join(outputDir, fmt.Sprintf("report-%s.json", report.GeneratedAt.Format("2006-01-02")))
	payload, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal report: %w", err)
	}
	if err := os.WriteFile(path, payload, 0o644); err != nil {
		return "", fmt.Errorf("write report: %w", err)
	}
	return path, nil
}

func PrintSummary(report *Report) {
	fmt.Printf("Cloud Janitor Phase 1 (Dry Run)\n")
	fmt.Printf("Resources scanned: %d\n", report.TotalResources)
	fmt.Printf("Healthy: %d | Warning: %d | Cleanup Candidate: %d | Delete Candidate: %d\n",
		report.BandSummary.Healthy,
		report.BandSummary.Warning,
		report.BandSummary.CleanupCandidate,
		report.BandSummary.DeleteCandidate,
	)
	fmt.Printf("Estimated monthly savings: $%.2f\n", report.EstimatedMonthlySavings)
}

func buildHumanSummary(report *Report) string {
	return fmt.Sprintf(
		"Dry-run scan across %d subscriptions found %d resources: %d healthy, %d warning, %d cleanup candidates, and %d delete candidates. Estimated monthly savings from cleanup/delete candidates is $%.2f.",
		len(report.SubscriptionIDs),
		report.TotalResources,
		report.BandSummary.Healthy,
		report.BandSummary.Warning,
		report.BandSummary.CleanupCandidate,
		report.BandSummary.DeleteCandidate,
		report.EstimatedMonthlySavings,
	)
}

func ownerFromTags(tags map[string]string) string {
	for key, value := range tags {
		if strings.EqualFold(key, "owner") && strings.TrimSpace(value) != "" {
			return value
		}
	}
	return "unassigned"
}
