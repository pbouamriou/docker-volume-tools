package main

import (
	"fmt"
	"os"
	"path/filepath"
	"text/tabwriter"

	"github.com/pbouamriou/docker-volume-tools/internal/backup"
	"github.com/pbouamriou/docker-volume-tools/internal/compose"
	"github.com/pbouamriou/docker-volume-tools/internal/restore"
	"github.com/pbouamriou/docker-volume-tools/pkg/models"
	"github.com/spf13/cobra"
)

var (
	// Version information
	Version = "0.2.0"
	Commit  = "dev"
)

func main() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

var rootCmd = &cobra.Command{
	Use:   "dvtools",
	Short: "Docker Volume Tools - Backup and restore Docker Compose volumes",
	Long: `Docker Volume Tools (dvtools) provides commands to manage backups of Docker volumes
associated with Docker Compose projects. It helps you save and restore your data volumes
while maintaining their associations with specific services.`,
	Version: fmt.Sprintf("%s (commit: %s)", Version, Commit),
}

// List command
var listCmd = &cobra.Command{
	Use:   "list <compose-file>",
	Short: "List all volumes defined in a Docker Compose project",
	Long: `Analyzes your Docker Compose file and shows:
- Volume names and their associated services
- Volume types (named volumes vs bind mounts)
- External volume status`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		composeFile := args[0]

		// Parse compose file
		volumes, err := compose.ParseComposeFile(composeFile)
		if err != nil {
			return fmt.Errorf("failed to parse compose file: %w", err)
		}

		if len(volumes) == 0 {
			fmt.Println("No volumes found in the compose file.")
			return nil
		}

		// Create table
		w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', tabwriter.TabIndent)
		fmt.Println("\nVolumes found in compose file:")
		fmt.Fprintln(w, "VOLUME\tSERVICE\tTYPE\tMOUNT POINT\tEXTERNAL")
		fmt.Fprintln(w, "------\t-------\t----\t-----------\t--------")

		// Add rows
		for _, vol := range volumes {
			external := "No"
			if vol.IsExternal {
				external = "Yes"
			}
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n",
				vol.Name,
				vol.Service,
				vol.Type,
				vol.Target,
				external,
			)
		}
		w.Flush()

		// Summary
		namedCount := 0
		bindCount := 0
		for _, vol := range volumes {
			if vol.Type == "named" {
				namedCount++
			} else {
				bindCount++
			}
		}

		fmt.Println("\nSummary:")
		fmt.Printf("- Named volumes: %d\n", namedCount)
		fmt.Printf("- Bind mounts: %d\n", bindCount)
		fmt.Printf("- Total: %d\n", len(volumes))

		return nil
	},
}

// Backup command
var (
	backupOutputDir string
	backupCompress  bool
	backupVolumes   []string
	backupSSHTarget string
)

var backupCmd = &cobra.Command{
	Use:   "backup <compose-file>",
	Short: "Backup all volumes from a Docker Compose project",
	Long: `Creates backups of all volumes defined in your Docker Compose file:
- Automatically detects all volumes in the compose file
- Creates consistent backups of each volume
- Maintains service associations
- Includes volume metadata and configurations
- Preserves symbolic links correctly
- Supports direct SSH transfer with --ssh-target option`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		composeFile, err := filepath.Abs(args[0])
		if err != nil {
			return fmt.Errorf("invalid compose file path: %w", err)
		}

		// Show volumes that will be backed up
		volumes, err := compose.ParseComposeFile(composeFile)
		if err != nil {
			return fmt.Errorf("failed to parse compose file: %w", err)
		}

		// Filter if specific volumes requested
		if len(backupVolumes) > 0 {
			filtered := make([]models.VolumeInfo, 0)
			for _, vol := range volumes {
				for _, name := range backupVolumes {
					if vol.Name == name {
						filtered = append(filtered, vol)
						break
					}
				}
			}
			volumes = filtered
		}

		// Filter named volumes only
		namedVolumes := make([]models.VolumeInfo, 0)
		seen := make(map[string]bool)
		for _, vol := range volumes {
			if vol.Type == "named" && !seen[vol.Name] {
				namedVolumes = append(namedVolumes, vol)
				seen[vol.Name] = true
			}
		}

		if len(namedVolumes) == 0 {
			return fmt.Errorf("no named volumes to backup")
		}

		// Display table
		w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', tabwriter.TabIndent)
		fmt.Println("\nVolumes to backup:")
		fmt.Fprintln(w, "VOLUME\tSERVICE\tTYPE\tMOUNT POINT")
		fmt.Fprintln(w, "------\t-------\t----\t-----------")

		for _, vol := range namedVolumes {
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\n", vol.Name, vol.Service, vol.Type, vol.Target)
		}
		w.Flush()

		// Confirm
		if !confirmPrompt("\nProceed with backup?") {
			fmt.Println("Backup cancelled")
			return nil
		}

		// Create backup
		options := models.BackupOptions{
			ComposeFile:     composeFile,
			OutputDir:       backupOutputDir,
			Compress:        backupCompress,
			VolumesToBackup: backupVolumes,
			SSHTarget:       backupSSHTarget,
		}

		backupPath, err := backup.CreateBackup(options)
		if err != nil {
			return fmt.Errorf("backup failed: %w", err)
		}

		fmt.Println("\nBackup completed successfully!")
		if backupSSHTarget != "" {
			fmt.Printf("Backup transferred to: %s\n", backupPath)
		} else {
			fmt.Printf("Backup archive: %s\n", backupPath)
		}

		return nil
	},
}

