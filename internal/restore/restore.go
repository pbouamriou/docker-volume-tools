package restore

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

	"github.com/pbouamriou/docker-volume-tools/internal/docker"
	"github.com/pbouamriou/docker-volume-tools/pkg/models"
)

// ValidateBackup validates a backup archive and returns its metadata
func ValidateBackup(backupPath string) (*models.BackupMetadata, error) {
	if _, err := os.Stat(backupPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("backup file not found: %s", backupPath)
	}

	// Open archive
	file, err := os.Open(backupPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open backup: %w", err)
	}
	defer file.Close()

	// Setup decompression
	var reader io.Reader = file
	if strings.HasSuffix(backupPath, ".gz") {
		gzReader, err := gzip.NewReader(file)
		if err != nil {
			return nil, fmt.Errorf("failed to decompress backup: %w", err)
		}
		defer gzReader.Close()
		reader = gzReader
	}

	// Read tar archive
	tarReader := tar.NewReader(reader)

	// Find and read metadata.json
	var metadata models.BackupMetadata
	metadataFound := false

	for {
		header, err := tarReader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("failed to read tar: %w", err)
		}

		// Look for metadata.json (handles both "metadata.json" and "./metadata.json")
		cleanName := strings.TrimPrefix(header.Name, "./")
		if cleanName == "metadata.json" || strings.HasSuffix(cleanName, "/metadata.json") {
			metadataBytes, err := io.ReadAll(tarReader)
			if err != nil {
				return nil, fmt.Errorf("failed to read metadata: %w", err)
			}

			if err := json.Unmarshal(metadataBytes, &metadata); err != nil {
				return nil, fmt.Errorf("failed to parse metadata: %w", err)
			}

			metadataFound = true
			break
		}
	}

	if !metadataFound {
		return nil, fmt.Errorf("metadata.json not found in backup")
	}

	if len(metadata.Volumes) == 0 {
		return nil, fmt.Errorf("no volumes found in backup metadata")
	}

	return &metadata, nil
}

// RestoreBackup restores volumes from a backup archive
func RestoreBackup(options models.RestoreOptions) error {
	// Validate backup
	metadata, err := ValidateBackup(options.BackupPath)
	if err != nil {
		return err
	}

	// Filter volumes if specified
	volumesToRestore := metadata.Volumes
	if len(options.VolumesToRestore) > 0 {
		volumesToRestore = filterVolumes(volumesToRestore, options.VolumesToRestore)
		if len(volumesToRestore) == 0 {
			return fmt.Errorf("no matching volumes found in backup")
		}
	}

	// Create Docker client
	dockerClient, err := docker.NewClient()
	if err != nil {
		return err
	}
	defer dockerClient.Close()

	// Prepare all volumes first (check existence, remove if force, create)
	for _, vol := range volumesToRestore {
		volumeName := vol.Name

		exists, err := dockerClient.VolumeExists(volumeName)
		if err != nil {
			return err
		}

		if exists {
			if !options.Force {
				return fmt.Errorf("volume %s already exists (use --force to overwrite)", volumeName)
			}
			fmt.Printf("Removing existing volume %s\n", volumeName)
			if err := dockerClient.RemoveVolume(volumeName, true); err != nil {
				return fmt.Errorf("failed to remove existing volume %s: %w", volumeName, err)
			}
		}

		fmt.Printf("Creating volume %s\n", volumeName)
		if err := dockerClient.CreateVolume(volumeName); err != nil {
			return fmt.Errorf("failed to create volume %s: %w", volumeName, err)
		}
	}

	// Restore all volumes in a single pass
	fmt.Println("\nRestoring all volumes in a single pass...")
	if err := restoreAllVolumes(dockerClient, volumesToRestore, options.BackupPath); err != nil {
		// Cleanup volumes on failure
		for _, vol := range volumesToRestore {
			dockerClient.RemoveVolume(vol.Name, true)
		}
		return fmt.Errorf("restore failed: %w", err)
	}

	fmt.Println("\nAll volumes restored successfully!")
	return nil
}

