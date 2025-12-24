package models

import "time"

// VolumeInfo represents information about a Docker volume in a Compose project
type VolumeInfo struct {
	Name        string `json:"name"`
	Service     string `json:"service"`
	Type        string `json:"type"` // "named" or "bind"
	Source      string `json:"source"`
	Target      string `json:"target"`
	IsExternal  bool   `json:"is_external"`
	ComposeName string `json:"compose_name"` // Full name with project prefix
}

// BackupMetadata contains metadata about a backup archive
type BackupMetadata struct {
	Timestamp   string         `json:"timestamp"`
	Project     string         `json:"project"`
	ComposeFile string         `json:"compose_file"`
	Volumes     []VolumeBackup `json:"volumes"`
}

// VolumeBackup represents a backed up volume in the metadata
type VolumeBackup struct {
	Name        string `json:"name"`
	Service     string `json:"service"`
	Target      string `json:"target"`
	IsExternal  bool   `json:"is_external"`
	ArchivePath string `json:"archive_path"` // Path in the backup archive
}

// BackupOptions contains options for backup operation
type BackupOptions struct {
	ComposeFile     string
	OutputDir       string
	Compress        bool
	VolumesToBackup []string // Empty means all volumes
	SSHTarget       string   // Format: user@host:path
}

// RestoreOptions contains options for restore operation
type RestoreOptions struct {
	BackupPath       string
	VolumesToRestore []string // Empty means all volumes
	Force            bool     // Override existing volumes
}

// GenerateTimestamp returns a timestamp string in the format YYYYMMDD_HHMMSS
func GenerateTimestamp() string {
	return time.Now().Format("20060102_150405")
}
