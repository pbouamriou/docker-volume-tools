"""Docker Compose file parser and analyzer."""

import os
from typing import Dict, List, Optional
import yaml
from dataclasses import dataclass

@dataclass
class VolumeInfo:
    """Information about a volume in a Docker Compose project."""
    name: str
    service: str
    type: str  # 'named' or 'bind'
    source: str
    target: str
    is_external: bool = False
    compose_name: Optional[str] = None  # Le nom complet avec le préfixe du projet

def get_project_name(compose_path: str) -> str:
    """Get the project name from the compose file path.
    
    By default, Docker Compose uses the directory name as the project name.
    
    Args:
        compose_path: Path to the docker-compose.yml file
        
    Returns:
        Project name
    """
    return os.path.basename(os.path.dirname(os.path.abspath(compose_path)))

def parse_compose_file(compose_path: str) -> List[VolumeInfo]:
    """Parse a docker-compose.yml file and extract volume information.
    
    Args:
        compose_path: Path to the docker-compose.yml file
        
    Returns:
        List of VolumeInfo objects describing each volume
        
    Raises:
        FileNotFoundError: If compose file doesn't exist
        yaml.YAMLError: If compose file is invalid
    """
    if not os.path.exists(compose_path):
        raise FileNotFoundError(f"Compose file not found: {compose_path}")
        
    with open(compose_path, 'r') as f:
        compose_data = yaml.safe_load(f)
        
    if not compose_data:
        return []
        
    volumes: List[VolumeInfo] = []
    project_name = get_project_name(compose_path)
    
    # Parse top-level volumes section
    named_volumes = compose_data.get('volumes', {})
    
    # Parse services section
    services = compose_data.get('services', {})
    for service_name, service_data in services.items():
        service_volumes = service_data.get('volumes', [])
        
        for volume in service_volumes:
            # Handle short syntax (string)
            if isinstance(volume, str):
                parts = volume.split(':')
                if len(parts) >= 2:
                    source, target = parts[0:2]
                    # Determine if it's a named volume or bind mount
                    if source in named_volumes:
                        volume_type = 'named'
                        # Handle case where volume has no configuration (value is None)
                        volume_config = named_volumes[source] or {}
                        is_external = bool(volume_config.get('external', False))
                        # Use explicit name if provided, otherwise use project_name prefix
                        compose_name = volume_config.get('name', f"{project_name}_{source}")
                    else:
                        volume_type = 'bind'
                        is_external = False
                        compose_name = source
                        
                    volumes.append(VolumeInfo(
                        name=source,
                        service=service_name,
                        type=volume_type,
                        source=source,
                        target=target,
                        is_external=is_external,
                        compose_name=compose_name
                    ))
                    
            # Handle long syntax (dictionary)
            elif isinstance(volume, dict):
                source = volume.get('source', '')
                target = volume.get('target', '')
                volume_type = volume.get('type', 'volume')
                
                if volume_type == 'volume':
                    # Handle case where volume has no configuration (value is None)
                    volume_config = named_volumes.get(source) or {}
                    is_external = bool(volume_config.get('external', False))
                    # Use explicit name if provided, otherwise use project_name prefix
                    compose_name = volume_config.get('name', f"{project_name}_{source}")
                    volumes.append(VolumeInfo(
                        name=source,
                        service=service_name,
                        type='named',
                        source=source,
                        target=target,
                        is_external=is_external,
                        compose_name=compose_name
                    ))
                elif volume_type == 'bind':
                    volumes.append(VolumeInfo(
                        name=source,
                        service=service_name,
                        type='bind',
                        source=source,
                        target=target,
                        is_external=False,
                        compose_name=source
                    ))
                    
    return volumes 