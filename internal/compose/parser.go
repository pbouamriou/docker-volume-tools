package compose

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/pbouamriou/docker-volume-tools/pkg/models"
	"gopkg.in/yaml.v3"
)

// ComposeFile represents the structure of a docker-compose.yml file
type ComposeFile struct {
	Services map[string]Service      `yaml:"services"`
	Volumes  map[string]VolumeConfig `yaml:"volumes"`
}

// Service represents a service in docker-compose.yml
type Service struct {
	Volumes []interface{} `yaml:"volumes"`
}

// VolumeConfig represents volume configuration in the volumes section
type VolumeConfig struct {
	External interface{} `yaml:"external"` // Can be bool or struct
	Name     string      `yaml:"name"`
}

// VolumeMount can be either short syntax (string) or long syntax (struct)
type VolumeMount struct {
	Type   string `yaml:"type"`
	Source string `yaml:"source"`
	Target string `yaml:"target"`
}

// GetProjectName returns the project name from the compose file path.
// By default, Docker Compose uses the directory name as the project name.
func GetProjectName(composePath string) string {
	absPath, err := filepath.Abs(composePath)
	if err != nil {
		return "unknown"
	}
	return filepath.Base(filepath.Dir(absPath))
}

// ParseComposeFile parses a docker-compose.yml file and extracts volume information
func ParseComposeFile(composePath string) ([]models.VolumeInfo, error) {
	// Read the compose file
	data, err := os.ReadFile(composePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read compose file: %w", err)
	}

	// Parse YAML
	var composeFile ComposeFile
	if err := yaml.Unmarshal(data, &composeFile); err != nil {
		return nil, fmt.Errorf("failed to parse compose file: %w", err)
	}

	projectName := GetProjectName(composePath)
	var volumes []models.VolumeInfo

	// Parse volumes from services
	for serviceName, service := range composeFile.Services {
		for _, vol := range service.Volumes {
			var volumeInfo *models.VolumeInfo

			// Handle short syntax (string)
			if volStr, ok := vol.(string); ok {
				volumeInfo = parseShortSyntax(volStr, serviceName, projectName, composeFile.Volumes)
			} else if volMap, ok := vol.(map[string]interface{}); ok {
				// Handle long syntax (map)
				volumeInfo = parseLongSyntax(volMap, serviceName, projectName, composeFile.Volumes)
			}

			if volumeInfo != nil {
				volumes = append(volumes, *volumeInfo)
			}
		}
	}

	return volumes, nil
}

// parseShortSyntax parses volume short syntax (e.g., "volume_name:/path")
func parseShortSyntax(volStr, serviceName, projectName string, volumeConfigs map[string]VolumeConfig) *models.VolumeInfo {
	// Split by ':'
	parts := splitVolumeParts(volStr)
	if len(parts) < 2 {
		return nil
	}

	source := parts[0]
	target := parts[1]

	// Check if it's a named volume or bind mount
	if _, exists := volumeConfigs[source]; exists {
		// Named volume
		config := volumeConfigs[source]
		isExternal := isVolumeExternal(config)
		composeName := getComposeName(source, projectName, config)

		return &models.VolumeInfo{
			Name:        source,
			Service:     serviceName,
			Type:        "named",
			Source:      source,
			Target:      target,
			IsExternal:  isExternal,
			ComposeName: composeName,
		}
	}

	// Bind mount
	return &models.VolumeInfo{
		Name:        source,
		Service:     serviceName,
		Type:        "bind",
		Source:      source,
		Target:      target,
		IsExternal:  false,
		ComposeName: source,
	}
}

// parseLongSyntax parses volume long syntax (map with type, source, target)
func parseLongSyntax(volMap map[string]interface{}, serviceName, projectName string, volumeConfigs map[string]VolumeConfig) *models.VolumeInfo {
	volType, _ := volMap["type"].(string)
	source, _ := volMap["source"].(string)
	target, _ := volMap["target"].(string)

	if volType == "" {
		volType = "volume" // Default type
	}

	if volType == "volume" {
		// Named volume
		config := volumeConfigs[source]
		isExternal := isVolumeExternal(config)
		composeName := getComposeName(source, projectName, config)

		return &models.VolumeInfo{
			Name:        source,
			Service:     serviceName,
			Type:        "named",
			Source:      source,
			Target:      target,
			IsExternal:  isExternal,
			ComposeName: composeName,
		}
	} else if volType == "bind" {
		// Bind mount
		return &models.VolumeInfo{
			Name:        source,
			Service:     serviceName,
			Type:        "bind",
			Source:      source,
			Target:      target,
			IsExternal:  false,
			ComposeName: source,
		}
	}

	return nil
}

// splitVolumeParts splits volume string by ':' handling edge cases
func splitVolumeParts(volStr string) []string {
	var parts []string
	var current string
	escaped := false

	for _, ch := range volStr {
		if ch == '\\' && !escaped {
			escaped = true
			continue
		}
		if ch == ':' && !escaped {
			parts = append(parts, current)
			current = ""
			escaped = false
			continue
		}
		current += string(ch)
		escaped = false
	}
	if current != "" {
		parts = append(parts, current)
	}

	return parts
}

// isVolumeExternal checks if a volume is marked as external
func isVolumeExternal(config VolumeConfig) bool {
	if config.External == nil {
		return false
	}

	// Handle bool
	if external, ok := config.External.(bool); ok {
		return external
	}

	// Handle struct (external: {name: ...})
	if _, ok := config.External.(map[string]interface{}); ok {
		return true
	}

	return false
}

// getComposeName returns the full Docker volume name with project prefix
func getComposeName(volumeName, projectName string, config VolumeConfig) string {
	// If explicit name is provided, use it
	if config.Name != "" {
		return config.Name
	}

	// Otherwise, use project_volumeName convention
	return projectName + "_" + volumeName
}
