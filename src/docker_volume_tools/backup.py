"""Module for backing up Docker volumes."""

import os
import json
import datetime
import tempfile
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
    volumes_to_backup: Optional[List[str]] = None,
    ssh_target: Optional[str] = None
) -> str:
    """Create a backup of Docker volumes from a compose project.
    
    Args:
        compose_file: Path to the docker-compose.yml file
        output_dir: Directory to store the backup
        compress: Whether to compress the backup
        volumes_to_backup: List of volume names to backup (None for all)
        ssh_target: Optional SSH target for direct transfer (format: user@host:path)
    
    Returns:
        Path to the backup file or SSH target path if using direct transfer
    """
    # Parse compose file
    volumes = parse_compose_file(compose_file)
    print("\nParsed volumes:")
    for v in volumes:
        print(f"- {v.name} -> {v.compose_name} (type: {v.type})")
    
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
        
    print("\nVolumes to backup:")
    for v in named_volumes:
        print(f"- {v.name} -> {v.compose_name}")
    
    # Create Docker client
    client = docker.from_env()
    
    # Generate backup name
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    project_name = os.path.splitext(os.path.basename(compose_file))[0]
    backup_name = f"{project_name}_volumes_{timestamp}"
    
    # Prepare metadata
    metadata = {
        'timestamp': timestamp,
        'project': project_name,
        'compose_file': os.path.basename(compose_file),
        'volumes': [
            {
                'name': v.compose_name,
                'service': v.service,
                'target': v.target,
                'is_external': v.is_external
            }
            for v in named_volumes
        ]
    }
    
    # Create temporary directory for metadata and SSH
    with tempfile.TemporaryDirectory() as temp_dir:
        metadata_file = os.path.join(temp_dir, 'metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Prepare volume mount options for backup container
        volume_mounts = {
            v.compose_name: {'bind': f'/volumes/{v.name}', 'mode': 'ro'}
            for v in named_volumes
        }
        volume_mounts[metadata_file] = {'bind': '/metadata.json', 'mode': 'ro'}
        
        if ssh_target:
            # Direct SSH transfer
            ssh_user_host, ssh_path = ssh_target.split(':', 1)
            remote_file = f"{ssh_path}/{backup_name}.{'tar.gz' if compress else 'tar'}"
            
            # Prepare SSH environment
            ssh_dir = os.path.join(temp_dir, '.ssh')
            os.makedirs(ssh_dir, mode=0o700)
            
            # Copy SSH config and keys
            home = os.path.expanduser("~")
            user_ssh_dir = os.path.join(home, '.ssh')
            
            # Copy known_hosts if exists
            known_hosts = os.path.join(user_ssh_dir, 'known_hosts')
            if os.path.exists(known_hosts):
                os.system(f"cp {known_hosts} {ssh_dir}/")
            
            # Copy SSH keys
            for key_file in ['id_rsa', 'id_ed25519']:
                key_path = os.path.join(user_ssh_dir, key_file)
                if os.path.exists(key_path):
                    os.system(f"cp {key_path} {ssh_dir}/")
                    os.chmod(os.path.join(ssh_dir, key_file), 0o600)
            
            # Add SSH directory to volume mounts (en lecture/écriture pour known_hosts)
            volume_mounts[ssh_dir] = {'bind': '/root/.ssh', 'mode': 'rw'}
            
            try:
                # Create and start container with SSH support
                container = client.containers.run(
                    'alpine:latest',
                    command="sleep infinity",  # Keep container running
                    volumes=volume_mounts,
                    network_mode="host",  # Important pour SSH
                    detach=True  # Run in background
                )
                
                # Install SSH in container
                print("Installing SSH client in container...")
                result = container.exec_run("apk add --no-cache openssh-client")
                if result.exit_code != 0:
                    raise BackupError(f"Failed to install SSH client: {result.output.decode()}")
                
                # Create remote directory if it doesn't exist
                print(f"Creating remote directory {ssh_path}...")
                mkdir_cmd = f"ssh -o StrictHostKeyChecking=accept-new {ssh_user_host} 'mkdir -p {ssh_path}'"
                result = container.exec_run(["/bin/sh", "-c", mkdir_cmd])
                if result.exit_code != 0:
                    raise BackupError(f"Failed to create remote directory: {result.output.decode()}")
                
                # Construire la commande tar pour créer une archive avec tous les volumes
                print("Starting backup transfer...")
                
                # Créer un répertoire temporaire pour organiser les volumes
                result = container.exec_run("mkdir -p /tmp_backup")
                if result.exit_code != 0:
                    raise BackupError("Failed to create temporary directory")
                
                # Copier le metadata
                result = container.exec_run("cp /metadata.json /tmp_backup/")
                if result.exit_code != 0:
                    raise BackupError("Failed to copy metadata")
                
                # Créer des liens symboliques vers les volumes dans le répertoire temporaire
                result = container.exec_run("mkdir -p /tmp_backup/volumes")
                if result.exit_code != 0:
                    raise BackupError("Failed to create volumes directory")
                
                # Créer des liens symboliques vers chaque volume
                for v in named_volumes:
                    print(f"Adding volume {v.name} to backup...")
                    result = container.exec_run(f"ln -s /volumes/{v.name} /tmp_backup/volumes/{v.name}")
                    if result.exit_code != 0:
                        raise BackupError(f"Failed to create symlink for volume {v.name}")
                
                # Créer l'archive tar avec tous les fichiers
                # Utiliser -h pour suivre les liens symboliques
                tar_cmd = "cd /tmp_backup && tar -hcf - ."
                if compress:
                    tar_cmd = f"({tar_cmd}) | gzip"
                
                # Pipe vers SSH
                ssh_cmd = f"ssh -o StrictHostKeyChecking=accept-new {ssh_user_host} 'cat > {remote_file}'"
                full_cmd = f"{tar_cmd} | {ssh_cmd}"
                
                # Exécuter la commande
                result = container.exec_run(
                    ["/bin/sh", "-c", full_cmd],
                    demux=True  # Separate stdout/stderr
                )
                
                if result.exit_code != 0:
                    error_msg = result.output[1].decode() if result.output[1] else "Unknown error"
                    raise BackupError(f"Backup transfer failed: {error_msg}")
                
                # Nettoyer le répertoire temporaire
                container.exec_run("rm -rf /tmp_backup")
                
                return remote_file
                
            except Exception as e:
                print(f"Error during SSH transfer: {str(e)}")
                raise BackupError(f"Failed to transfer backup via SSH: {str(e)}")
            finally:
                # Cleanup
                try:
                    container.stop()
                    container.remove()
                except:
                    pass
        else:
            # Local backup
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            backup_dir = os.path.join(output_dir, backup_name)
            os.makedirs(backup_dir)
            
            # Backup each volume locally
            for volume in named_volumes:
                print(f"\nBacking up volume {volume.compose_name}...")
                tar_name = f"{volume.name}.{'tar.gz' if compress else 'tar'}"
                tar_cmd = f"tar {'cz' if compress else 'c'}f /backup/{tar_name} -C /volumes/{volume.name} ."
                
                try:
                    backup_container = client.containers.run(
                        'alpine:latest',
                        command=tar_cmd,
                        volumes={
                            volume.compose_name: {'bind': f'/volumes/{volume.name}', 'mode': 'ro'},
                            backup_dir: {'bind': '/backup', 'mode': 'rw'}
                        },
                        remove=True
                    )
                except Exception as e:
                    print(f"Error backing up volume {volume.compose_name}: {str(e)}")
                    raise BackupError(f"Failed to backup volume {volume.compose_name}: {str(e)}")
            
            # Copy metadata
            os.system(f"cp {metadata_file} {backup_dir}/metadata.json")
            
            # Create final archive
            final_archive = os.path.join(output_dir, f"{backup_name}.{'tar.gz' if compress else 'tar'}")
            archive_cmd = f"tar {'cz' if compress else 'c'}f {final_archive} -C {output_dir} {backup_name}"
            os.system(archive_cmd)
            
            # Cleanup temporary directory
            os.system(f"rm -rf {backup_dir}")
            
            return final_archive

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