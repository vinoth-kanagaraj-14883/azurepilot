package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/spf13/cobra"

	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/cost"
	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/discovery"
	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/metrics"
	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/report"
	"github.com/vinoth-kanagaraj-14883/azurepilot/cloud-janitor/internal/rules"
)

// Phase 1: DRY RUN ONLY - No stop/delete/resize actions are performed against Azure resources.
// All output is read-only reports and dashboard visualization.
// Phase 2 (stop/deallocate VMs, delete orphaned resources) and Phase 3 (AI recommendations)
// are out of scope for this implementation.

func main() {
	root := &cobra.Command{
		Use:   "janitor",
		Short: "Cloud Janitor dry-run FinOps scanner for Azure",
	}

	root.AddCommand(newScanCommand())
	root.AddCommand(newServeCommand())

	if err := root.Execute(); err != nil {
		log.Fatal(err)
	}
}

func newScanCommand() *cobra.Command {
	var configPath string
	var subscriptions []string
	var outputDir string
	var lookbackDays int
	var logLevel string

	cmd := &cobra.Command{
		Use:   "scan",
		Short: "Scan Azure resources and generate a dry-run waste report",
		RunE: func(cmd *cobra.Command, args []string) error {
			_ = logLevel
			subscriptions = normalizeSubscriptions(subscriptions)
			if len(subscriptions) == 0 {
				return fmt.Errorf("at least one subscription must be supplied with --subscriptions")
			}

			ruleConfig, err := rules.LoadConfig(configPath)
			if err != nil {
				return fmt.Errorf("load config: %w", err)
			}

			cred, err := azidentity.NewDefaultAzureCredential(nil)
			if err != nil {
				return fmt.Errorf("create azure credential: %w", err)
			}

			ctx := context.Background()
			discoverer := discovery.NewAzureDiscoverer(cred)
			metricsProvider := metrics.NewAzureMetricsProvider(cred)
			costProvider := cost.NewAzureCostProvider(cred)
			scoring := rules.NewScoringEngine(*ruleConfig)

			resources, err := discoverer.Discover(ctx, subscriptions)
			if err != nil {
				return fmt.Errorf("discover resources: %w", err)
			}

			for i := range resources {
				resourceLookback := lookbackDays
				if strings.EqualFold(resources[i].Type, "Microsoft.Storage/storageAccounts") {
					resourceLookback = ruleConfig.StorageLookbackDays
				}
				metricResult, err := metricsProvider.GetMetrics(ctx, resources[i], resourceLookback)
				if err != nil {
					resources[i].Reasons = append(resources[i].Reasons, fmt.Sprintf("metrics unavailable: %v", err))
					continue
				}
				if metricResult != nil {
					resources[i].IsIdle = metricResult.IsIdle
				}
			}

			costsByKey := map[string]map[string]cost.ResourceCost{}
			for _, resource := range resources {
				if resource.SubscriptionID == "" || resource.ResourceGroup == "" {
					continue
				}
				key := resource.SubscriptionID + "|" + strings.ToLower(resource.ResourceGroup)
				if _, ok := costsByKey[key]; ok {
					continue
				}
				groupCosts, err := costProvider.GetCost(ctx, resource.SubscriptionID, resource.ResourceGroup)
				if err != nil {
					return fmt.Errorf("get cost for %s/%s: %w", resource.SubscriptionID, resource.ResourceGroup, err)
				}
				mapped := make(map[string]cost.ResourceCost, len(groupCosts))
				for _, item := range groupCosts {
					mapped[strings.ToLower(item.ResourceID)] = item
				}
				costsByKey[key] = mapped
			}

			for i := range resources {
				key := resources[i].SubscriptionID + "|" + strings.ToLower(resources[i].ResourceGroup)
				if groupCosts, ok := costsByKey[key]; ok {
					if item, ok := groupCosts[strings.ToLower(resources[i].ID)]; ok {
						resources[i].Cost = item.Cost
					}
				}
				scoring.Score(&resources[i])
			}

			reportData := report.Generate(resources, subscriptions)
			reportPath, err := report.Save(reportData, outputDir)
			if err != nil {
				return fmt.Errorf("save report: %w", err)
			}

			report.PrintSummary(reportData)
			fmt.Printf("Report saved to %s\n", reportPath)
			return nil
		},
	}

	cmd.Flags().StringVar(&configPath, "config", "config/rules.json", "Path to rules configuration file")
	cmd.Flags().StringSliceVar(&subscriptions, "subscriptions", nil, "Azure subscription IDs (repeat flag or provide comma-separated values)")
	cmd.Flags().StringVar(&outputDir, "output", "output/", "Directory to save generated report")
	cmd.Flags().IntVar(&lookbackDays, "lookback-days", 7, "Metric lookback period in days")
	cmd.Flags().StringVar(&logLevel, "log-level", "info", "Log verbosity level")
	return cmd
}

func newServeCommand() *cobra.Command {
	var reportPath string
	var port int

	cmd := &cobra.Command{
		Use:   "serve",
		Short: "Serve the dashboard and a generated report",
		RunE: func(cmd *cobra.Command, args []string) error {
			if reportPath == "" {
				return fmt.Errorf("--report is required")
			}
			staticDir, err := resolveDashboardDir()
			if err != nil {
				return err
			}

			reportBytes, err := os.ReadFile(reportPath)
			if err != nil {
				return fmt.Errorf("read report: %w", err)
			}
			var pretty json.RawMessage
			if err := json.Unmarshal(reportBytes, &pretty); err != nil {
				return fmt.Errorf("report is not valid JSON: %w", err)
			}

			mux := http.NewServeMux()
			mux.HandleFunc("/api/report", func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write(reportBytes)
			})
			mux.Handle("/", http.FileServer(http.Dir(staticDir)))

			addr := fmt.Sprintf(":%d", port)
			fmt.Printf("Dashboard available at http://localhost:%d\n", port)
			return http.ListenAndServe(addr, mux)
		},
	}

	cmd.Flags().StringVar(&reportPath, "report", "", "Path to a generated report JSON file")
	cmd.Flags().IntVar(&port, "port", 8080, "Port for the local dashboard server")
	_ = cmd.MarkFlagRequired("report")
	return cmd
}

func normalizeSubscriptions(input []string) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(input))
	for _, item := range input {
		parts := strings.Split(item, ",")
		for _, part := range parts {
			trimmed := strings.TrimSpace(part)
			if trimmed == "" {
				continue
			}
			if _, ok := seen[trimmed]; ok {
				continue
			}
			seen[trimmed] = struct{}{}
			result = append(result, trimmed)
		}
	}
	sort.Strings(result)
	return result
}

func resolveDashboardDir() (string, error) {
	candidates := []string{
		filepath.Join("dashboard", "build"),
		filepath.Join("dashboard", "dist"),
		filepath.Join("dashboard", "public"),
	}
	for _, candidate := range candidates {
		info, err := os.Stat(candidate)
		if err == nil && info.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("dashboard assets not found; expected dashboard/build, dashboard/dist, or dashboard/public")
}
