package rules

import (
	"testing"
	"time"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
)

func testConfig() RuleConfig {
	return RuleConfig{
		BudgetThresholdPerResource: 1000,
		ScoreExpired:               40,
		ScoreIdle:                  30,
		ScoreNoOwner:               20,
		ScoreNoTags:                10,
		ScorePremiumSKU:            15,
		ScoreOverBudget:            25,
		PremiumSKUKeywords:         []string{"premium", "P1"},
	}
}

func TestScoreExpired(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{Tags: map[string]string{
		"ExpiryDate": time.Now().AddDate(0, 0, -1).Format("2006-01-02"),
		"owner":      "alice",
	}}

	engine.Score(resource)

	if resource.Score != 40 {
		t.Fatalf("expected score 40, got %d", resource.Score)
	}
}

func TestScoreIdle(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{Tags: map[string]string{"owner": "alice"}, IsIdle: true}

	engine.Score(resource)

	if resource.Score != 30 {
		t.Fatalf("expected score 30, got %d", resource.Score)
	}
}

func TestScoreNoOwner(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{Tags: map[string]string{"env": "dev"}}

	engine.Score(resource)

	if resource.Score != 20 {
		t.Fatalf("expected score 20, got %d", resource.Score)
	}
}

func TestScoreNoTags(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{}

	engine.Score(resource)

	if resource.Score != 30 {
		t.Fatalf("expected score 30, got %d", resource.Score)
	}
}

func TestScorePremiumSKU(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{Name: "premium-db", Tags: map[string]string{"owner": "alice"}}

	engine.Score(resource)

	if resource.Score != 15 {
		t.Fatalf("expected score 15, got %d", resource.Score)
	}
}

func TestScoreOverBudget(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{Cost: 1500, Tags: map[string]string{"owner": "alice"}}

	engine.Score(resource)

	if resource.Score != 25 {
		t.Fatalf("expected score 25, got %d", resource.Score)
	}
}

func TestScoreCombined(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	resource := &discovery.Resource{
		Name:   "premium-db",
		Cost:   1501,
		IsIdle: true,
		Tags:   map[string]string{"ExpiryDate": time.Now().AddDate(0, 0, -1).Format("2006-01-02")},
	}

	engine.Score(resource)

	if resource.Score != 130 {
		t.Fatalf("expected score 130, got %d", resource.Score)
	}
	if resource.Band != "Delete Candidate" {
		t.Fatalf("expected Delete Candidate, got %s", resource.Band)
	}
}

func TestBandHealthy(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	if band := engine.Band(19); band != "Healthy" {
		t.Fatalf("expected Healthy, got %s", band)
	}
}

func TestBandWarning(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	if band := engine.Band(20); band != "Warning" {
		t.Fatalf("expected Warning, got %s", band)
	}
}

func TestBandCleanupCandidate(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	if band := engine.Band(40); band != "Cleanup Candidate" {
		t.Fatalf("expected Cleanup Candidate, got %s", band)
	}
}

func TestBandDeleteCandidate(t *testing.T) {
	engine := NewScoringEngine(testConfig())
	if band := engine.Band(70); band != "Delete Candidate" {
		t.Fatalf("expected Delete Candidate, got %s", band)
	}
}
