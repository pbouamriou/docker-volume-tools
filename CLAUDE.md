# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker Volume Tools (`dvtools`) is a Go CLI tool for backing up and restoring Docker volumes associated with Docker Compose projects. It creates structured backups with metadata and supports both local and SSH-based remote transfers.

**Key Features**:
- Streaming backup/restore without local disk space requirements
- Direct SSH transfer for remote backups
- Single-pass restore of all volumes
- Correct symbolic link handling

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

# Build static binary (compatible with Debian 10+)
make build-static

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

# Create backup (local)
./dvtools backup docker-compose.yml
./dvtools backup docker-compose.yml --output-dir /backups
./dvtools backup docker-compose.yml -v postgres_data -v redis_data

# Create backup (SSH streaming - no local disk space needed)
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
- **[internal/backup/backup.go](internal/backup/backup.go)**: Backup engine with streaming SSH support
- **[internal/restore/restore.go](internal/restore/restore.go)**: Restore engine with single-pass multi-volume restoration
- **[internal/docker/client.go](internal/docker/client.go)**: Docker SDK client wrapper
- **[pkg/models/volume.go](pkg/models/volume.go)**: Data structures (VolumeInfo, BackupMetadata, etc.)

### Key Data Flow

1. **Compose Parsing**: `ParseComposeFile()` reads docker-compose.yml and creates `VolumeInfo` structs
   - Distinguishes between named volumes and bind mounts
   - Handles Docker Compose project name prefixing (e.g., `myproject_postgres_data`)
   - Detects external volumes via `ComposeName` attribute

2. **Backup Process**: `CreateBackup()` orchestrates volume backups
   - **Local mode**: Creates archive in specified output directory
   - **SSH mode**: Streams directly to remote host without local temp files
     - Mounts all volumes in a single Alpine container
     - Creates tar archive and pipes through SSH
     - No local disk space required (except for small metadata file)

3. **Restore Process**: `RestoreBackup()` recreates volumes from backups
   - Validates backup integrity via `ValidateBackup()`
   - **Single-pass restoration**: All volumes restored in one archive read
     - Mounts all target volumes in one container
     - Uses symlinks to redirect extraction to correct volumes
     - Streams archive directly into container

### Critical Implementation Details

**SSH Streaming Backup** ([backup.go:306-472](internal/backup/backup.go#L306-L472)):
```go
// Mount all volumes in container
// Create symlinks: /tmp_backup/volumes/<name> -> /volumes/<name>
// Stream: tar -hcf - metadata.json volumes | gzip | ssh user@host 'cat > file'
```

**Single-Pass Restore** ([restore.go:148-216](internal/restore/restore.go#L148-L216)):
```go
// Mount all volumes at /restore_volumes/<archive_path>
// Create symlinks: /volumes/<name> -> /restore_volumes/<name>
// Extract: gunzip -c | tar -xf - -C /
// Files go to /volumes/<name> which redirects to mounted volumes
```

**Volume Name Resolution**: Docker Compose prefixes volume names with the project name. The code tracks both the compose file name (e.g., `postgres_data`) and the actual Docker volume name (e.g., `testdata_postgres_data`) using `VolumeInfo.ComposeName`.

**Backup Archive Structure**:
```
project_volumes_20240112_123456.tar.gz
├── metadata.json          # FIRST in archive for fast validation
└── volumes/
    ├── postgres_data/
    │   └── [volume contents]
    └── redis_data/
        └── [volume contents]
```

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

Integration tests in [test/integration/](test/integration/) cover full backup/restore workflows.

Tests require Docker daemon to be running and accessible.

## Dependencies

Key Go packages:
- `github.com/spf13/cobra` - CLI framework
- `github.com/docker/docker/client` - Docker SDK
- `gopkg.in/yaml.v3` - YAML parser
- `archive/tar` - Tar archive handling
- `compress/gzip` - Compression

All dependencies managed via `go.mod`.