// restoreAllVolumes restores all volumes in a single pass by mounting them all
// in one container and extracting the archive once
func restoreAllVolumes(dockerClient *docker.Client, volumes []models.VolumeBackup, backupPath string) error {
	// Pull alpine image if needed
	if err := dockerClient.PullImage("alpine:latest"); err != nil {
		return err
	}

	// Mount all volumes in one container
	// Each volume is mounted at /restore_volumes/<archive_path>
	volumeMounts := make(map[string]string)
	for _, vol := range volumes {
		volumeMounts[vol.Name] = fmt.Sprintf("/restore_volumes/%s", vol.ArchivePath)
	}

	containerID, err := dockerClient.RunContainer(docker.ContainerConfig{
		Image:   "alpine:latest",
		Name:    "",
		Cmd:     []string{"sleep", "infinity"},
		Volumes: volumeMounts,
	})
	if err != nil {
		return fmt.Errorf("failed to create container: %w", err)
	}
	defer dockerClient.Cleanup(containerID)

	// Strategy: Extract the entire archive, but use symlinks to redirect extraction
	// to the mounted volumes. This way tar extracts directly to the volume mounts.
	//
	// The archive structure is: volumes/<name>/files...
	// We create /restore_volumes/<name> as mount points
	// We extract with: tar -xf - -C / which puts files at /volumes/<name>/...
	// Then we create symlinks: /volumes/<name> -> /restore_volumes/<name>
	// So when tar writes to /volumes/<name>, it actually writes to the volume mount

	// Build script to create symlinks and extract
	extractScript := `
		# Create the volumes directory and symlinks to mounted volumes
		mkdir -p /volumes
		for dir in /restore_volumes/*; do
			name=$(basename "$dir")
			ln -sf "/restore_volumes/$name" "/volumes/$name"
		done

		# Extract archive - files go to /volumes/<name> which symlinks to /restore_volumes/<name>
		gunzip -c | tar -xf - -C / 2>/dev/null

		# Show what was restored
		echo "Restored volumes:"
		for dir in /restore_volumes/*; do
			name=$(basename "$dir")
			count=$(find "$dir" -type f 2>/dev/null | wc -l)
			echo "  $name: $count files"
		done
	`

	// Use docker exec with stdin to pipe the archive data
	dockerCmd := fmt.Sprintf("docker exec -i %s /bin/sh -c '%s'", containerID, extractScript)

	// Open the backup file and pipe it to docker exec
	cmd := exec.Command("sh", "-c", fmt.Sprintf("cat '%s' | %s", backupPath, dockerCmd))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("failed to extract volumes: %s: %w", string(output), err)
	}

	fmt.Printf("%s", string(output))
	return nil
}

// restoreVolume restores a single volume from the backup archive
// Uses streaming to avoid using local disk space - data is piped directly into the container
func restoreVolume(dockerClient *docker.Client, volumeBackup models.VolumeBackup, backupPath string, force bool) error {
	volumeName := volumeBackup.Name

	// Check if volume exists
	exists, err := dockerClient.VolumeExists(volumeName)
	if err != nil {
		return err
	}

	if exists {
		if !force {
			return fmt.Errorf("volume %s already exists (use --force to overwrite)", volumeName)
		}
		fmt.Printf("Removing existing volume %s\n", volumeName)
		if err := dockerClient.RemoveVolume(volumeName, true); err != nil {
			return fmt.Errorf("failed to remove existing volume: %w", err)
		}
	}

	// Create new volume
	fmt.Printf("Creating volume %s\n", volumeName)
	if err := dockerClient.CreateVolume(volumeName); err != nil {
		return fmt.Errorf("failed to create volume: %w", err)
	}

	// Stream data directly into a container using tar pipe
	// This avoids using local disk space
	if err := streamRestoreToVolume(dockerClient, volumeName, volumeBackup.ArchivePath, backupPath); err != nil {
		// Cleanup volume on failure
		dockerClient.RemoveVolume(volumeName, true)
		return fmt.Errorf("failed to restore volume data: %w", err)
	}

	return nil
}

