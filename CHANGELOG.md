# Changelog

All notable changes to Docker Volume Tools will be documented in this file.

## [0.2.0] - 2025-01-29

### 🚀 Complete Rewrite in Go

This version is a complete rewrite of the tool in Go, bringing significant improvements and critical bug fixes.

### ✨ Added
- **SSH Transfer Support**: Direct backup transfer to remote host via SSH/SCP without creating local copy
  - Saves disk space on source machine
  - Format: `dvtools backup compose.yml --ssh-target user@host:path`
- **Force Restore Option**: Override existing volumes with `--force` flag
- **Native Binary**: Single executable, no Python runtime required
- **Cross-Platform Build**: Easy compilation for Linux, macOS, Windows
- **Makefile**: Build automation with targets for build, test, install, clean
- **Better Error Handling**: Clear error messages with context

### 🐛 Fixed
- **CRITICAL: Symbolic Link Handling**
  - **Problem**: Python version used `tar -h` during backup which dereferenced symlinks (copied target content instead of link), but restore tried to recreate symlinks. This was fundamentally broken.
  - **Solution**: Go version correctly preserves symlinks during backup (`tar.TypeSymlink`) and recreates them during restore (`os.Symlink()`)
  - Symlinks now work correctly through the entire backup/restore cycle

### 🔄 Changed
- **Binary Name**: Changed from `dvt` to `dvtools` for clarity
- **Language**: Migrated from Python to Go 1.24
- **Architecture**: Modular package structure with `internal/` and `pkg/` organization
- **Performance**: Faster execution due to native compiled binary
- **Dependencies**: No external runtime dependencies (previously required Python + pip packages)

### 📝 Technical Details

#### Symbolic Link Fix Details

**Before (Python - BROKEN)**:
- Backup: Used `tar -hcf` which followed symlinks and copied their targets
- Restore: Tried to recreate symlinks from metadata
- Result: Incompatible operations, data duplication, incorrect restoration

**After (Go - FIXED)**:
```go
// Backup: Preserve symlinks
if info.Mode()&os.ModeSymlink != 0 {
    header := &tar.Header{
        Typeflag: tar.TypeSymlink,
        Linkname: os.Readlink(path),
    }
}

// Restore: Recreate symlinks
case tar.TypeSymlink:
    os.Symlink(header.Linkname, targetPath)
```

#### Architecture Changes

**Python Version**:
```
src/docker_volume_tools/
├── cli.py
├── compose.py
├── backup.py
└── restore.py
```

**Go Version**:
```
cmd/dvtools/main.go          # CLI entry point
internal/
├── compose/parser.go         # Compose file parsing
├── backup/backup.go          # Backup with symlink fix
├── restore/restore.go        # Restore with symlink fix
└── docker/client.go          # Docker operations
pkg/models/volume.go          # Data structures
```

### 🔧 Maintenance
- Removed Python-specific files: `setup.py`, `build.py`, `requirements.txt` (for Python version)
- Added Go-specific files: `go.mod`, `go.sum`, `Makefile`
- Updated documentation: `README.md`, `CLAUDE.md`, `CONVERSION_PLAN.md`

### ⚙️ Compatibility
- Backup metadata format remains compatible with Python version
- Archives created by Python version can be read by Go version
- Archives created by Go version have correct symlinks (unlike Python)

---

## [0.1.0] - 2024-04-23 (Python Version)

### Added
- Initial Python implementation
- `list` command to show volumes in docker-compose projects
- `backup` command for volume backups
- `restore` command for volume restoration
- Compression support
- Metadata tracking
- Integration tests with pytest

### Known Issues
- ❌ Symbolic links incorrectly handled (dereferenced during backup)
- Limited to local backups only
- Requires Python runtime and dependencies

---

## Migration Guide: Python → Go

### Command Changes
```bash
# Old (Python)
dvt list docker-compose.yml
dvt backup docker-compose.yml

# New (Go)
dvtools list docker-compose.yml
dvtools backup docker-compose.yml
```

### Installation Changes
```bash
# Old (Python)
pip install -e .
dvt --version

# New (Go)
make build
./dvtools --version
# or
make install
dvtools --version
```

### New Features Available
```bash
# SSH transfer (NEW in Go version)
dvtools backup compose.yml --ssh-target user@remote:/backups

# Force restore (NEW in Go version)
dvtools restore backup.tar.gz --force
```

### What Stays the Same
- Backup archive format and structure
- Metadata.json format
- Command-line argument structure (mostly)
- Docker Compose file compatibility
