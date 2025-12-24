# Docker Volume Tools (dvtools)

A fast, reliable CLI tool to backup and restore Docker volumes - written in Go.

## Features

- **List** all volumes in a Docker Compose project
- **Backup** named volumes with metadata
- **Restore** volumes with force override option
- **SSH Streaming**: Backup directly to remote host without local disk space
- **Single-Pass Restore**: Restore all volumes in one archive read
- **Static Binary**: Works on older systems (Debian 10+)
- **No Dependencies**: Single binary, no runtime required

## Installation

### From Source

```bash
git clone https://github.com/yourusername/docker-volume-tools.git
cd docker-volume-tools

# Build standard binary
make build

# Build static binary (for older systems)
make build-static

# Install to GOPATH/bin
make install
```

### Binary Releases

Download pre-compiled binaries from the [Releases page](https://github.com/yourusername/docker-volume-tools/releases).

## Usage

### List volumes

```bash
dvtools list docker-compose.yml
```

### Backup volumes

```bash
# Backup all volumes locally
dvtools backup docker-compose.yml

# Backup to custom directory
dvtools backup docker-compose.yml --output-dir /backups

# Backup specific volumes
dvtools backup docker-compose.yml -v volume1 -v volume2

# SSH streaming backup (no local disk space needed)
dvtools backup docker-compose.yml --ssh-target user@remote:/path/to/backups
```

### Restore volumes

```bash
# Restore all volumes
dvtools restore backup.tar.gz

# Restore specific volumes
dvtools restore backup.tar.gz -v postgres_data

# Force override existing volumes
dvtools restore backup.tar.gz --force
```

## Backup Format

The tool creates structured backup archives:

```
project_volumes_20240112_123456.tar.gz
├── metadata.json
└── volumes/
    ├── postgres_data/
    │   └── [volume contents]
    └── redis_data/
        └── [volume contents]
```

## Key Features

### SSH Streaming Backup

Backup directly to a remote server without using local disk space:

```bash
dvtools backup docker-compose.yml -s user@server:/backups
```

This is ideal for servers with limited disk space. The backup streams directly through SSH.

### Single-Pass Restore

All volumes are restored in a single read of the archive, making restoration much faster for multi-volume backups.

### Static Binary

Build a fully static binary that works on older Linux distributions:

```bash
make build-static
```

This creates a binary with no GLIBC dependencies, compatible with Debian 10 and older.

## Development

### Requirements

- Go 1.19 or higher
- Docker
- Make (optional)

### Building

```bash
# Standard build
make build

# Static build (no GLIBC dependency)
make build-static

# Cross-platform builds
make build-all

# Run tests
make test

# Format code
make fmt
```

### Project Structure

```
docker-volume-tools/
├── cmd/dvtools/           # CLI entry point
├── internal/
│   ├── compose/           # Docker Compose parser
│   ├── backup/            # Backup with SSH streaming
│   ├── restore/           # Single-pass restore
│   └── docker/            # Docker client wrapper
├── pkg/models/            # Data structures
├── test/                  # Integration tests
├── Makefile
└── go.mod
```

## License

MIT License
