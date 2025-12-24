package backup

import (
	"archive/tar"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/pbouamriou/docker-volume-tools/internal/compose"
	"github.com/pbouamriou/docker-volume-tools/internal/docker"
	"github.com/pbouamriou/docker-volume-tools/pkg/models"
)

// CreateBackup creates a backup of Docker volumes from a compose project
func CreateBackup(options models.BackupOptions) (string, error) {
	// Parse compose file
	volumes, err := compose.ParseComposeFile(options.ComposeFile)
	if err != nil {
		return "", fmt.Errorf("failed to parse compose file: %w", err)
	}

	// Filter volumes if specified
	if len(options.VolumesToBackup) > 0 {
		volumes = filterVolumes(volumes, options.VolumesToBackup)
	}

	// Filter only named volumes and deduplicate
	namedVolumes := deduplicateVolumes(filterNamedVolumes(volumes))
	if len(namedVolumes) == 0 {
		return "", fmt.Errorf("no named volumes to backup")
	}

	// Create Docker client
	dockerClient, err := docker.NewClient()
	if err != nil {
		return "", err
	}
	defer dockerClient.Close()

	// Generate backup name
	timestamp := models.GenerateTimestamp()
	projectName := filepath.Base(strings.TrimSuffix(options.ComposeFile, filepath.Ext(options.ComposeFile)))
	backupName := fmt.Sprintf("%s_volumes_%s", projectName, timestamp)

	// Create backup directory or use SSH
	if options.SSHTarget != "" {
		return createSSHBackup(dockerClient, namedVolumes, backupName, projectName, options)
	}

	return createLocalBackup(dockerClient, namedVolumes, backupName, projectName, options)
}

// createLocalBackup creates a local backup archive
func createLocalBackup(dockerClient *docker.Client, volumes []models.VolumeInfo, backupName, projectName string, options models.BackupOptions) (string, error) {
	// Create output directory
	if err := os.MkdirAll(options.OutputDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create output directory: %w", err)
	}

	// Create temporary directory for backup
	tempDir := filepath.Join(options.OutputDir, backupName)
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create temp directory: %w", err)
	}
	defer os.RemoveAll(tempDir)

	// Create volumes subdirectory
	volumesDir := filepath.Join(tempDir, "volumes")
	if err := os.MkdirAll(volumesDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create volumes directory: %w", err)
	}

	// Backup each volume
	var volumeBackups []models.VolumeBackup
	for _, vol := range volumes {
		fmt.Printf("Backing up volume %s...\n", vol.ComposeName)

		volumeBackupDir := filepath.Join(volumesDir, vol.Name)
		if err := os.MkdirAll(volumeBackupDir, 0755); err != nil {
			return "", fmt.Errorf("failed to create volume backup dir: %w", err)
		}

		if err := backupVolume(dockerClient, vol.ComposeName, volumeBackupDir); err != nil {
			return "", fmt.Errorf("failed to backup volume %s: %w", vol.ComposeName, err)
		}

		volumeBackups = append(volumeBackups, models.VolumeBackup{
			Name:        vol.ComposeName,
			Service:     vol.Service,
			Target:      vol.Target,
			IsExternal:  vol.IsExternal,
			ArchivePath: vol.Name,
		})
	}

	// Create metadata
	metadata := models.BackupMetadata{
		Timestamp:   models.GenerateTimestamp(),
		Project:     projectName,
		ComposeFile: filepath.Base(options.ComposeFile),
		Volumes:     volumeBackups,
	}

	metadataBytes, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return "", fmt.Errorf("failed to marshal metadata: %w", err)
	}

	metadataPath := filepath.Join(tempDir, "metadata.json")
	if err := os.WriteFile(metadataPath, metadataBytes, 0644); err != nil {
		return "", fmt.Errorf("failed to write metadata: %w", err)
	}

	// Create final archive
	ext := ".tar"
	if options.Compress {
		ext = ".tar.gz"
	}
	archivePath := filepath.Join(options.OutputDir, backupName+ext)

	if err := createTarArchive(tempDir, archivePath, options.Compress); err != nil {
		return "", fmt.Errorf("failed to create archive: %w", err)
	}

	return archivePath, nil
}

