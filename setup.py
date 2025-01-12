"""Setup file for Docker Volume Tools."""

from setuptools import setup, find_packages

setup(
    name="docker-volume-tools",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "docker>=7.0.0",
        "click>=8.1.7",
    ],
    entry_points={
        "console_scripts": [
            "dvt=docker_volume_tools.cli:cli",
        ],
    },
    author="Philippe Bouamriou",
    description="A set of tools to manage Docker volumes efficiently",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    keywords="docker, volumes, management, tools",
    python_requires=">=3.8",
) 