package rules

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
)

type RuleConfig struct {
	IdleCPUThresholdPercent    float64  `json:"idleCpuThresholdPercent"`
	IdleLookbackDays           int      `json:"idleLookbackDays"`
	StorageLookbackDays        int      `json:"storageLookbackDays"`
	BudgetThresholdPerResource float64  `json:"budgetThresholdPerResource"`
	ScoreExpired               int      `json:"scoreExpired"`
	ScoreIdle                  int      `json:"scoreIdle"`
	ScoreNoOwner               int      `json:"scoreNoOwner"`
	ScoreNoTags                int      `json:"scoreNoTags"`
	ScorePremiumSKU            int      `json:"scorePremiumSku"`
	ScoreOverBudget            int      `json:"scoreOverBudget"`
	PremiumSKUKeywords         []string `json:"premiumSkuKeywords"`
}

type ScoringEngine struct {
	Config RuleConfig
}

func NewScoringEngine(config RuleConfig) *ScoringEngine {
	merged := defaultConfig()
	mergeConfig(&merged, config)
	return &ScoringEngine{Config: merged}
}

func (e *ScoringEngine) Score(resource *discovery.Resource) {
	resource.Score = 0
	resource.Reasons = nil
	resource.IsExpired = false

	if isExpired(resource.Tags) {
		resource.IsExpired = true
		resource.Score += e.Config.ScoreExpired
		resource.Reasons = append(resource.Reasons, "expired based on ExpiryDate tag")
	}

	if resource.IsIdle {
		resource.Score += e.Config.ScoreIdle
		resource.Reasons = append(resource.Reasons, "idle based on resource metrics or attachment state")
	}

	owner := tagValue(resource.Tags, "owner")
	if owner == "" {
		resource.Score += e.Config.ScoreNoOwner
		resource.Reasons = append(resource.Reasons, "missing owner tag")
	}

	if len(resource.Tags) == 0 {
		resource.Score += e.Config.ScoreNoTags
		resource.Reasons = append(resource.Reasons, "resource has no tags")
	}

	if matchesPremiumKeyword(resource, e.Config.PremiumSKUKeywords) {
		resource.Score += e.Config.ScorePremiumSKU
		resource.Reasons = append(resource.Reasons, "premium SKU keyword match")
	}

	if resource.Cost > e.Config.BudgetThresholdPerResource {
		resource.Score += e.Config.ScoreOverBudget
		resource.Reasons = append(resource.Reasons, fmt.Sprintf("monthly cost %.2f exceeds threshold %.2f", resource.Cost, e.Config.BudgetThresholdPerResource))
	}

	resource.Band = e.Band(resource.Score)
}

func (e *ScoringEngine) Band(score int) string {
	switch {
	case score >= 70:
		return "Delete Candidate"
	case score >= 40:
		return "Cleanup Candidate"
	case score >= 20:
		return "Warning"
	default:
		return "Healthy"
	}
}

func LoadConfig(path string) (*RuleConfig, error) {
	payload, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read rules config: %w", err)
	}
	// Start with defaults so any omitted JSON fields retain their default values.
	cfg := defaultConfig()
	if err := json.Unmarshal(payload, &cfg); err != nil {
		return nil, fmt.Errorf("parse rules config: %w", err)
	}
	return &cfg, nil
}

func defaultConfig() RuleConfig {
	return RuleConfig{
		IdleCPUThresholdPercent:    2.0,
		IdleLookbackDays:           7,
		StorageLookbackDays:        30,
		BudgetThresholdPerResource: 1000.0,
		ScoreExpired:               40,
		ScoreIdle:                  30,
		ScoreNoOwner:               20,
		ScoreNoTags:                10,
		ScorePremiumSKU:            15,
		ScoreOverBudget:            25,
		PremiumSKUKeywords:         []string{"premium", "P1", "P2", "P3", "Standard_D", "Standard_E", "Standard_F", "Standard_G"},
	}
}

func mergeConfig(target *RuleConfig, source RuleConfig) {
	if source.IdleCPUThresholdPercent > 0 {
		target.IdleCPUThresholdPercent = source.IdleCPUThresholdPercent
	}
	if source.IdleLookbackDays > 0 {
		target.IdleLookbackDays = source.IdleLookbackDays
	}
	if source.StorageLookbackDays > 0 {
		target.StorageLookbackDays = source.StorageLookbackDays
	}
	if source.BudgetThresholdPerResource > 0 {
		target.BudgetThresholdPerResource = source.BudgetThresholdPerResource
	}
	if source.ScoreExpired > 0 {
		target.ScoreExpired = source.ScoreExpired
	}
	if source.ScoreIdle > 0 {
		target.ScoreIdle = source.ScoreIdle
	}
	if source.ScoreNoOwner > 0 {
		target.ScoreNoOwner = source.ScoreNoOwner
	}
	if source.ScoreNoTags > 0 {
		target.ScoreNoTags = source.ScoreNoTags
	}
	if source.ScorePremiumSKU > 0 {
		target.ScorePremiumSKU = source.ScorePremiumSKU
	}
	if source.ScoreOverBudget > 0 {
		target.ScoreOverBudget = source.ScoreOverBudget
	}
	if len(source.PremiumSKUKeywords) > 0 {
		target.PremiumSKUKeywords = append([]string(nil), source.PremiumSKUKeywords...)
	}
}

func isExpired(tags map[string]string) bool {
	expiry := firstNonEmpty(
		tagValue(tags, "ExpiryDate"),
		tagValue(tags, "expiryDate"),
		tagValue(tags, "expiry"),
	)
	if expiry == "" {
		return false
	}
	for _, layout := range []string{time.RFC3339, "2006-01-02", "02-01-2006"} {
		parsed, err := time.Parse(layout, expiry)
		if err == nil {
			now := time.Now().UTC().Truncate(24 * time.Hour)
			return parsed.UTC().Before(now)
		}
	}
	return false
}

func matchesPremiumKeyword(resource *discovery.Resource, keywords []string) bool {
	lookup := strings.ToLower(resource.Name + " " + resource.Type)
	for _, keyword := range keywords {
		if strings.Contains(lookup, strings.ToLower(keyword)) {
			return true
		}
	}
	return false
}

func tagValue(tags map[string]string, key string) string {
	if len(tags) == 0 {
		return ""
	}
	for existingKey, value := range tags {
		if strings.EqualFold(existingKey, key) && strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
