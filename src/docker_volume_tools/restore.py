"""Module for restoring Docker volumes from backups."""

import os
import json
import tarfile
import tempfile
from typing import List, Optional
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
                
            # Vérifier que le répertoire volumes existe
            volumes_dir = backup_dir / "volumes"
            if not volumes_dir.exists() or not volumes_dir.is_dir():
                raise ValueError("Volumes directory not found in backup")
                
            # Vérifier que tous les volumes référencés dans le metadata existent
            for volume in metadata["volumes"]:
                if "name" not in volume:
                    raise ValueError("Invalid volume metadata: missing name")
                    
                volume_dir = volumes_dir / volume["name"]
                if not volume_dir.exists() or not volume_dir.is_dir():
                    raise ValueError(f"Volume directory not found: {volume['name']}")
                    
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
    volume_dir = backup_dir / "volumes" / volume_name
    
    print(f"\nRestoring volume {volume_name}...")
    print(f"Volume directory: {volume_dir}")
    print(f"Directory exists: {volume_dir.exists()}")
    
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
            # Copier le contenu du répertoire du volume vers le conteneur
            print(f"Copying volume data to container: {container.id}")
            cp_cmd = f"docker cp {volume_dir}/. {container.id}:/volume/"
            print(f"Running: {cp_cmd}")
            cp_result = os.system(cp_cmd)
            print(f"Copy result: {cp_result}")
            
            if cp_result != 0:
                raise ValueError(f"Failed to copy volume data: {cp_result}")
                
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

def restore_backup(backup_path: str, volumes: Optional[List[str]] = None, force: bool = False) -> None:
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