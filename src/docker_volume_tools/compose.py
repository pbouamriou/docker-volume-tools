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
                        is_external = bool(named_volumes[source].get('external', False))
                    else:
                        volume_type = 'bind'
                        is_external = False
                        
                    volumes.append(VolumeInfo(
                        name=source,
                        service=service_name,
                        type=volume_type,
                        source=source,
                        target=target,
                        is_external=is_external
                    ))
                    
            # Handle long syntax (dictionary)
            elif isinstance(volume, dict):
                source = volume.get('source', '')
                target = volume.get('target', '')
                volume_type = volume.get('type', 'volume')
                
                if volume_type == 'volume':
                    is_external = bool(named_volumes.get(source, {}).get('external', False))
                    volumes.append(VolumeInfo(
                        name=source,
                        service=service_name,
                        type='named',
                        source=source,
                        target=target,
                        is_external=is_external
                    ))
                elif volume_type == 'bind':
                    volumes.append(VolumeInfo(
                        name=source,
                        service=service_name,
                        type='bind',
                        source=source,
                        target=target,
                        is_external=False
                    ))
                    
    return volumes 