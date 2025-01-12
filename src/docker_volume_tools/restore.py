"""Module for restoring Docker volumes from backups."""

import os
import json
import tarfile
import tempfile
from pathlib import Path
import docker

def validate_backup(backup_path: str) -> dict:
    """
    Validate backup archive structure and return metadata.
    
    Args:
        backup_path: Path to the backup archive
        
    Returns:
        dict: Backup metadata
        
    Raises:
        ValueError: If backup is invalid or corrupted
    """
    if not os.path.exists(backup_path):
        raise ValueError(f"Backup file not found: {backup_path}")
        
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract main archive
            with tarfile.open(backup_path, 'r:gz') as tar:
                tar.extractall(temp_dir)
            
            # Find backup directory (should be only one)
            contents = [p for p in Path(temp_dir).glob("*") if not p.name.startswith(".")]
            if len(contents) != 1 or not contents[0].is_dir():
                raise ValueError("Invalid backup structure")
                
            backup_dir = contents[0]
            metadata_file = backup_dir / "metadata.json"
            
            if not metadata_file.exists():
                raise ValueError("Metadata file not found in backup")
                
            with open(metadata_file) as f:
                metadata = json.load(f)
                
            # Validate metadata structure
            if "volumes" not in metadata:
                raise ValueError("Invalid metadata: missing volumes section")
                
            # Validate volume archives exist
            for volume in metadata["volumes"]:
                if "name" not in volume or "archive" not in volume:
                    raise ValueError("Invalid volume metadata")
                    
                archive_path = backup_dir / volume["archive"]
                if not archive_path.exists():
                    raise ValueError(f"Volume archive missing: {volume['archive']}")
                    
            return metadata
    except (tarfile.TarError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid backup format: {str(e)}")

def restore_volume(backup_dir: Path, volume_metadata: dict, force: bool = False) -> None:
    """
    Restore a single volume from backup.
    
    Args:
        backup_dir: Path to the extracted backup directory
        volume_metadata: Volume metadata from backup
        force: Whether to force restore even if volume exists
        
    Raises:
        ValueError: If restore fails
    """
    client = docker.from_env()
    volume_name = volume_metadata["name"]
    archive_path = backup_dir / volume_metadata["archive"]
    
    print(f"\nRestoring volume {volume_name}...")
    print(f"Archive path: {archive_path}")
    print(f"Archive exists: {archive_path.exists()}")
    
    # Check if volume exists
    try:
        volume = client.volumes.get(volume_name)
        if not force:
            raise ValueError(f"Volume {volume_name} already exists. Use --force to overwrite")
        print(f"Removing existing volume {volume_name}")
        volume.remove()
    except docker.errors.NotFound:
        print(f"Volume {volume_name} does not exist")
        pass
        
    # Create new volume
    print(f"Creating new volume {volume_name}")
    volume = client.volumes.create(volume_name)
    
    try:
        # Create temporary container to restore data
        print("Creating temporary container")
        container = client.containers.run(
            "alpine:latest",
            "tail -f /dev/null",  # Keep container running
            volumes={volume_name: {"bind": "/volume", "mode": "rw"}},
            detach=True
        )
        
        try:
            # Copy archive to container
            print(f"Copying archive to container: {container.id}")
            cp_cmd = f"docker cp {archive_path} {container.id}:/volume.tar.gz"
            print(f"Running: {cp_cmd}")
            cp_result = os.system(cp_cmd)
            print(f"Copy result: {cp_result}")
            
            # Extract archive in container
            print("Extracting archive in container")
            exec_result = container.exec_run(
                "sh -c 'cd /volume && tar xzf /volume.tar.gz --strip-components=1'"
            )
            print(f"Extract result: {exec_result.exit_code}")
            print(f"Extract output: {exec_result.output.decode()}")
            
            if exec_result.exit_code != 0:
                raise ValueError(f"Failed to extract volume data: {exec_result.output.decode()}")
                
        finally:
            print("Cleaning up container")
            container.stop()
            container.remove()
            
    except Exception as e:
        # Cleanup on error
        print(f"Error occurred, cleaning up volume: {str(e)}")
        volume.remove()
        raise ValueError(f"Failed to restore volume {volume_name}: {str(e)}")
    
    print(f"Volume {volume_name} restored successfully")

def restore_backup(backup_path: str, volumes: list[str] = None, force: bool = False) -> None:
    """
    Restore volumes from a backup archive.
    
    Args:
        backup_path: Path to the backup archive
        volumes: List of volume names to restore (None for all)
        force: Whether to force restore even if volumes exist
        
    Raises:
        ValueError: If restore fails
    """
    metadata = validate_backup(backup_path)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract main archive
        with tarfile.open(backup_path, 'r:gz') as tar:
            tar.extractall(temp_dir)
            
        # Find backup directory
        backup_dir = next(p for p in Path(temp_dir).glob("*") if p.is_dir())
        
        # Filter volumes to restore
        volumes_to_restore = metadata["volumes"]
        if volumes:
            volumes_to_restore = [
                v for v in volumes_to_restore
                if v["name"] in volumes
            ]
            if len(volumes_to_restore) != len(volumes):
                missing = set(volumes) - {v["name"] for v in volumes_to_restore}
                raise ValueError(f"Volumes not found in backup: {', '.join(missing)}")
                
        # Restore each volume
        for volume in volumes_to_restore:
            restore_volume(backup_dir, volume, force) 