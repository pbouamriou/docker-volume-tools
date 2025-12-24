# Changelog

All notable changes to Docker Volume Tools will be documented in this file.

## [0.3.0] - 2025-12-02

### Added
- **Streaming SSH Backup**: Backup directly to remote host without using local disk space
  - Mounts all volumes in a single container
  - Streams tar archive through SSH pipe
  - Only requires space for small metadata file locally
- **Single-Pass Restore**: Restore all volumes in one archive read
  - Mounts all target volumes in one container
  - Uses symlink redirection for efficient extraction
  - Significantly faster for multi-volume restores
- **Static Binary Build**: `make build-static` for GLIBC-independent binaries
  - Compatible with older systems (Debian 10+)
  - Uses `CGO_ENABLED=0` for full static linking
- **Optimized Archive Structure**: metadata.json placed first in archive
  - Enables fast validation without reading entire archive

### Fixed
- Archive path handling for `./` prefixed entries
- Volume restoration on systems with limited `/tmp` space

### Changed
- Restore now processes all volumes in a single pass instead of one-by-one
- SSH backup no longer requires local temporary storage for volume data

---

## [0.2.0] - 2025-01-29

### Complete Rewrite in Go

This version is a complete rewrite of the tool in Go, bringing significant improvements and critical bug fixes.

### Added
- **SSH Transfer Support**: Direct backup transfer to remote host via SSH/SCP
  - Format: `dvtools backup compose.yml --ssh-target user@host:path`
- **Force Restore Option**: Override existing volumes with `--force` flag
- **Native Binary**: Single executable, no Python runtime required
- **Cross-Platform Build**: Easy compilation for Linux, macOS, Windows
- **Makefile**: Build automation with targets for build, test, install, clean

### Fixed
- **CRITICAL: Symbolic Link Handling**
  - **Problem**: Python version used `tar -h` during backup which dereferenced symlinks
  - **Solution**: Go version correctly preserves symlinks during backup and restore

### Changed
- **Binary Name**: Changed from `dvt` to `dvtools`
- **Language**: Migrated from Python to Go
- **Architecture**: Modular package structure with `internal/` and `pkg/`

---

## [0.1.0] - 2024-04-23 (Python Version - Deprecated)

### Added
- Initial Python implementation
- `list` command to show volumes in docker-compose projects
- `backup` command for volume backups
- `restore` command for volume restoration

### Known Issues (Fixed in Go version)
- Symbolic links incorrectly handled (dereferenced during backup)
- Required Python runtime and dependencies
- No SSH streaming support

---

## Migration Guide

### From Python to Go

```bash
# Old (Python)
dvt list docker-compose.yml

# New (Go)
dvtools list docker-compose.yml
```

### New Features

```bash
# SSH streaming backup (no local disk space needed)
dvtools backup compose.yml --ssh-target user@remote:/backups

# Static binary for older systems
make build-static

# Force restore
dvtools restore backup.tar.gz --force
```
