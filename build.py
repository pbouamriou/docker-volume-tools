#!/usr/bin/env python3
"""Script to build the executable."""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def clean_build():
    """Clean build directories."""
    print("Cleaning build directories...")
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
    
    # Clean spec files
    for spec_file in Path('.').glob('*.spec'):
        spec_file.unlink()

def build_executable():
    """Build the executable using PyInstaller."""
    print("Building executable...")
    
    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--name=dvt',
        '--onefile',  # Create a single executable
        '--clean',    # Clean PyInstaller cache
        '--add-data=README.md:.',  # Include README
        'src/docker_volume_tools/cli.py'  # Entry point
    ]
    
    # Add platform-specific options
    if sys.platform == 'win32':
        cmd.extend([
            '--noconsole',  # No console window on Windows
            '--icon=resources/icon.ico'  # Add icon if you have one
        ])
    
    # Run PyInstaller
    subprocess.run(cmd, check=True)
    
    print("\nBuild complete!")
    print("Executable location:")
    if sys.platform == 'win32':
        print("  dist/dvt.exe")
    else:
        print("  dist/dvt")

def main():
    """Main build script."""
    try:
        clean_build()
        build_executable()
    except subprocess.CalledProcessError as e:
        print(f"Error during build: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 