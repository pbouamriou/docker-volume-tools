"""Integration tests for Docker Volume Tools."""

import os
import json
import shutil
import tempfile
import tarfile
from pathlib import Path
import docker
import pytest
from click.testing import CliRunner
from docker_volume_tools.cli import cli

@pytest.fixture
def docker_client():
    """Create a Docker client."""
    return docker.from_env()

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def example_compose_dir(temp_dir):
    """Create a temporary directory with example docker-compose setup."""
    compose_dir = Path(temp_dir) / "compose_test"
    compose_dir.mkdir()
    
    # Create docker-compose.yml
    compose_content = """
services:
  database:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: testpassword
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d

  redis:
    image: redis:7
    volumes:
      - type: volume
        source: redis_data
        target: /data

volumes:
  postgres_data: {}  # Le nom sera automatiquement préfixé par compose_test_
  redis_data: {}     # Le nom sera automatiquement préfixé par compose_test_
"""
    compose_file = compose_dir / "docker-compose.yml"
    compose_file.write_text(compose_content)
    
    print("\nDocker Compose content:")
    print(compose_content)
    
    # Create init-scripts directory with test SQL
    init_scripts_dir = compose_dir / "init-scripts"
    init_scripts_dir.mkdir()
    init_sql = """
CREATE TABLE test_data (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);
INSERT INTO test_data (name) VALUES ('Test 1'), ('Test 2');
"""
    (init_scripts_dir / "init.sql").write_text(init_sql)
    
    yield compose_dir

def test_backup_workflow(docker_client, temp_dir, example_compose_dir):
    """Test the complete backup workflow."""
    runner = CliRunner()
    backup_dir = Path(temp_dir) / "backups"
    network_name = "test_network"
    containers = []
    volumes = []
    
    try:
        # Create network
        network = docker_client.networks.create(network_name)
        
        # Create and populate initial volumes
        postgres_volume = docker_client.volumes.create("compose_test_postgres_data")
        redis_volume = docker_client.volumes.create("compose_test_redis_data")
        volumes.extend([postgres_volume, redis_volume])
        
        # Start services to populate volumes
        db = docker_client.containers.run(
            "postgres:15",
            environment={"POSTGRES_PASSWORD": "testpassword"},
            volumes={
                "compose_test_postgres_data": {"bind": "/var/lib/postgresql/data", "mode": "rw"},
                str(example_compose_dir / "init-scripts"): {"bind": "/docker-entrypoint-initdb.d", "mode": "ro"}
            },
            network=network_name,
            detach=True,
            name="test_database"
        )
        containers.append(db)
        
        redis = docker_client.containers.run(
            "redis:7",
            volumes={
                "compose_test_redis_data": {"bind": "/data", "mode": "rw"}
            },
            network=network_name,
            detach=True,
            name="test_redis"
        )
        containers.append(redis)
        
        # Wait for services to be ready
        import time
        time.sleep(5)
        
        # Test list command
        result = runner.invoke(cli, ['list', str(example_compose_dir / "docker-compose.yml")])
        assert result.exit_code == 0
        assert "postgres_data" in result.output
        assert "redis_data" in result.output
        assert "Named volumes: 2" in result.output
        
        # Test backup command
        result = runner.invoke(cli, [
            'backup',
            str(example_compose_dir / "docker-compose.yml"),
            '--output-dir', str(backup_dir)
        ], input='y\n')
        assert result.exit_code == 0
        assert "Backup completed successfully!" in result.output
        
        # Verify backup structure
        backup_files = list(backup_dir.glob("*.tar.gz"))
        assert len(backup_files) == 1
        backup_file = backup_files[0]
        
        with tempfile.TemporaryDirectory() as extract_dir:
            # Extract main archive
            with tarfile.open(backup_file, 'r:gz') as tar:
                tar.extractall(extract_dir)
            
            # Ignore hidden files (macOS metadata)
            backup_contents = [
                p for p in Path(extract_dir).glob("*")
                if not p.name.startswith(".")
            ]
            assert len(backup_contents) == 1
            backup_dir = backup_contents[0]
            
            # Check metadata.json
            with open(backup_dir / "metadata.json") as f:
                metadata = json.load(f)
                assert "volumes" in metadata
                volumes = {v["name"] for v in metadata["volumes"]}
                assert "compose_test_postgres_data" in volumes
                assert "compose_test_redis_data" in volumes
                assert len(metadata["volumes"]) == 2  # Vérifie la déduplication
                
                # Verify archive extensions
                for volume in metadata["volumes"]:
                    assert volume["archive"].endswith(".tar.gz")
                    assert (backup_dir / volume["archive"]).exists()
    
    finally:
        # Cleanup
        for container in containers:
            try:
                container.stop()
                container.remove()
            except:
                pass
            
        for volume in volumes:
            try:
                volume.remove()
            except:
                pass
            
        try:
            network.remove()
        except:
            pass 

