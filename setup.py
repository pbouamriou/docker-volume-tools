"""Setup file for Docker Volume Tools."""

from setuptools import setup, find_packages

setup(
    name="docker-volume-tools",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "click>=8.0.0",
        "docker>=6.0.0",
        "PyYAML>=6.0",
        "tabulate>=0.8.0"
    ],
    entry_points={
        "console_scripts": [
            "dvt=docker_volume_tools.cli:cli"
        ]
    },
    python_requires=">=3.8",
    author="Philippe Bouamriou",
    description="Tools for managing Docker volumes",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    keywords="docker, volumes, backup, restore",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Systems Administration",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
) 