// Restore command
var (
	restoreVolumes []string
	restoreForce   bool
)

var restoreCmd = &cobra.Command{
	Use:   "restore <backup-path>",
	Short: "Restore volumes from a backup",
	Long: `Restores previously backed up volumes:
- Validates backup integrity before restoration
- Recreates volumes with original configurations
- Restores data and metadata
- Correctly restores symbolic links
- Maintains service associations
- Supports selective restoration`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		backupPath := args[0]

		// Validate backup
		fmt.Printf("Validating backup: %s\n", backupPath)
		metadata, err := restore.ValidateBackup(backupPath)
		if err != nil {
			return fmt.Errorf("backup validation failed: %w", err)
		}

		// Filter volumes if specified
		volumesToRestore := metadata.Volumes
		if len(restoreVolumes) > 0 {
			filtered := make([]models.VolumeBackup, 0)
			for _, vol := range volumesToRestore {
				for _, name := range restoreVolumes {
					if vol.Name == name {
						filtered = append(filtered, vol)
						break
					}
				}
			}

			if len(filtered) != len(restoreVolumes) {
				return fmt.Errorf("some volumes not found in backup")
			}

			volumesToRestore = filtered
		}

		// Display table
		w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', tabwriter.TabIndent)
		fmt.Println("\nVolumes to restore:")
		fmt.Fprintln(w, "VOLUME\tSERVICE\tTARGET")
		fmt.Fprintln(w, "------\t-------\t------")

		for _, vol := range volumesToRestore {
			fmt.Fprintf(w, "%s\t%s\t%s\n", vol.Name, vol.Service, vol.Target)
		}
		w.Flush()

		// Confirm
		if !confirmPrompt("\nProceed with restore?") {
			fmt.Println("Restore cancelled")
			return nil
		}

		// Restore
		options := models.RestoreOptions{
			BackupPath:       backupPath,
			VolumesToRestore: restoreVolumes,
			Force:            restoreForce,
		}

		if err := restore.RestoreBackup(options); err != nil {
			return fmt.Errorf("restore failed: %w", err)
		}

		fmt.Println("\nRestore completed successfully!")
		return nil
	},
}

func init() {
	// Backup flags
	backupCmd.Flags().StringVarP(&backupOutputDir, "output-dir", "o", "./backups", "Directory to store backups")
	backupCmd.Flags().BoolVar(&backupCompress, "compress", true, "Enable backup compression")
	backupCmd.Flags().StringSliceVarP(&backupVolumes, "volumes", "v", nil, "Specific volumes to backup (default: all)")
	backupCmd.Flags().StringVarP(&backupSSHTarget, "ssh-target", "s", "", "SSH target for direct transfer (format: user@host:path)")

	// Restore flags
	restoreCmd.Flags().StringSliceVarP(&restoreVolumes, "volumes", "v", nil, "Specific volumes to restore (default: all)")
	restoreCmd.Flags().BoolVar(&restoreForce, "force", false, "Override existing volumes")

	// Add commands
	rootCmd.AddCommand(listCmd)
	rootCmd.AddCommand(backupCmd)
	rootCmd.AddCommand(restoreCmd)
}

// Helper function for confirmation prompts
func confirmPrompt(message string) bool {
	fmt.Print(message + " [y/N]: ")
	var response string
	fmt.Scanln(&response)
	return response == "y" || response == "Y" || response == "yes" || response == "Yes"
}
