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
        # Ouvrir l'archive sans l'extraire
        with tarfile.open(backup_path, 'r:gz') as tar:
            # Vérifier la présence du fichier metadata.json
            # Prendre en compte les chemins avec ou sans './' au début
            metadata_members = [m for m in tar.getmembers() 
                               if m.name == 'metadata.json' or m.name == './metadata.json']
            if not metadata_members:
                raise ValueError("Metadata file not found in backup")
            
            # Extraire uniquement le fichier metadata.json
            metadata_member = metadata_members[0]
            metadata_content = tar.extractfile(metadata_member)
            if metadata_content is None:
                raise ValueError("Could not read metadata file")
                
            # Charger le contenu du metadata
            metadata = json.loads(metadata_content.read().decode('utf-8'))
            
            # Validate metadata structure
            if "volumes" not in metadata:
                raise ValueError("Invalid metadata: missing volumes section")
            
            # Vérifier la présence de fichiers dans le dossier volumes
            # Au lieu de chercher un dossier volumes spécifique, on vérifie qu'il y a des fichiers
            # qui commencent par volumes/ ou ./volumes/
            volume_files = [m for m in tar.getmembers() 
                           if m.name.startswith('volumes/') or m.name.startswith('./volumes/')]
            if not volume_files:
                raise ValueError("No volume files found in backup")
            
            # Vérifier que tous les volumes référencés dans le metadata existent
            for volume in metadata["volumes"]:
                if "name" not in volume:
                    raise ValueError("Invalid volume metadata: missing name")
                
                # Prendre en compte les chemins avec ou sans './' au début
                volume_path = f"volumes/{volume['name']}/"
                volume_path_with_dot = f"./volumes/{volume['name']}/"
                volume_members = [m for m in tar.getmembers() 
                                 if m.name.startswith(volume_path) or m.name.startswith(volume_path_with_dot)]
                if not volume_members:
                    raise ValueError(f"Volume directory not found: {volume['name']}")
            
            return metadata
    except (tarfile.TarError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid backup format: {str(e)}")

def restore_volume(backup_path: str, volume_metadata: dict, force: bool = False) -> None:
    """
    Restore a single volume from backup.
    
    Args:
        backup_path: Path to the backup archive
        volume_metadata: Volume metadata from backup
        force: Whether to force restore even if volume exists
        
    Raises:
        ValueError: If restore fails
    """
    client = docker.from_env()
    volume_name = volume_metadata["name"]
    
    # Récupérer le chemin exact dans l'archive si disponible
    archive_path = volume_metadata.get("archive_path", volume_name)
    
    print(f"\nRestoring volume {volume_name}...")
    print(f"Archive path: {archive_path}")
    
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
            # Créer un répertoire temporaire pour extraire les données du volume
            with tempfile.TemporaryDirectory() as temp_volume_dir:
                # Extraire uniquement les fichiers du volume spécifique
                with tarfile.open(backup_path, 'r:gz') as tar:
                    # Utiliser le chemin exact dans l'archive
                    volume_prefix = f"volumes/{archive_path}/"
                    volume_prefix_with_dot = f"./volumes/{archive_path}/"
                    
                    # Vérifier si le préfixe existe dans l'archive
                    volume_members = [m for m in tar.getmembers() 
                                     if m.name.startswith(volume_prefix) or m.name.startswith(volume_prefix_with_dot)]
                    
                    if not volume_members:
                        # Si le chemin exact n'est pas trouvé, essayer les variations comme avant
                        print(f"Volume directory not found with exact path, trying variations...")
                        possible_prefixes = [
                            f"volumes/{volume_name}/",
                            f"./volumes/{volume_name}/",
                            # Essayer avec des variations du nom (remplacer les caractères spéciaux)
                            f"volumes/{volume_name.replace('-', '_')}/",
                            f"./volumes/{volume_name.replace('-', '_')}/",
                            # Essayer avec le nom en minuscules
                            f"volumes/{volume_name.lower()}/",
                            f"./volumes/{volume_name.lower()}/",
                            # Essayer avec le nom sans caractères spéciaux
                            f"volumes/{volume_name.replace('-', '').replace('_', '')}/",
                            f"./volumes/{volume_name.replace('-', '').replace('_', '')}/"
                        ]
                        
                        # Parcourir tous les membres de l'archive pour trouver le préfixe
                        for member in tar.getmembers():
                            for prefix in possible_prefixes:
                                if member.name.startswith(prefix):
                                    volume_prefix = prefix
                                    print(f"Found volume directory with prefix: {volume_prefix}")
                                    break
                            if volume_prefix:
                                break
                        
                        if not volume_prefix:
                            # Si aucun préfixe n'est trouvé, essayer de trouver un dossier qui pourrait correspondre
                            print(f"Volume directory not found with exact name, searching for similar directories...")
                            all_members = tar.getmembers()
                            volume_dirs = set()
                            
                            # Collecter tous les dossiers de volumes
                            for member in all_members:
                                if member.name.startswith('volumes/') or member.name.startswith('./volumes/'):
                                    parts = member.name.split('/')
                                    if len(parts) >= 3:  # volumes/nom_du_volume/...
                                        volume_dirs.add(parts[1])
                            
                            print(f"Available volume directories: {', '.join(volume_dirs)}")
                            
                            # Essayer de trouver un dossier qui pourrait correspondre au volume
                            for dir_name in volume_dirs:
                                # Vérifier si le nom du dossier est similaire au nom du volume
                                if (dir_name.lower() == volume_name.lower() or
                                    dir_name.replace('-', '_') == volume_name.replace('-', '_') or
                                    dir_name.replace('-', '').replace('_', '') == volume_name.replace('-', '').replace('_', '')):
                                    volume_prefix = f"volumes/{dir_name}/"
                                    print(f"Found similar volume directory: {volume_prefix}")
                                    break
                            
                            if not volume_prefix:
                                raise ValueError(f"Volume directory not found: {volume_name}")
                    
                    # Extraire les fichiers du volume
                    for member in tar.getmembers():
                        if member.name.startswith(volume_prefix):
                            # Ajuster le chemin pour l'extraction
                            member.name = member.name[len(volume_prefix):]
                            tar.extract(member, temp_volume_dir)
                
                # Copier le contenu du répertoire temporaire vers le conteneur
                print(f"Copying volume data to container: {container.id}")
                cp_cmd = f"docker cp {temp_volume_dir}/. {container.id}:/volume/"
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
        restore_volume(backup_path, volume, force) 