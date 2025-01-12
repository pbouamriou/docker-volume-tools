"""Module for backing up Docker volumes."""

import os
import json
import datetime
from typing import Dict, List, Optional
import docker
from docker.models.volumes import Volume
from .compose import VolumeInfo, parse_compose_file

class BackupError(Exception):
    """Error during backup operation."""
    pass

def create_backup(
    compose_file: str,
    output_dir: str,
    compress: bool = True,
    volumes_to_backup: Optional[List[str]] = None
) -> str:
    """Create a backup of Docker volumes from a compose project.
    
    Args:
        compose_file: Path to the docker-compose.yml file
        output_dir: Directory where to store the backup
        compress: Whether to compress the backup
        volumes_to_backup: List of volume names to backup (None for all)
        
    Returns:
        Path to the created backup archive
        
    Raises:
        BackupError: If backup operation fails
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Parse compose file
    volumes = parse_compose_file(compose_file)
    
    # Filter volumes if needed
    if volumes_to_backup:
        volumes = [v for v in volumes if v.name in volumes_to_backup]
        
    if not volumes:
        raise BackupError("No volumes to backup")
    
    # Filter out bind mounts and deduplicate volumes by name
    volume_dict = {}
    for volume in volumes:
        if volume.type == 'named':
            # Keep only the first occurrence of each volume (primary service)
            if volume.name not in volume_dict:
                volume_dict[volume.name] = volume
    
    named_volumes = list(volume_dict.values())
    if not named_volumes:
        raise BackupError("No named volumes to backup")
    
    # Create Docker client
    client = docker.from_env()
    
    # Create backup container
    container = client.containers.create(
        'alpine:latest',
        command='sleep infinity',  # Keep container running
        volumes={
            v.name: {'bind': f'/volumes/{v.name}', 'mode': 'ro'}
            for v in named_volumes
        }
    )
    
    try:
        # Start container
        container.start()
        
        # Generate backup name
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        project_name = os.path.splitext(os.path.basename(compose_file))[0]
        backup_name = f"{project_name}_volumes_{timestamp}"
        backup_dir = os.path.join(output_dir, backup_name)
        os.makedirs(backup_dir)
        
        # Backup each volume
        for volume in named_volumes:
            # Create tar archive
            tar_name = f"{volume.name}.tar.gz" if compress else f"{volume.name}.tar"
            tar_cmd = f"tar {'cz' if compress else 'c'}f /backup/{tar_name} -C /volumes/{volume.name} ."
            
            # Mount backup directory and create archive
            backup_container = client.containers.run(
                'alpine:latest',
                command=tar_cmd,
                volumes={
                    volume.name: {'bind': f'/volumes/{volume.name}', 'mode': 'ro'},
                    backup_dir: {'bind': '/backup', 'mode': 'rw'}
                },
                remove=True
            )
            
        # Save metadata
        metadata = {
            'timestamp': timestamp,
            'project': project_name,
            'compose_file': os.path.basename(compose_file),
            'volumes': [
                {
                    'name': v.name,
                    'service': v.service,
                    'target': v.target,
                    'is_external': v.is_external,
                    'archive': f"{v.name}.tar.gz" if compress else f"{v.name}.tar"
                }
                for v in named_volumes
            ]
        }
        
        with open(os.path.join(backup_dir, 'metadata.json'), 'w') as f:
            json.dump(metadata, f, indent=2)
            
        # Create final archive
        final_archive = os.path.join(output_dir, f"{backup_name}.tar.gz" if compress else f"{backup_name}.tar")
        archive_cmd = f"tar {'cz' if compress else 'c'}f {final_archive} -C {output_dir} {backup_name}"
        os.system(archive_cmd)
        
        # Cleanup temporary directory
        os.system(f"rm -rf {backup_dir}")
        
        return final_archive
            
    finally:
        # Cleanup
        container.stop()
        container.remove()
        
def get_volume_size(volume: Volume) -> str:
    """Get the size of a Docker volume.
    
    Args:
        volume: Docker volume object
        
    Returns:
        Human readable size string
    """
    try:
        # Create temporary container to check size
        container = docker.from_env().containers.run(
            'alpine:latest',
            command=f"du -sh /volume",
            volumes={volume.name: {'bind': '/volume', 'mode': 'ro'}},
            remove=True
        )
        size = container.decode().split()[0]
        return size
    except Exception:
        return "unknown" 