# Docker Volume Tools (dvtools)

A fast, reliable tool to manage Docker volumes efficiently - now written in Go!

## Description

Docker Volume Tools (`dvtools`) provides a collection of commands to help manage Docker volumes, making it easier to handle data persistence in Docker environments. It includes features for listing, backing up, and restoring Docker volumes associated with Docker Compose projects.

**Key improvement**: The Go version correctly preserves symbolic links during backup and restore operations, fixing a critical bug in the previous Python implementation.

## Features

- ✅ List all volumes in a Docker Compose project
- ✅ Backup named volumes with metadata
- ✅ **Correctly preserves symbolic links** (fixed in Go version)
- ✅ Support for selective volume backup
- ✅ Compressed archives with configurable options
- ✅ **Direct SSH transfer** to avoid local disk space issues
- ✅ Restore with force override option
- ✅ Fast native binary (no Python runtime needed)

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/docker-volume-tools.git
cd docker-volume-tools

# Build the binary
make build

# Or install to GOPATH/bin
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
# Backup all volumes
dvtools backup docker-compose.yml

# Backup specific volumes
dvtools backup docker-compose.yml -v volume1 -v volume2

# Backup without compression
dvtools backup docker-compose.yml --compress=false

# Backup to custom directory
dvtools backup docker-compose.yml --output-dir /backups

# Direct SSH transfer (no local copy)
dvtools backup docker-compose.yml --ssh-target user@remote:/path/to/backups
```

### Restore volumes

```bash
# Restore all volumes
dvtools restore backups/project_volumes_20240112_123456.tar.gz

# Restore specific volumes
dvtools restore backup.tar.gz -v postgres_data

# Force override existing volumes
dvtools restore backup.tar.gz --force
```

### Backup format

The tool creates a structured backup archive:

```
project_volumes_20240112_123456.tar.gz
├── metadata.json
└── volumes/
    ├── postgres_data/
    │   └── [volume contents with preserved symlinks]
    └── redis_data/
        └── [volume contents with preserved symlinks]
```

## Critical Bug Fix: Symbolic Links

**Problem in Python version**: The backup used `tar -h` which dereferenced symlinks (copied the target content instead of the link itself), but restore tried to recreate symlinks. This was incompatible and led to data duplication and incorrect restoration.

**Fixed in Go version**:
- **Backup**: Preserves symlinks using `tar.TypeSymlink` (no dereferencing)
- **Restore**: Correctly recreates symlinks with `os.Symlink()`
- Symlinks are now properly maintained through the backup/restore cycle

## Development

### Requirements

- Go 1.19 or higher
- Docker (for running and testing)
- Make (optional, for build automation)

### Development guidelines

- Go code follows standard Go conventions
- All code, variables, functions, and file names are in English
- Git commit messages are in French
- Documentation is available in French in `devbook.md`

### Building

```bash
# Build for current platform
make build

# Build for all platforms
make build-all

# Format code
make fmt

# Run tests
make test

# Run integration tests (requires Docker)
make integration
```

### Project Structure

```
docker-volume-tools/
├── cmd/dvtools/           # CLI entry point
├── internal/
│   ├── compose/           # Docker Compose parser
│   ├── backup/            # Backup logic with symlink fix
│   ├── restore/           # Restore logic with symlink fix
│   └── docker/            # Docker client wrapper
├── pkg/models/            # Data structures
├── test/
│   ├── integration/       # Integration tests
│   └── testdata/          # Test fixtures
├── Makefile
└── go.mod
```

## Testing

```bash
# Run unit tests
make test

# Run integration tests (requires Docker daemon)
make integration

# Run all tests
make test-all
```

## Migration from Python Version

The Go version (`dvtools`) is a complete rewrite with the following improvements:

1. **Fixed symbolic link handling** - Critical bug fix
2. **Better performance** - Native compiled binary
3. **Smaller footprint** - Single binary, no Python runtime needed
4. **SSH transfer support** - Direct transfer without local copy
5. **Cross-platform** - Easy to build for Linux, macOS, Windows

### Breaking Changes

- Binary name changed from `dvt` to `dvtools`
- Command-line flags use `--flag` instead of `--flag` format
- Backup metadata format is **compatible** with Python version

## License

MIT License