// backupVolume backs up a single Docker volume to a directory
// IMPORTANT: This preserves symlinks (does NOT dereference them)
func backupVolume(dockerClient *docker.Client, volumeName, outputDir string) error {
	// Pull alpine image
	if err := dockerClient.PullImage("alpine:latest"); err != nil {
		return fmt.Errorf("failed to pull alpine image: %w", err)
	}

	// Create temporary container with volume mounted
	containerID, err := dockerClient.RunContainer(docker.ContainerConfig{
		Image: "alpine:latest",
		Name:  fmt.Sprintf("backup_%s", volumeName),
		Cmd:   []string{"sleep", "infinity"},
		Volumes: map[string]string{
			volumeName: "/volume",
		},
	})
	if err != nil {
		return err
	}
	defer dockerClient.Cleanup(containerID)

	// Copy files from container preserving symlinks
	// Use docker cp which preserves symlinks by default
	copyCmd := fmt.Sprintf("docker cp %s:/volume/. %s/", containerID, outputDir)
	if err := runCommand(copyCmd); err != nil {
		return fmt.Errorf("failed to copy volume data: %w", err)
	}

	return nil
}

// createTarArchive creates a tar archive from a directory
// CRITICAL: Preserves symlinks by detecting and storing them correctly
func createTarArchive(sourceDir, targetPath string, compress bool) error {
	// Create output file
	outFile, err := os.Create(targetPath)
	if err != nil {
		return fmt.Errorf("failed to create archive file: %w", err)
	}
	defer outFile.Close()

	// Setup compression if needed
	var writer io.Writer = outFile
	if compress {
		gzWriter := gzip.NewWriter(outFile)
		defer gzWriter.Close()
		writer = gzWriter
	}

	// Create tar writer
	tarWriter := tar.NewWriter(writer)
	defer tarWriter.Close()

	// Walk directory and add files
	return filepath.Walk(sourceDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		// Get relative path
		relPath, err := filepath.Rel(sourceDir, path)
		if err != nil {
			return err
		}

		// Skip root directory
		if relPath == "." {
			return nil
		}

		// Create tar header
		header, err := tar.FileInfoHeader(info, "")
		if err != nil {
			return fmt.Errorf("failed to create header for %s: %w", path, err)
		}
		header.Name = relPath

		// Handle symlinks specially
		if info.Mode()&os.ModeSymlink != 0 {
			// Read the symlink target
			linkTarget, err := os.Readlink(path)
			if err != nil {
				return fmt.Errorf("failed to read symlink %s: %w", path, err)
			}
			header.Typeflag = tar.TypeSymlink
			header.Linkname = linkTarget
			header.Size = 0

			// Write header only (no file content for symlinks)
			if err := tarWriter.WriteHeader(header); err != nil {
				return fmt.Errorf("failed to write symlink header: %w", err)
			}
			fmt.Printf("  Preserved symlink: %s -> %s\n", relPath, linkTarget)
			return nil
		}

		// Write header
		if err := tarWriter.WriteHeader(header); err != nil {
			return fmt.Errorf("failed to write header: %w", err)
		}

		// If it's a file, write its content
		if info.Mode().IsRegular() {
			file, err := os.Open(path)
			if err != nil {
				return fmt.Errorf("failed to open file %s: %w", path, err)
			}
			defer file.Close()

			if _, err := io.Copy(tarWriter, file); err != nil {
				return fmt.Errorf("failed to write file %s: %w", path, err)
			}
		}

		return nil
	})
}

// Helper functions

func filterVolumes(volumes []models.VolumeInfo, names []string) []models.VolumeInfo {
	nameMap := make(map[string]bool)
	for _, name := range names {
		nameMap[name] = true
	}

	var filtered []models.VolumeInfo
	for _, vol := range volumes {
		if nameMap[vol.Name] {
			filtered = append(filtered, vol)
		}
	}
	return filtered
}

