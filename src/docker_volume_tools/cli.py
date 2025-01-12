"""Command line interface for docker-volume-tools."""

import os
import click
from tabulate import tabulate
from docker_volume_tools.compose import parse_compose_file, VolumeInfo
from docker_volume_tools.backup import create_backup, BackupError
from docker_volume_tools.restore import restore_backup, validate_backup

@click.group()
def cli():
    """Docker Volume Tools - Backup and restore Docker Compose volumes efficiently.
    
    This tool provides commands to manage backups of Docker volumes associated with
    Docker Compose projects. It helps you save and restore your data volumes while
    maintaining their associations with specific services.
    """
    pass

@cli.command()
@click.argument('compose_file', type=click.Path(exists=True))
@click.option('--output-dir', '-o', type=click.Path(), default='./backups',
              help='Directory to store backups (default: ./backups)')
@click.option('--compress/--no-compress', default=True,
              help='Enable/disable backup compression (default: enabled)')
@click.option('--volumes', '-v', multiple=True,
              help='Specific volumes to backup (default: all volumes)')
def backup(compose_file, output_dir, compress, volumes):
    """Backup all volumes from a Docker Compose project.
    
    This command creates backups of all volumes defined in your Docker Compose file:
    - Automatically detects all volumes in the compose file
    - Creates consistent backups of each volume
    - Maintains service associations
    - Includes volume metadata and configurations
    - Supports incremental backups (coming soon)
    
    Examples:
        dvt backup docker-compose.yml
        dvt backup docker-compose.yml --output-dir /backups
        dvt backup docker-compose.yml --no-compress
        dvt backup docker-compose.yml -v postgres_data -v redis_data
    
    Args:
        compose_file: Path to your docker-compose.yml file
    """
    try:
        # Convert relative paths to absolute
        compose_file = os.path.abspath(compose_file)
        output_dir = os.path.abspath(output_dir)
        
        click.echo(f"Starting backup of volumes from {compose_file}")
        click.echo(f"Output directory: {output_dir}")
        
        # List volumes that will be backed up
        volumes_list = parse_compose_file(compose_file)
        if volumes:
            volumes_list = [v for v in volumes_list if v.name in volumes]
            
        named_volumes = [v for v in volumes_list if v.type == 'named']
        if not named_volumes:
            click.echo("No named volumes to backup")
            return
            
        click.echo("\nVolumes to backup:")
        headers = ["Volume", "Service", "Type", "Mount Point"]
        table_data = [
            [v.name, v.service, v.type, v.target]
            for v in named_volumes
        ]
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        if not click.confirm("\nProceed with backup?"):
            click.echo("Backup cancelled")
            return
            
        # Create backup
        backup_file = create_backup(
            compose_file=compose_file,
            output_dir=output_dir,
            compress=compress,
            volumes_to_backup=volumes if volumes else None
        )
        
        click.echo(f"\nBackup completed successfully!")
        click.echo(f"Backup archive: {backup_file}")
        
    except BackupError as e:
        click.echo(f"Backup error: {str(e)}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        raise click.Abort()

@cli.command()
@click.argument('backup_path', type=click.Path(exists=True))
@click.option('--volumes', '-v', multiple=True,
              help='Specific volumes to restore (default: all volumes)')
@click.option('--force/--no-force', default=False,
              help='Override existing volumes')
def restore(backup_path, volumes, force):
    """Restore volumes from a backup.
    
    This command restores previously backed up volumes:
    - Validates backup integrity before restoration
    - Recreates volumes with original configurations
    - Restores data and metadata
    - Maintains service associations
    - Supports selective restoration
    
    Examples:
        dvt restore backups/volumes_20240112_123456.tar.gz
        dvt restore backups/volumes_20240112_123456.tar.gz -v postgres_data
        dvt restore backups/volumes_20240112_123456.tar.gz --force
    
    Args:
        backup_path: Path to the backup archive
    """
    try:
        click.echo(f"Validating backup: {backup_path}")
        metadata = validate_backup(backup_path)
        
        # Show volumes that will be restored
        volumes_to_restore = metadata["volumes"]
        if volumes:
            volumes_to_restore = [
                v for v in volumes_to_restore
                if v["name"] in volumes
            ]
            if len(volumes_to_restore) != len(volumes):
                missing = set(volumes) - {v["name"] for v in volumes_to_restore}
                raise ValueError(f"Volumes not found in backup: {', '.join(missing)}")
        
        click.echo("\nVolumes to restore:")
        headers = ["Volume", "Size", "Created"]
        table_data = [
            [v["name"], v.get("size", "N/A"), v.get("created", "N/A")]
            for v in volumes_to_restore
        ]
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        if not click.confirm("\nProceed with restore?"):
            click.echo("Restore cancelled")
            return
            
        click.echo("\nRestoring volumes...")
        restore_backup(
            backup_path=backup_path,
            volumes=volumes if volumes else None,
            force=force
        )
        
        click.echo("\nRestore completed successfully!")
        
    except ValueError as e:
        click.echo(f"Restore error: {str(e)}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Unexpected error: {str(e)}", err=True)
        raise click.Abort()

@cli.command()
@click.argument('compose_file', type=click.Path(exists=True))
def list(compose_file):
    """List all volumes defined in a Docker Compose project.
    
    This command analyzes your Docker Compose file and shows:
    - Volume names and their associated services
    - Volume types (named volumes vs bind mounts)
    - Current size and usage
    - Last backup status and date (if any)
    
    Examples:
        dvt list docker-compose.yml
    
    Args:
        compose_file: Path to your docker-compose.yml file
    """
    try:
        volumes = parse_compose_file(compose_file)
        
        if not volumes:
            click.echo("No volumes found in the compose file.")
            return
            
        # Prepare table data
        headers = ["Volume", "Service", "Type", "Mount Point", "External"]
        table_data = [
            [
                v.name,
                v.service,
                v.type,
                v.target,
                "Yes" if v.is_external else "No"
            ]
            for v in volumes
        ]
        
        # Display table
        click.echo("\nVolumes found in compose file:")
        click.echo(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Display summary
        named_volumes = sum(1 for v in volumes if v.type == 'named')
        bind_mounts = sum(1 for v in volumes if v.type == 'bind')
        click.echo(f"\nSummary:")
        click.echo(f"- Named volumes: {named_volumes}")
        click.echo(f"- Bind mounts: {bind_mounts}")
        click.echo(f"- Total: {len(volumes)}")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        raise click.Abort()

if __name__ == '__main__':
    cli() 