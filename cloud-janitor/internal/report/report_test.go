package report

import (
	"strings"
	"testing"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
)

func TestGenerateReport(t *testing.T) {
	resources := []discovery.Resource{
		{Name: "vm-1", Band: "Healthy", Cost: 10, Tags: map[string]string{"owner": "alice"}},
		{Name: "vm-2", Band: "Warning", Cost: 20, Tags: map[string]string{"owner": "bob"}},
		{Name: "vm-3", Band: "Cleanup Candidate", Cost: 30, Tags: map[string]string{"owner": "bob"}},
		{Name: "vm-4", Band: "Delete Candidate", Cost: 40, Tags: map[string]string{"owner": "alice"}},
	}

	report := Generate(resources, []string{"sub-1"})

	if report.TotalResources != 4 {
		t.Fatalf("expected 4 resources, got %d", report.TotalResources)
	}
	if report.BandSummary.Healthy != 1 || report.BandSummary.Warning != 1 || report.BandSummary.CleanupCandidate != 1 || report.BandSummary.DeleteCandidate != 1 {
		t.Fatalf("unexpected band summary: %+v", report.BandSummary)
	}
	if report.EstimatedMonthlySavings != 70 {
		t.Fatalf("expected savings 70, got %v", report.EstimatedMonthlySavings)
	}
}

func TestHumanSummary(t *testing.T) {
	resources := []discovery.Resource{{Name: "vm-1", Band: "Cleanup Candidate", Cost: 15, Tags: map[string]string{"owner": "alice"}}}
	report := Generate(resources, []string{"sub-1", "sub-2"})

	summary := report.HumanSummary
	if !strings.Contains(summary, "2 subscriptions") {
		t.Fatalf("expected summary to include subscription count, got %q", summary)
	}
	if !strings.Contains(summary, "Estimated monthly savings") && !strings.Contains(strings.ToLower(summary), "estimated monthly savings") {
		t.Fatalf("expected summary to mention savings, got %q", summary)
	}
}
