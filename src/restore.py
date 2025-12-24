import time
import subprocess
from log import logger

def restore_volume(volume_name: str, backup_path: str, archive_path: str) -> None:
    """Restore a Docker volume from a backup archive."""
    try:
        # Create a temporary container to restore the volume
        container_name = f"restore_{volume_name}_{int(time.time())}"
        volume_path = f"/volumes/{volume_name}"
        
        # Create container with the volume mounted
        subprocess.run([
            "docker", "run", "--rm", "-d",
            "--name", container_name,
            "-v", f"{volume_name}:{volume_path}",
            "alpine:latest",
            "tail", "-f", "/dev/null"
        ], check=True)
        
        try:
            # First pass: extract all regular files
            logger.info("First pass: extracting regular files...")
            subprocess.run([
                "docker", "exec", container_name,
                "tar", "xzf", archive_path,
                "-C", volume_path,
                "--exclude", "*.symlink"
            ], check=True)
            
            # Second pass: extract symlinks and fix their paths
            logger.info("Second pass: extracting and fixing symlinks...")
            subprocess.run([
                "docker", "exec", container_name,
                "sh", "-c", f"""
                cd {volume_path} && \
                tar xzf {archive_path} --include "*.symlink" && \
                find . -type l -exec sh -c '
                    link="$(readlink "$1")"
                    if echo "$link" | grep -q "^\./volumes/"; then
                        new_link="$(echo "$link" | sed "s|^\./volumes/[^/]*/||")"
                        ln -sf "$new_link" "$1"
                    fi
                ' sh {{}} \;
                """
            ], check=True)
            
            logger.info(f"Successfully restored volume {volume_name}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error during volume restoration: {str(e)}")
            raise
            
        finally:
            # Clean up the temporary container
            logger.info("Cleaning up container")
            subprocess.run(["docker", "rm", "-f", container_name], check=False)
            
    except Exception as e:
        logger.error(f"Restore error: {str(e)}")
        raise 