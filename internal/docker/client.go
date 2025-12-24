package docker

import (
	"context"
	"fmt"
	"io"
	"time"

	cerrdefs "github.com/containerd/errdefs"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/image"
	"github.com/docker/docker/api/types/volume"
	"github.com/docker/docker/client"
)

// Client wraps the Docker API client with helper methods
type Client struct {
	cli *client.Client
	ctx context.Context
}

// NewClient creates a new Docker client wrapper
func NewClient() (*Client, error) {
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("failed to create Docker client: %w", err)
	}

	return &Client{
		cli: cli,
		ctx: context.Background(),
	}, nil
}

// Close closes the Docker client connection
func (c *Client) Close() error {
	return c.cli.Close()
}

// CreateVolume creates a new Docker volume
func (c *Client) CreateVolume(name string) error {
	_, err := c.cli.VolumeCreate(c.ctx, volume.CreateOptions{
		Name: name,
	})
	if err != nil {
		return fmt.Errorf("failed to create volume %s: %w", name, err)
	}
	return nil
}

// RemoveVolume removes a Docker volume
func (c *Client) RemoveVolume(name string, force bool) error {
	err := c.cli.VolumeRemove(c.ctx, name, force)
	if err != nil {
		return fmt.Errorf("failed to remove volume %s: %w", name, err)
	}
	return nil
}

// VolumeExists checks if a volume exists
func (c *Client) VolumeExists(name string) (bool, error) {
	_, err := c.cli.VolumeInspect(c.ctx, name)
	if err != nil {
		if cerrdefs.IsNotFound(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

// ListVolumes lists all Docker volumes
func (c *Client) ListVolumes() ([]*volume.Volume, error) {
	volumesResponse, err := c.cli.VolumeList(c.ctx, volume.ListOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to list volumes: %w", err)
	}
	return volumesResponse.Volumes, nil
}

// ContainerConfig holds configuration for creating a container
type ContainerConfig struct {
	Image       string
	Name        string
	Cmd         []string
	Volumes     map[string]string // volume_name -> container_path
	NetworkMode string
}

// RunContainer creates and starts a container
func (c *Client) RunContainer(config ContainerConfig) (string, error) {
	// Prepare volume binds
	var binds []string
	for volumeName, containerPath := range config.Volumes {
		binds = append(binds, fmt.Sprintf("%s:%s", volumeName, containerPath))
	}

	// Create container
	resp, err := c.cli.ContainerCreate(c.ctx,
		&container.Config{
			Image: config.Image,
			Cmd:   config.Cmd,
		},
		&container.HostConfig{
			Binds:       binds,
			NetworkMode: container.NetworkMode(config.NetworkMode),
		},
		nil, nil, config.Name)

	if err != nil {
		return "", fmt.Errorf("failed to create container: %w", err)
	}

	// Start container
	if err := c.cli.ContainerStart(c.ctx, resp.ID, container.StartOptions{}); err != nil {
		return "", fmt.Errorf("failed to start container: %w", err)
	}

	return resp.ID, nil
}

// ExecResult holds the result of a command execution
type ExecResult struct {
	ExitCode int
	Stdout   string
	Stderr   string
}

// ExecInContainer executes a command in a running container
func (c *Client) ExecInContainer(containerID string, cmd []string) (*ExecResult, error) {
	execConfig := container.ExecOptions{
		Cmd:          cmd,
		AttachStdout: true,
		AttachStderr: true,
	}

	execID, err := c.cli.ContainerExecCreate(c.ctx, containerID, execConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create exec: %w", err)
	}

	resp, err := c.cli.ContainerExecAttach(c.ctx, execID.ID, container.ExecAttachOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to attach to exec: %w", err)
	}
	defer resp.Close()

	// Read output
	output, err := io.ReadAll(resp.Reader)
	if err != nil {
		return nil, fmt.Errorf("failed to read exec output: %w", err)
	}

	// Get exit code
	inspectResp, err := c.cli.ContainerExecInspect(c.ctx, execID.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to inspect exec: %w", err)
	}

	return &ExecResult{
		ExitCode: inspectResp.ExitCode,
		Stdout:   string(output),
		Stderr:   "",
	}, nil
}

// StopContainer stops a running container
func (c *Client) StopContainer(containerID string) error {
	timeout := 10
	return c.cli.ContainerStop(c.ctx, containerID, container.StopOptions{
		Timeout: &timeout,
	})
}

// RemoveContainer removes a container
func (c *Client) RemoveContainer(containerID string, force bool) error {
	return c.cli.ContainerRemove(c.ctx, containerID, container.RemoveOptions{
		Force: force,
	})
}

// Cleanup stops and removes a container
func (c *Client) Cleanup(containerID string) error {
	// Stop container (ignore error if already stopped)
	_ = c.StopContainer(containerID)

	// Wait a bit for graceful shutdown
	time.Sleep(1 * time.Second)

	// Force remove
	return c.RemoveContainer(containerID, true)
}

// PullImage pulls a Docker image if not present
func (c *Client) PullImage(imageName string) error {
	// Check if image exists locally
	_, err := c.cli.ImageInspect(c.ctx, imageName)
	if err == nil {
		// Image exists
		return nil
	}

	// Pull image
	reader, err := c.cli.ImagePull(c.ctx, imageName, image.PullOptions{})
	if err != nil {
		return fmt.Errorf("failed to pull image %s: %w", imageName, err)
	}
	defer reader.Close()

	// Wait for pull to complete
	_, err = io.Copy(io.Discard, reader)
	return err
}
