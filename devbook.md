# Docker Volume Tools - Cahier des charges

## 1. Objectif du projet

Créer un outil en ligne de commande pour gérer la sauvegarde et la restauration des volumes Docker associés à un projet Docker Compose.

## 2. Fonctionnalités

### 2.1 Commande `list`

- ✅ Lister tous les volumes d'un projet Docker Compose
- ✅ Afficher les informations détaillées (service, type, point de montage)
- ✅ Distinguer les volumes nommés des bind mounts
- ✅ Identifier les volumes externes

### 2.2 Commande `backup`

- ✅ Sauvegarder tous les volumes nommés d'un projet
- ✅ Permettre la sélection de volumes spécifiques
- ✅ Créer des archives compressées (tar.gz)
- ✅ Sauvegarder les métadonnées (service, configuration)
- ✅ Gérer les volumes partagés entre services
- ✅ Options de compression configurables

### 2.3 Commande `restore` (à implémenter)

- ⏳ Restaurer les volumes depuis une sauvegarde
- ⏳ Valider l'intégrité de la sauvegarde
- ⏳ Recréer les volumes avec leurs configurations
- ⏳ Option pour forcer l'écrasement des volumes existants
- ⏳ Restauration sélective de volumes spécifiques

## 3. Architecture

### 3.1 Structure du projet

```
docker-volume-tools/
├── src/docker_volume_tools/
│   ├── __init__.py
│   ├── cli.py          # Interface en ligne de commande
│   ├── compose.py      # Analyse des fichiers docker-compose
│   └── backup.py       # Gestion des sauvegardes
├── tests/              # Tests unitaires
├── examples/           # Exemples d'utilisation
└── backups/           # Dossier par défaut des sauvegardes
```

### 3.2 Format des sauvegardes

```
project_volumes_20240112_123456.tar.gz
└── project_volumes_20240112_123456/
    ├── volume1.tar.gz
    ├── volume2.tar.gz
    └── metadata.json
```

## 4. État d'avancement

### 4.1 Fonctionnalités implémentées

- ✅ Commande `list` complète
- ✅ Commande `backup` complète
- ✅ Gestion des erreurs
- ✅ Documentation des commandes
- ✅ Tests unitaires de base
- ✅ Tests d'intégration pour les commandes `list` et `backup`

### 4.2 En cours

- ⏳ Commande `restore`
- ⏳ Documentation utilisateur

### 4.3 Corrections récentes

- ✅ Correction de l'extension des archives (.tar.gz au lieu de .targz)
- ✅ Déduplication des volumes dans les métadonnées
- ✅ Mise à jour du .gitignore
- ✅ Ajout des tests d'intégration avec environnement Docker isolé

## 5. Utilisation

### 5.1 Installation

```bash
pip install -e .
```

### 5.2 Commandes disponibles

```bash
# Lister les volumes
dvt list docker-compose.yml

# Sauvegarder tous les volumes
dvt backup docker-compose.yml

# Sauvegarder des volumes spécifiques
dvt backup docker-compose.yml -v volume1 -v volume2

# Sauvegarder sans compression
dvt backup docker-compose.yml --no-compress
```

## 6. Règles de développement

### 6.1 Style de code

- ✅ Respect de PEP 8
- ✅ Documentation en anglais
- ✅ Messages de commit en français
- ✅ Tests unitaires pour les nouvelles fonctionnalités

### 6.2 Gestion des fichiers

- ✅ Noms de fichiers en anglais
- ✅ Documentation utilisateur en français (devbook.md)
- ✅ Fichiers de configuration en anglais