// streamRestoreToVolume streams data from the backup archive directly into a container
// Uses a custom extraction script that handles busybox tar limitations
func streamRestoreToVolume(dockerClient *docker.Client, volumeName, archivePath, backupPath string) error {
	// Pull alpine image if needed
	if err := dockerClient.PullImage("alpine:latest"); err != nil {
		return err
	}

	// Create temporary container with volume mounted
	containerID, err := dockerClient.RunContainer(docker.ContainerConfig{
		Image: "alpine:latest",
		Name:  "",
		Cmd:   []string{"sleep", "infinity"},
		Volumes: map[string]string{
			volumeName: "/volume",
		},
	})
	if err != nil {
		return fmt.Errorf("failed to create container: %w", err)
	}
	defer dockerClient.Cleanup(containerID)

	// Volume prefix in archive (e.g., "volumes/nextcloud/")
	// Handle both "volumes/X/" and "./volumes/X/" formats
	volumePrefix1 := fmt.Sprintf("volumes/%s/", archivePath)
	volumePrefix2 := fmt.Sprintf("./volumes/%s/", archivePath)

	// Strategy: Use a shell script that reads tar entries and extracts only matching ones
	// This works with busybox tar by using a filtering approach
	extractScript := fmt.Sprintf(`
		PREFIX1="%s"
		PREFIX2="%s"
		DEST="/volume"

		# Decompress if needed and process with tar
		gunzip -c 2>/dev/null || cat | tar -tf - | while read -r entry; do
			# Check if this entry matches our volume
			case "$entry" in
				"$PREFIX1"*|"$PREFIX2"*)
					# Calculate relative path
					relpath="${entry#$PREFIX1}"
					relpath="${relpath#$PREFIX2}"
					relpath="${relpath#./volumes/%s/}"
					if [ -n "$relpath" ]; then
						echo "$entry"
					fi
					;;
			esac
		done > /tmp/files_to_extract.txt

		# Now extract only the matching files
		if [ -s /tmp/files_to_extract.txt ]; then
			gunzip -c 2>/dev/null || cat | tar -xf - -T /tmp/files_to_extract.txt --strip-components=2 -C "$DEST"
		fi
		rm -f /tmp/files_to_extract.txt
	`, volumePrefix1, volumePrefix2, archivePath)

	// This approach requires reading the archive twice, which is slow for large archives
	// Let's use a simpler approach: extract everything but use --exclude for non-matching dirs

	// Simpler approach: extract with strip-components, tar will naturally filter
	// because non-existent paths are skipped
	simpleScript := fmt.Sprintf(`
		# Create a temporary extraction point
		mkdir -p /tmp/extract

		# Extract the archive
		gunzip -c | tar -xf - -C /tmp/extract 2>/dev/null

		# Find and copy the volume data
		if [ -d "/tmp/extract/volumes/%s" ]; then
			cp -a "/tmp/extract/volumes/%s/." /volume/
		elif [ -d "/tmp/extract/./volumes/%s" ]; then
			cp -a "/tmp/extract/./volumes/%s/." /volume/
		else
			echo "ERROR: Volume directory not found" >&2
			ls -la /tmp/extract/ >&2
			ls -la /tmp/extract/volumes/ 2>/dev/null >&2
			exit 1
		fi

		# Cleanup
		rm -rf /tmp/extract
	`, archivePath, archivePath, archivePath, archivePath)

	// Use docker exec with stdin to pipe the archive data
	dockerCmd := fmt.Sprintf("docker exec -i %s /bin/sh -c '%s'", containerID, simpleScript)

	// Open the backup file and pipe it to docker exec
	cmd := exec.Command("sh", "-c", fmt.Sprintf("cat '%s' | %s", backupPath, dockerCmd))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("failed to extract volume data: %s: %w", string(output), err)
	}

	// Suppress unused variable warning
	_ = extractScript

	return nil
}