func filterNamedVolumes(volumes []models.VolumeInfo) []models.VolumeInfo {
	var named []models.VolumeInfo
	for _, vol := range volumes {
		if vol.Type == "named" {
			named = append(named, vol)
		}
	}
	return named
}

func deduplicateVolumes(volumes []models.VolumeInfo) []models.VolumeInfo {
	seen := make(map[string]bool)
	var deduplicated []models.VolumeInfo

	for _, vol := range volumes {
		if !seen[vol.Name] {
			seen[vol.Name] = true
			deduplicated = append(deduplicated, vol)
		}
	}
	return deduplicated
}

func runCommand(cmdStr string) error {
	parts := strings.Fields(cmdStr)
	if len(parts) == 0 {
		return fmt.Errorf("empty command")
	}

	cmd := exec.Command(parts[0], parts[1:]...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("command failed: %s: %w", string(output), err)
	}
	return nil
}

// createSSHBackup creates a backup and streams it directly via SSH without using local disk space
// This method uses a Docker container to mount all volumes and stream the tar archive directly to SSH
func createSSHBackup(dockerClient *docker.Client, volumes []models.VolumeInfo, backupName, projectName string, options models.BackupOptions) (string, error) {
	// Parse SSH target (format: user@host:path)
	parts := strings.Split(options.SSHTarget, ":")
	if len(parts) != 2 {
		return "", fmt.Errorf("invalid SSH target format, expected user@host:path")
	}

	userHost := parts[0]
	remotePath := parts[1]

	// Determine file extension
	ext := ".tar"
	if options.Compress {
		ext = ".tar.gz"
	}
	remoteFile := fmt.Sprintf("%s/%s%s", remotePath, backupName, ext)

	// Prepare metadata
	var volumeBackups []models.VolumeBackup
	for _, vol := range volumes {
		volumeBackups = append(volumeBackups, models.VolumeBackup{
			Name:        vol.ComposeName,
			Service:     vol.Service,
			Target:      vol.Target,
			IsExternal:  vol.IsExternal,
			ArchivePath: vol.Name,
		})
	}

	metadata := models.BackupMetadata{
		Timestamp:   models.GenerateTimestamp(),
		Project:     projectName,
		ComposeFile: filepath.Base(options.ComposeFile),
		Volumes:     volumeBackups,
	}

	metadataBytes, err := json.MarshalIndent(metadata, "", "  ")
	if err != nil {
		return "", fmt.Errorf("failed to marshal metadata: %w", err)
	}

	// Create a small temp directory ONLY for metadata and SSH config (very small files)
	tempDir, err := os.MkdirTemp("", "dvtools-metadata-*")
	if err != nil {
		return "", fmt.Errorf("failed to create temp dir: %w", err)
	}
	defer os.RemoveAll(tempDir)

	metadataPath := filepath.Join(tempDir, "metadata.json")
	if err := os.WriteFile(metadataPath, metadataBytes, 0644); err != nil {
		return "", fmt.Errorf("failed to write metadata: %w", err)
	}

	// Copy SSH config to temp directory
	sshDir := filepath.Join(tempDir, ".ssh")
	if err := os.MkdirAll(sshDir, 0700); err != nil {
		return "", fmt.Errorf("failed to create SSH directory: %w", err)
	}

	homeDir, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("failed to get home directory: %w", err)
	}

	userSSHDir := filepath.Join(homeDir, ".ssh")

	// Copy known_hosts if exists
	knownHosts := filepath.Join(userSSHDir, "known_hosts")
	if _, err := os.Stat(knownHosts); err == nil {
		exec.Command("cp", knownHosts, sshDir).Run()
	}

	// Copy SSH keys
	for _, keyFile := range []string{"id_rsa", "id_ed25519"} {
		keyPath := filepath.Join(userSSHDir, keyFile)
		if _, err := os.Stat(keyPath); err == nil {
			destPath := filepath.Join(sshDir, keyFile)
			exec.Command("cp", keyPath, destPath).Run()
			os.Chmod(destPath, 0600)
		}
	}

	// Prepare volume mounts for container
	volumeMounts := make(map[string]string)
	for _, vol := range volumes {
		volumeMounts[vol.ComposeName] = fmt.Sprintf("/volumes/%s", vol.Name)
	}

	// Add metadata and SSH directory as bind mounts (not volume mounts)
	// Note: The RunContainer method will handle these correctly
	volumeMounts[metadataPath] = "/metadata.json"
	volumeMounts[sshDir] = "/root/.ssh"

	// Create and start container
	fmt.Println("Creating temporary container for streaming backup...")
	containerID, err := dockerClient.RunContainer(docker.ContainerConfig{
		Image:       "alpine:latest",
		Name:        "",
		Cmd:         []string{"sleep", "infinity"},
		Volumes:     volumeMounts,
		NetworkMode: "host", // Important for SSH
	})
	if err != nil {
		return "", fmt.Errorf("failed to create container: %w", err)
	}
	defer dockerClient.Cleanup(containerID)

	// Install SSH client in container
	fmt.Println("Installing SSH client in container...")
	result, err := dockerClient.ExecInContainer(containerID, []string{"apk", "add", "--no-cache", "openssh-client"})
	if err != nil || result.ExitCode != 0 {
		return "", fmt.Errorf("failed to install SSH client: %v %s", err, result.Stderr)
	}

	// Create remote directory
	fmt.Printf("Creating remote directory %s...\n", remotePath)
	mkdirCmd := fmt.Sprintf("ssh -o StrictHostKeyChecking=accept-new %s 'mkdir -p %s'", userHost, remotePath)
	result, err = dockerClient.ExecInContainer(containerID, []string{"/bin/sh", "-c", mkdirCmd})
	if err != nil || result.ExitCode != 0 {
		return "", fmt.Errorf("failed to create remote directory: %v %s", err, result.Stderr)
	}

	// Prepare temporary backup structure inside container
	fmt.Println("Starting backup transfer...")

	commands := []string{
		"mkdir -p /tmp_backup/volumes",
		"cp /metadata.json /tmp_backup/",
	}

	// Create symbolic links to volumes
	for _, vol := range volumes {
		cmd := fmt.Sprintf("ln -s /volumes/%s /tmp_backup/volumes/%s", vol.Name, vol.Name)
		commands = append(commands, cmd)
	}

	// Execute setup commands
	for _, cmd := range commands {
		result, err = dockerClient.ExecInContainer(containerID, []string{"/bin/sh", "-c", cmd})
		if err != nil || result.ExitCode != 0 {
			return "", fmt.Errorf("failed to execute command %s: %v %s", cmd, err, result.Stderr)
		}
	}

	// Stream tar archive directly to SSH
	// Use -h flag to follow symlinks (dereference them)
	// IMPORTANT: We tar metadata.json first, then volumes, to ensure fast validation
	// (avoids having to read the entire archive to find metadata at the end)
	tarCmd := "cd /tmp_backup && tar -hcf - metadata.json volumes"
	if options.Compress {
		tarCmd = fmt.Sprintf("(%s) | gzip", tarCmd)
	}

	sshCmd := fmt.Sprintf("ssh -o StrictHostKeyChecking=accept-new %s 'cat > %s'", userHost, remoteFile)
	fullCmd := fmt.Sprintf("%s | %s", tarCmd, sshCmd)

	fmt.Printf("Streaming backup to %s...\n", options.SSHTarget)
	result, err = dockerClient.ExecInContainer(containerID, []string{"/bin/sh", "-c", fullCmd})
	if err != nil || result.ExitCode != 0 {
		return "", fmt.Errorf("backup transfer failed: %v %s", err, result.Stderr)
	}

	// Cleanup temp directory in container
	dockerClient.ExecInContainer(containerID, []string{"rm", "-rf", "/tmp_backup"})

	fmt.Println("Transfer completed successfully!")
	return remoteFile, nil
}
