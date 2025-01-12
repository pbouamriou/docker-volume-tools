# Docker Volume Tools

A set of tools to manage Docker volumes efficiently.

## Description

This project provides a collection of tools to help manage Docker volumes, making it easier to handle data persistence in Docker environments. It includes features for listing, backing up, and restoring Docker volumes associated with Docker Compose projects.

## Features

- List all volumes in a Docker Compose project
- Backup named volumes with metadata
- Support for selective volume backup
- Compressed archives with configurable options
- Comprehensive integration tests

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/docker-volume-tools.git
cd docker-volume-tools

# Install in development mode
pip install -e .
```

## Usage

### List volumes

```bash
dvt list docker-compose.yml
```

### Backup volumes

```bash
# Backup all volumes
dvt backup docker-compose.yml

# Backup specific volumes
dvt backup docker-compose.yml -v volume1 -v volume2

# Backup without compression
dvt backup docker-compose.yml --no-compress
```

### Backup format

The tool creates a structured backup archive:

```
project_volumes_20240112_123456.tar.gz
└── project_volumes_20240112_123456/
    ├── volume1.tar.gz
    ├── volume2.tar.gz
    └── metadata.json
```

## Development

This project follows specific development guidelines:

- Python code follows PEP 8 style guide
- All code, variables, functions, and file names are in English
- Git commit messages are in French
- Documentation is available in French in `devbook.md`
- Integration tests ensure reliability

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_integration.py
```

## License

MIT License