// extractVolumeFromBackup extracts a specific volume's data from the backup archive
// CRITICAL: Properly handles symlinks by recreating them with correct paths
func extractVolumeFromBackup(backupPath, volumeArchivePath, destDir string) error {
	// Open backup archive
	file, err := os.Open(backupPath)
	if err != nil {
		return err
	}
	defer file.Close()

	// Setup decompression
	var reader io.Reader = file
	if strings.HasSuffix(backupPath, ".gz") {
		gzReader, err := gzip.NewReader(file)
		if err != nil {
			return err
		}
		defer gzReader.Close()
		reader = gzReader
	}

	// Read tar archive
	tarReader := tar.NewReader(reader)

	// Volume prefix in archive (e.g., "volumes/postgres_data/" or "./volumes/postgres_data/")
	volumePrefix := fmt.Sprintf("volumes/%s/", volumeArchivePath)

	// Extract files
	for {
		header, err := tarReader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}

		// Normalize path by removing leading "./"
		normalizedName := strings.TrimPrefix(header.Name, "./")

		// Check if this file belongs to our volume
		if !strings.HasPrefix(normalizedName, volumePrefix) {
			continue
		}

		// Get relative path within volume
		relPath := strings.TrimPrefix(normalizedName, volumePrefix)
		if relPath == "" {
			continue
		}

		targetPath := filepath.Join(destDir, relPath)

		// Handle different file types
		switch header.Typeflag {
		case tar.TypeDir:
			// Create directory
			if err := os.MkdirAll(targetPath, os.FileMode(header.Mode)); err != nil {
				return fmt.Errorf("failed to create directory %s: %w", relPath, err)
			}

		case tar.TypeReg:
			// Create parent directory
			if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
				return err
			}

			// Create and write file
			outFile, err := os.OpenFile(targetPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, os.FileMode(header.Mode))
			if err != nil {
				return fmt.Errorf("failed to create file %s: %w", relPath, err)
			}

			if _, err := io.Copy(outFile, tarReader); err != nil {
				outFile.Close()
				return fmt.Errorf("failed to write file %s: %w", relPath, err)
			}
			outFile.Close()

		case tar.TypeSymlink:
			// Create parent directory
			if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
				return err
			}

			// Create symlink
			// The linkname in the header is the target of the symlink
			if err := os.Symlink(header.Linkname, targetPath); err != nil {
				// If symlink already exists, remove and recreate
				if os.IsExist(err) {
					os.Remove(targetPath)
					if err := os.Symlink(header.Linkname, targetPath); err != nil {
						return fmt.Errorf("failed to create symlink %s -> %s: %w", relPath, header.Linkname, err)
					}
				} else {
					return fmt.Errorf("failed to create symlink %s -> %s: %w", relPath, header.Linkname, err)
				}
			}
			fmt.Printf("  Restored symlink: %s -> %s\n", relPath, header.Linkname)

		default:
			fmt.Printf("  Warning: unsupported file type %c for %s\n", header.Typeflag, relPath)
		}
	}

	return nil
}

// copyDataToVolume copies data from a local directory to a Docker volume
func copyDataToVolume(dockerClient *docker.Client, volumeName, sourceDir string) error {
	// Pull alpine image
	if err := dockerClient.PullImage("alpine:latest"); err != nil {
		return err
	}

	// Create temporary container with volume mounted
	containerID, err := dockerClient.RunContainer(docker.ContainerConfig{
		Image: "alpine:latest",
		Name:  fmt.Sprintf("restore_%s", volumeName),
		Cmd:   []string{"sleep", "infinity"},
		Volumes: map[string]string{
			volumeName: "/volume",
		},
	})
	if err != nil {
		return err
	}
	defer dockerClient.Cleanup(containerID)

	// Use docker cp to copy files to container
	// The trailing /. ensures contents are copied, not the directory itself
	copyCmd := fmt.Sprintf("docker cp %s/. %s:/volume/", sourceDir, containerID)
	cmd := exec.Command("sh", "-c", copyCmd)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("docker cp failed: %s: %w", string(output), err)
	}

	return nil
}

// Helper functions

func filterVolumes(volumes []models.VolumeBackup, names []string) []models.VolumeBackup {
	nameMap := make(map[string]bool)
	for _, name := range names {
		nameMap[name] = true
	}

	var filtered []models.VolumeBackup
	for _, vol := range volumes {
		if nameMap[vol.Name] {
			filtered = append(filtered, vol)
		}
	}
	return filtered
}
