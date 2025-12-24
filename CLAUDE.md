# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker Volume Tools (`dvtools`) is a Go CLI tool for backing up and restoring Docker volumes associated with Docker Compose projects. It creates structured backups with metadata and supports both local and SSH-based remote transfers.

**Critical Fix**: This Go rewrite fixes a major bug in the Python version where symbolic links were incorrectly handled (dereferenced during backup but attempted recreation during restore).

## Development Commands

### Environment Setup
```bash
# Install Go 1.19+ (version 1.24 installed)
# No virtual environment needed - Go manages dependencies via go.mod

# Download dependencies
go mod download
go mod tidy
```

### Building
```bash
# Build binary
make build

# Build for all platforms
make build-all

# Install to GOPATH/bin
make install
```

### Testing
```bash
# Run unit tests
make test

# Run integration tests (requires Docker)
make integration

# Run all tests
make test-all

# Format code
make fmt

# Lint code
make lint
```

### Running the CLI
```bash
# List volumes in a compose project
./dvtools list docker-compose.yml

# Create backup
./dvtools backup docker-compose.yml
./dvtools backup docker-compose.yml --output-dir /backups
./dvtools backup docker-compose.yml -v postgres_data -v redis_data
./dvtools backup docker-compose.yml --ssh-target user@remote:/path/to/backups

# Restore from backup
./dvtools restore backups/volumes_20240112_123456.tar.gz
./dvtools restore backups/volumes_20240112_123456.tar.gz -v postgres_data
./dvtools restore backups/volumes_20240112_123456.tar.gz --force
```

## Architecture

### Module Structure

- **[cmd/dvtools/main.go](cmd/dvtools/main.go)**: Cobra-based CLI interface with three main commands (`list`, `backup`, `restore`)
- **[internal/compose/parser.go](internal/compose/parser.go)**: Docker Compose YAML parser that extracts volume information
- **[internal/backup/backup.go](internal/backup/backup.go)**: Backup engine that creates tar archives with **proper symlink preservation**
- **[internal/restore/restore.go](internal/restore/restore.go)**: Restore engine that recreates volumes with **correct symlink handling**
- **[internal/docker/client.go](internal/docker/client.go)**: Docker SDK client wrapper
- **[pkg/models/volume.go](pkg/models/volume.go)**: Data structures (VolumeInfo, BackupMetadata, etc.)

### Key Data Flow

1. **Compose Parsing**: `ParseComposeFile()` reads docker-compose.yml and creates `VolumeInfo` structs
   - Distinguishes between named volumes and bind mounts
   - Handles Docker Compose project name prefixing (e.g., `myproject_postgres_data`)
   - Detects external volumes via `ComposeName` attribute

2. **Backup Process**: `CreateBackup()` orchestrates volume backups
   - Uses temporary Alpine containers to read volume data via `docker cp`
   - Creates tar archives with `archive/tar` package
   - **CRITICAL**: Preserves symlinks using `tar.TypeSymlink` (NO dereferencing with `-h`)
   - Generates metadata.json with volume configurations
   - Supports two modes:
     - **Local**: Creates archive in specified output directory
     - **SSH**: Creates temp archive and transfers via SCP to save disk space
   - Final archive structure: `project_volumes_timestamp.tar.gz` containing `volumes/` directory and `metadata.json`

3. **Restore Process**: `RestoreBackup()` recreates volumes from backups
   - Validates backup integrity via `ValidateBackup()`
   - Extracts metadata and volume data from archive
   - Creates new Docker volumes and populates them using temporary containers
   - **CRITICAL**: Correctly handles symlinks by detecting `tar.TypeSymlink` and recreating with `os.Symlink()`
   - Handles volume name prefixing and `ArchivePath` mapping

### Critical Implementation Details

**Volume Name Resolution**: Docker Compose prefixes volume names with the project name. The code tracks both the compose file name (e.g., `postgres_data`) and the actual Docker volume name (e.g., `testdata_postgres_data`) using `VolumeInfo.ComposeName`.

**Backup Archive Structure**:
```
project_volumes_20240112_123456.tar.gz
├── metadata.json
└── volumes/
    ├── postgres_data/  (uses compose file volume name, not Docker volume name)
    │   ├── data/
    │   └── config -> ../data/config  (symlink preserved!)
    └── redis_data/
        └── dump.rdb
```

**Symbolic Link Fix**:

**Backup** ([backup.go:195-241](internal/backup/backup.go#L195-L241)):
```go
// In createTarArchive()
if info.Mode()&os.ModeSymlink != 0 {
    linkTarget, _ := os.Readlink(path)
    header := &tar.Header{
        Typeflag: tar.TypeSymlink,
        Linkname: linkTarget,  // Store the link target
        Size:     0,
    }
    tarWriter.WriteHeader(header)
    // No file content written for symlinks
}
```

**Restore** ([restore.go:245-266](internal/restore/restore.go#L245-L266)):
```go
// In extractVolumeFromBackup()
case tar.TypeSymlink:
    // Recreate the symlink
    if err := os.Symlink(header.Linkname, targetPath); err != nil {
        // Handle errors
    }
```

**SSH Transfer Implementation** ([backup.go:306-412](internal/backup/backup.go#L306-L412)):
- Creates backup in temp directory
- Uses `ssh` command to create remote directory
- Uses `scp` command to transfer archive
- Cleans up temp files after transfer
- This avoids needing local disk space for the backup

**Container-Based Operations**: All volume read/write operations use temporary Alpine containers with volume mounts to ensure cross-platform compatibility and avoid permission issues.

## Code Conventions

### Language Rules
- All code, variables, functions, and file names: **English**
- Git commit messages: **French** (as per project conventions)
- Documentation in devbook.md: **French**
- Go code follows standard Go conventions and uses `gofmt`

### Development Workflow
- Update [devbook.md](devbook.md) when implementing features (contains French documentation and project progress)
- Ensure tests pass before commits (`make test`)
- Format code with `make fmt`
- Keep code clean and well-structured

## Testing

Unit tests in [internal/compose/parser_test.go](internal/compose/parser_test.go) cover compose file parsing.

Integration tests will cover full backup/restore workflows:
- Creating real Docker containers (PostgreSQL, Redis)
- Testing volume population, backup creation, and restoration
- Validating metadata structure and data integrity
- **Testing symlink preservation** (critical!)
- Cleaning up Docker resources (containers, volumes, networks) with defer

Tests require Docker daemon to be running and accessible.

## Dependencies

Key Go packages:
- `github.com/spf13/cobra` - CLI framework
- `github.com/docker/docker/client` - Docker SDK
- `gopkg.in/yaml.v3` - YAML parser
- `archive/tar` - Tar archive handling (symlink support)
- `compress/gzip` - Compression
- `golang.org/x/crypto/ssh` - SSH support (for transfers)

All dependencies managed via `go.mod`.
