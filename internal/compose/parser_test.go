package compose

import (
	"path/filepath"
	"testing"
)

func TestParseComposeFile(t *testing.T) {
	// Use testdata compose file
	composePath := filepath.Join("..", "..", "test", "testdata", "docker-compose.yml")

	volumes, err := ParseComposeFile(composePath)
	if err != nil {
		t.Fatalf("Failed to parse compose file: %v", err)
	}

	// Should have 4 volumes total (2 named + 2 bind mounts, but bind may appear twice if shared)
	if len(volumes) < 3 {
		t.Errorf("Expected at least 3 volumes, got %d", len(volumes))
	}

	// Check for named volumes
	var postgresVol, redisVol *interface{}
	for i := range volumes {
		vol := &volumes[i]
		if vol.Name == "postgres_data" && vol.Type == "named" {
			postgresVol = new(interface{})
			if vol.Target != "/var/lib/postgresql/data" {
				t.Errorf("Postgres volume target mismatch: got %s", vol.Target)
			}
			if vol.Service != "database" {
				t.Errorf("Postgres volume service mismatch: got %s", vol.Service)
			}
			// Check compose name has project prefix
			if vol.ComposeName != "testdata_postgres_data" {
				t.Errorf("Postgres compose name mismatch: got %s", vol.ComposeName)
			}
		}
		if vol.Name == "redis_data" && vol.Type == "named" {
			redisVol = new(interface{})
			if vol.Target != "/data" {
				t.Errorf("Redis volume target mismatch: got %s", vol.Target)
			}
			if vol.Service != "redis" {
				t.Errorf("Redis volume service mismatch: got %s", vol.Service)
			}
		}
	}

	if postgresVol == nil {
		t.Error("postgres_data volume not found")
	}
	if redisVol == nil {
		t.Error("redis_data volume not found")
	}
}

func TestGetProjectName(t *testing.T) {
	tests := []struct {
		path     string
		expected string
	}{
		{"/home/user/myproject/docker-compose.yml", "myproject"},
		{"./testdata/docker-compose.yml", "testdata"},
		{"../testdata/docker-compose.yml", "testdata"},
	}

	for _, tt := range tests {
		result := GetProjectName(tt.path)
		if result != tt.expected {
			t.Errorf("GetProjectName(%s) = %s, want %s", tt.path, result, tt.expected)
		}
	}
}
