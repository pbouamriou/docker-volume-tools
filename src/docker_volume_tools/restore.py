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
            volume_files = [m for m in tar.getmembers() 
                           if m.name.startswith('volumes/') or m.name.startswith('./volumes/')]
            if not volume_files:
                raise ValueError("No volume files found in backup")
            
            # Correction : extraire correctement les noms de volumes
            volume_dirs = set()
            for member in tar.getmembers():
                name = member.name
                if name.startswith('volumes/'):
                    parts = name.split('/')
                    if len(parts) > 1:
                        volume_dirs.add(parts[1])
                elif name.startswith('./volumes/'):
                    parts = name.split('/')
                    if len(parts) > 2:
                        volume_dirs.add(parts[2])
            
            # Vérifier que tous les volumes référencés dans le metadata existent
            for volume in metadata["volumes"]:
                if "name" not in volume:
                    raise ValueError("Invalid volume metadata: missing name")
                
                archive_path = volume.get("archive_path", volume["name"])
                print(f"\nValidating volume: {volume['name']}")
                print(f"Looking for archive path: {archive_path}")
                
                volume_paths = [
                    f"volumes/{archive_path}/",
                    f"./volumes/{archive_path}/",
                    f"volumes/{volume['name']}/",
                    f"./volumes/{volume['name']}/"
                ]
                
                volume_members = []
                found_path = None
                for path in volume_paths:
                    members = [m for m in tar.getmembers() if m.name.startswith(path)]
                    if members:
                        volume_members.extend(members)
                        found_path = path
                        print(f"✅ Found volume directory with path: {path}")
                        break
                
                if not volume_members:
                    print(f"❌ Volume directory not found with exact paths: {', '.join(volume_paths)}")
                    print(f"🔍 Trying alternative paths...")
                    possible_prefixes = [
                        f"volumes/{volume['name'].replace('-', '_')}/",
                        f"./volumes/{volume['name'].replace('-', '_')}/",
                        f"volumes/{volume['name'].lower()}/",
                        f"./volumes/{volume['name'].lower()}/",
                        f"volumes/{volume['name'].replace('-', '').replace('_', '')}/",
                        f"./volumes/{volume['name'].replace('-', '').replace('_', '')}/"
                    ]
                    for member in tar.getmembers():
                        for prefix in possible_prefixes:
                            if member.name.startswith(prefix):
                                found_path = prefix
                                print(f"✅ Found volume directory with prefix: {prefix}")
                                break
                        if found_path:
                            break
                    if not found_path:
                        print(f"❌ No matching directory found with standard variations")
                        print(f"🔍 Searching for similar directories in archive...")
                        print(f"📁 Available volume directories in archive: {', '.join(sorted(volume_dirs))}")
                        for dir_name in volume_dirs:
                            if dir_name == archive_path:
                                found_path = f"volumes/{dir_name}/"
                                print(f"✅ Found exact archive_path directory: {found_path}")
                                break
                        if not found_path:
                            print(f"❌ No matching directory found in archive")
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
                    
                    print(f"Looking for volume with prefix: {volume_prefix} or {volume_prefix_with_dot}")
                    
                    # Vérifier si le préfixe existe dans l'archive
                    volume_members = [m for m in tar.getmembers() 
                                     if m.name.startswith(volume_prefix) or m.name.startswith(volume_prefix_with_dot)]
                    
                    if not volume_members:
                        print(f"❌ Volume directory not found with exact path: {volume_prefix} or {volume_prefix_with_dot}")
                        print(f"🔍 Searching for exact archive_path in archive...")
                        # Recherche stricte dans la liste des dossiers de volumes
                        volume_dirs = set()
                        for member in tar.getmembers():
                            name = member.name
                            if name.startswith('volumes/'):
                                parts = name.split('/')
                                if len(parts) > 1:
                                    volume_dirs.add(parts[1])
                            elif name.startswith('./volumes/'):
                                parts = name.split('/')
                                if len(parts) > 2:
                                    volume_dirs.add(parts[2])
                        print(f"📁 Available volume directories in archive: {', '.join(sorted(volume_dirs))}")
                        if archive_path in volume_dirs:
                            volume_prefix = f"volumes/{archive_path}/"
                            print(f"✅ Found exact archive_path directory: {volume_prefix}")
                        else:
                            print(f"❌ No matching directory found in archive")
                            raise ValueError(f"Volume directory not found: {volume_name}")
                    # Extraire les fichiers du volume
                    print(f"\nExtracting files with prefix: {volume_prefix}")
                    # Première passe : extraire fichiers et dossiers (pas les symlinks)
                    for member in tar.getmembers():
                        for prefix in [volume_prefix, volume_prefix_with_dot]:
                            if member.name.startswith(prefix):
                                rel_name = member.name[len(prefix):]
                                if not rel_name:
                                    break
                                if member.issym():
                                    # On traitera les symlinks dans une seconde passe
                                    break
                                member.name = rel_name
                                print(f"Extracting: {rel_name}")
                                tar.extract(member, temp_volume_dir)
                                break
                    # Deuxième passe : créer les symlinks
                    for member in tar.getmembers():
                        for prefix in [volume_prefix, volume_prefix_with_dot]:
                            if member.name.startswith(prefix):
                                rel_name = member.name[len(prefix):]
                                if not rel_name:
                                    break
                                if member.issym():
                                    target_path = os.path.join(temp_volume_dir, rel_name)
                                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                    print(f"Creating symlink: {rel_name} -> {member.linkname}")
                                    try:
                                        os.symlink(member.linkname, target_path)
                                    except FileExistsError:
                                        pass
                                break
                    # Affichage intelligent du contenu extrait
                    print(f"\n[DEBUG] Temporary extracted directory: {temp_volume_dir}")
                    file_count = 0
                    max_files = 10
                    print("[DEBUG] First files extracted:")
                    for root, dirs, files in os.walk(temp_volume_dir):
                        for name in files:
                            rel_path = os.path.relpath(os.path.join(root, name), temp_volume_dir)
                            if file_count < max_files:
                                print(f"  - {rel_path}")
                            file_count += 1
                    if file_count > max_files:
                        print(f"  ... and {file_count - max_files} more files ...")
                    print(f"[DEBUG] Total files extracted: {file_count}")
                    # Copier le contenu du répertoire temporaire vers le conteneur
                    print(f"\nCopying volume data to container: {container.id}")
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