def test_restore_workflow(docker_client, temp_dir, example_compose_dir):
    """Test the complete restore workflow."""
    runner = CliRunner()
    backup_dir = Path(temp_dir) / "backups"
    network_name = "test_network"
    containers = []
    volumes = []
    
    try:
        # Create network
        network = docker_client.networks.create(network_name)
        
        # Create and populate initial volumes
        postgres_volume = docker_client.volumes.create("compose_test_postgres_data")
        redis_volume = docker_client.volumes.create("compose_test_redis_data")
        volumes.extend([postgres_volume, redis_volume])
        
        # Start services to populate volumes
        db = docker_client.containers.run(
            "postgres:15",
            environment={"POSTGRES_PASSWORD": "testpassword"},
            volumes={
                "compose_test_postgres_data": {"bind": "/var/lib/postgresql/data", "mode": "rw"},
                str(example_compose_dir / "init-scripts"): {"bind": "/docker-entrypoint-initdb.d", "mode": "ro"}
            },
            network=network_name,
            detach=True,
            name="test_database"
        )
        containers.append(db)
        
        redis = docker_client.containers.run(
            "redis:7",
            volumes={
                "compose_test_redis_data": {"bind": "/data", "mode": "rw"}
            },
            network=network_name,
            detach=True,
            name="test_redis"
        )
        containers.append(redis)
        
        # Wait for services to be ready
        import time
        time.sleep(5)
        
        # Create backup
        result = runner.invoke(cli, [
            'backup',
            str(example_compose_dir / "docker-compose.yml"),
            '--output-dir', str(backup_dir)
        ], input='y\n')
        assert result.exit_code == 0
        
        # Stop and remove containers
        for container in containers:
            container.stop()
            container.remove()
        containers.clear()
        
        # Remove volumes
        for volume in volumes:
            volume.remove()
        volumes.clear()
        
        # Find backup file
        backup_files = list(backup_dir.glob("*.tar.gz"))
        assert len(backup_files) == 1
        backup_file = backup_files[0]
        
        # Debug: Print metadata content
        with tempfile.TemporaryDirectory() as debug_dir:
            with tarfile.open(backup_file, 'r:gz') as tar:
                tar.extractall(debug_dir)
            backup_dir = next(p for p in Path(debug_dir).glob("*") if p.is_dir())
            with open(backup_dir / "metadata.json") as f:
                print("\nMetadata content:")
                print(json.dumps(json.load(f), indent=2))

        # Test restore command
        result = runner.invoke(cli, [
            'restore',
            str(backup_file),
            '--force'
        ], input='y\n')
        print("\nRestore command output:")
        print(result.output)
        assert result.exit_code == 0
        
        # Verify volumes were restored
        restored_volumes = docker_client.volumes.list()
        restored_names = {v.name for v in restored_volumes}
        assert "compose_test_postgres_data" in restored_names
        assert "compose_test_redis_data" in restored_names
        
        # Start services again to verify data
        db = docker_client.containers.run(
            "postgres:15",
            environment={"POSTGRES_PASSWORD": "testpassword"},
            volumes={
                "compose_test_postgres_data": {"bind": "/var/lib/postgresql/data", "mode": "rw"}
            },
            network=network_name,
            detach=True,
            name="test_database_restored"
        )
        containers.append(db)
        
        # Wait for PostgreSQL to start
        time.sleep(5)
        
        # Verify data was restored
        exec_result = db.exec_run(
            'psql -U postgres -c "SELECT COUNT(*) FROM test_data;"'
        )
        assert exec_result.exit_code == 0
        assert "2" in exec_result.output.decode()  # We inserted 2 rows in init.sql
        
    finally:
        # Cleanup
        for container in containers:
            try:
                container.stop()
                container.remove()
            except:
                pass
            
        for volume in volumes:
            try:
                volume.remove()
            except:
                pass
            
        try:
            network.remove()
        except:
            pass 