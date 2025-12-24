.PHONY: all build build-static test integration clean install fmt lint

# Variables
BINARY_NAME=dvtools
VERSION?=0.2.0
COMMIT?=$(shell git rev-parse --short HEAD 2>/dev/null || echo "dev")
BUILD_DIR=.
LDFLAGS=-ldflags "-X main.Version=$(VERSION) -X main.Commit=$(COMMIT)"
STATIC_LDFLAGS=-ldflags "-X main.Version=$(VERSION) -X main.Commit=$(COMMIT) -s -w"

# Default target
all: fmt test build

# Build the binary
build:
	@echo "Building $(BINARY_NAME)..."
	@go build $(LDFLAGS) -o $(BINARY_NAME) ./cmd/dvtools
	@echo "Build complete: ./$(BINARY_NAME)"

# Build static binary (compatible with older GLIBC like Debian 10)
build-static:
	@echo "Building static $(BINARY_NAME) (compatible with Debian 10+)..."
	@CGO_ENABLED=0 go build $(STATIC_LDFLAGS) -o $(BINARY_NAME) ./cmd/dvtools
	@echo "Static build complete: ./$(BINARY_NAME)"
	@echo "Verifying binary..."
	@file $(BINARY_NAME) | grep "statically linked" || echo "Warning: binary may not be fully static"

# Build for multiple platforms (static binaries)
build-all:
	@echo "Building static binaries for multiple platforms..."
	@CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build $(STATIC_LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-linux-amd64 ./cmd/dvtools
	@CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build $(STATIC_LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-linux-arm64 ./cmd/dvtools
	@CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build $(STATIC_LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-darwin-amd64 ./cmd/dvtools
	@CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build $(STATIC_LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-darwin-arm64 ./cmd/dvtools
	@echo "Cross-compilation complete (all static)"

# Run unit tests
test:
	@echo "Running unit tests..."
	@go test -v ./internal/... ./pkg/...

# Run integration tests (requires Docker)
integration:
	@echo "Running integration tests..."
	@go test -v ./test/integration/...

# Run all tests
test-all: test integration

# Format code
fmt:
	@echo "Formatting code..."
	@go fmt ./...
	@gofmt -s -w .

# Lint code
lint:
	@echo "Linting code..."
	@go vet ./...
	@test -z "$$(gofmt -l .)" || (echo "Code needs formatting. Run 'make fmt'" && exit 1)

# Install binary to GOPATH/bin
install:
	@echo "Installing $(BINARY_NAME)..."
	@go install $(LDFLAGS) ./cmd/dvtools
	@echo "Installed to $$(go env GOPATH)/bin/$(BINARY_NAME)"

# Clean build artifacts
clean:
	@echo "Cleaning..."
	@rm -f $(BINARY_NAME)
	@rm -f $(BINARY_NAME)-*
	@rm -rf dist/
	@rm -rf build/
	@rm -rf backups/
	@echo "Clean complete"

# Download dependencies
deps:
	@echo "Downloading dependencies..."
	@go mod download
	@go mod tidy

# Show help
help:
	@echo "Docker Volume Tools - Makefile targets:"
	@echo ""
	@echo "  make build         - Build the binary (dynamic linking)"
	@echo "  make build-static  - Build static binary (compatible with Debian 10+)"
	@echo "  make build-all     - Build static binaries for multiple platforms"
	@echo "  make test          - Run unit tests"
	@echo "  make integration   - Run integration tests (requires Docker)"
	@echo "  make test-all      - Run all tests"
	@echo "  make fmt           - Format code"
	@echo "  make lint          - Lint code"
	@echo "  make install       - Install binary to GOPATH/bin"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make deps          - Download and tidy dependencies"
	@echo "  make help          - Show this help"
	@echo ""
	@echo "Variables:"
	@echo "  VERSION=$(VERSION)"
	@echo "  COMMIT=$(COMMIT)"
