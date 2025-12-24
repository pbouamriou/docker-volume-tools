# Plan de conversion Python → Go pour Docker Volume Tools

## Analyse de la situation actuelle

### Structure Python actuelle
- **CLI**: Click (interface ligne de commande)
- **Docker**: docker-py SDK
- **YAML**: PyYAML pour parser docker-compose.yml
- **Tests**: pytest avec fixtures Docker
- **Build**: PyInstaller pour créer un exécutable standalone

### Problèmes identifiés avec les liens symboliques

**Problème 1 - Backup SSH (ligne 180)**: Utilise `tar -h` pour suivre les symlinks
- L'option `-h` déréférence les symlinks (copie le contenu cible au lieu du lien)
- Cela peut créer des doublons de données et augmenter la taille de l'archive
- Les symlinks ne sont pas préservés dans la structure originale

**Problème 2 - Restore (lignes 215-244)**: Traitement en deux passes
- Première passe: extrait fichiers réguliers (skip symlinks avec `issym()`)
- Deuxième passe: recrée les symlinks avec `os.symlink(member.linkname, target_path)`
- Risque: les chemins relatifs dans `linkname` peuvent être incorrects après extraction
- Pas de normalisation des chemins de symlinks

**Problème 3 - Incohérence backup/restore**:
- Backup: déréférence les symlinks (`tar -h`)
- Restore: tente de recréer les symlinks
- Ces deux approches sont incompatibles!

## Solution proposée pour les symlinks

### Approche recommandée
1. **Préserver les symlinks lors du backup** (ne pas utiliser `-h`)
2. **Stocker les symlinks tels quels dans l'archive**
3. **Lors de la restauration**, recréer les symlinks avec leurs chemins relatifs corrects
4. **Normaliser les chemins** pour garantir la cohérence

### Implémentation en Go
- Utiliser `archive/tar` qui gère nativement les symlinks
- Type `tar.Header.Typeflag == tar.TypeSymlink` pour détecter
- Champ `tar.Header.Linkname` contient la cible du symlink
- Lors de l'extraction, utiliser `os.Symlink(header.Linkname, targetPath)`

## Équivalents Go pour les dépendances Python

### 1. CLI Framework
**Python**: Click
**Go**:
- **Cobra** (recommandé) - https://github.com/spf13/cobra
  - Structure subcommands (list, backup, restore)
  - Flags et arguments
  - Génération aide automatique
- Alternative: **urfave/cli** (plus simple mais moins features)

### 2. Docker SDK
**Python**: docker-py
**Go**:
- **github.com/docker/docker/client** (SDK officiel)
- API identique en fonctionnalité
- Gestion containers, volumes, networks

### 3. YAML Parser
**Python**: PyYAML
**Go**:
- **gopkg.in/yaml.v3** (recommandé)
- Parse/Unmarshal vers structs Go
- Support des tags YAML

### 4. Table Display
**Python**: tabulate
**Go**:
- **github.com/olekukonko/tablewriter**
- Formatage tables en CLI

### 5. Testing
**Python**: pytest
**Go**:
- **testing** (standard library)
- **github.com/stretchr/testify** pour assertions (assert, require)
- **testcontainers-go** pour les tests d'intégration Docker

### 6. Archive/Compression
**Python**: tarfile, gzip
**Go**:
- **archive/tar** (standard library)
- **compress/gzip** (standard library)

## Structure du projet Go proposée

```
docker-volume-tools/
├── cmd/
│   └── dvt/
│       └── main.go              # Point d'entrée CLI
├── internal/
│   ├── compose/
│   │   └── parser.go            # Parse docker-compose.yml
│   ├── backup/
│   │   └── backup.go            # Logique de backup
│   ├── restore/
│   │   └── restore.go           # Logique de restore
│   └── docker/
│       └── client.go            # Wrapper Docker client
├── pkg/
│   └── models/
│       └── volume.go            # Structures de données (VolumeInfo, Metadata)
├── test/
│   ├── integration/
│   │   └── workflow_test.go     # Tests d'intégration
│   └── testdata/
│       └── docker-compose.yml   # Fixtures
├── go.mod
├── go.sum
├── Makefile                      # Build, test, install
└── README.md
```

### Organisation des packages

**cmd/dvt/main.go**: Point d'entrée, initialisation Cobra
**internal/**: Code privé non exportable
- **compose**: Parse et analyse docker-compose.yml
- **backup**: Création des archives
- **restore**: Restauration depuis archives
- **docker**: Wrapper pour faciliter les opérations Docker

**pkg/models**: Structures de données partagées (exportables)

## Plan d'implémentation détaillé

### Phase 1: Setup et structures de base
1. Initialiser module Go (`go mod init`)
2. Créer structure de dossiers
3. Définir structures de données dans `pkg/models/volume.go`:
   - `VolumeInfo` (équivalent Python dataclass)
   - `BackupMetadata`
   - `BackupOptions`, `RestoreOptions`

### Phase 2: Parser Docker Compose
1. Implémenter `internal/compose/parser.go`
2. Fonctions:
   - `ParseComposeFile(path string) ([]VolumeInfo, error)`
   - `GetProjectName(path string) string`
3. Gérer volumes nommés vs bind mounts
4. Gérer préfixage des noms (project_volumename)
5. Tests unitaires

### Phase 3: Client Docker wrapper
1. Créer `internal/docker/client.go`
2. Wrapper pour:
   - Créer/supprimer volumes
   - Lister volumes
   - Créer containers temporaires
   - Exec dans containers
3. Gestion erreurs et cleanup

### Phase 4: Module Backup
1. Implémenter `internal/backup/backup.go`
2. Fonctions principales:
   - `CreateBackup(options BackupOptions) (string, error)`
   - `backupVolume(volumeName string, outputPath string) error`
   - `createMetadata(volumes []VolumeInfo) MetadataJSON`
3. **FIX SYMLINKS**: Ne pas utiliser `-h`, préserver les symlinks
4. Support backup local et SSH
5. Tests unitaires pour backup local

### Phase 5: Module Restore
1. Implémenter `internal/restore/restore.go`
2. Fonctions:
   - `ValidateBackup(path string) (*BackupMetadata, error)`
   - `RestoreBackup(path string, options RestoreOptions) error`
   - `restoreVolume(volumeName string, archivePath string) error`
3. **FIX SYMLINKS**: Traitement correct des symlinks
   - Détecter `tar.TypeSymlink`
   - Recréer avec `os.Symlink()`
   - Normaliser chemins relatifs
4. Tests unitaires

### Phase 6: CLI avec Cobra
1. Créer `cmd/dvt/main.go`
2. Initialiser root command
3. Implémenter subcommands:
   - `list` command
   - `backup` command
   - `restore` command
4. Flags et arguments pour chaque commande
5. Affichage tableaux avec tablewriter

### Phase 7: Tests d'intégration
1. Port des tests pytest vers Go testing
2. Utiliser testcontainers-go pour:
   - Créer containers PostgreSQL et Redis
   - Tester workflow complet backup/restore
   - Vérifier intégrité des données
3. Tests spécifiques pour symlinks:
   - Créer volume avec symlinks
   - Backup
   - Restore
   - Vérifier que symlinks sont préservés

### Phase 8: Build et packaging
1. Créer Makefile avec targets:
   - `make build`: compile binaire
   - `make test`: run all tests
   - `make integration`: run integration tests
   - `make install`: install binaire
2. Cross-compilation pour Linux/macOS/Windows
3. Utiliser `go build -ldflags` pour versioning

### Phase 9: Documentation
1. Mettre à jour README.md
2. Mettre à jour CLAUDE.md pour Go
3. Documenter les fixes de symlinks
4. Exemples d'utilisation

## Détails techniques critiques

### Gestion correcte des symlinks en Go

#### Lors du backup (archive/tar)
```go
// Parcourir le volume et ajouter à l'archive
filepath.Walk(sourcePath, func(path string, info os.FileInfo, err error) error {
    if info.Mode()&os.ModeSymlink != 0 {
        // C'est un symlink
        linkTarget, _ := os.Readlink(path)
        header := &tar.Header{
            Name:     relativePath,
            Typeflag: tar.TypeSymlink,
            Linkname: linkTarget,  // Préserver le chemin cible
            Mode:     int64(info.Mode()),
        }
        tarWriter.WriteHeader(header)
        // Pas de WriteFile pour les symlinks
    } else {
        // Fichier régulier ou répertoire
        // ... traitement normal
    }
})
```

#### Lors du restore
```go
for {
    header, err := tarReader.Next()
    if err == io.EOF {
        break
    }

    targetPath := filepath.Join(destPath, header.Name)

    switch header.Typeflag {
    case tar.TypeSymlink:
        // Recréer le symlink
        os.Symlink(header.Linkname, targetPath)
    case tar.TypeReg:
        // Fichier régulier
        // ... extraction normale
    }
}
```

### Différences importantes Python → Go

1. **Error handling**: Go utilise `(result, error)` au lieu d'exceptions
2. **Defer**: Utiliser `defer` pour cleanup (équivalent `finally`)
3. **Concurrency**: Possibilité d'utiliser goroutines pour backup parallèle
4. **Static typing**: Définir toutes les structures explicitement
5. **No dependencies**: Go produit un binaire statique (pas besoin de PyInstaller)

### Avantages de la migration Go

1. **Binaire unique**: Compilation statique, aucune dépendance runtime
2. **Performance**: Plus rapide que Python
3. **Cross-compilation**: Facile de builder pour toutes plateformes
4. **Typage statique**: Moins d'erreurs à runtime
5. **Concurrency native**: Goroutines pour opérations parallèles
6. **Taille binaire**: Plus petit que bundle PyInstaller

## Validation du plan

### Questions à clarifier

1. **Compatibilité backward**: Les backups créés par la version Python doivent-ils être restaurables par la version Go?
   - Si oui: besoin de tests de compatibilité
   - Attention au format metadata.json

2. **Migration progressive ou remplacement complet**?
   - Garder les deux versions?
   - Renommer le binaire Go?

3. **Support SSH**: La fonctionnalité SSH est-elle critique?
   - Plus complexe en Go (pas de wrapper simple comme Python)
   - Alternative: générer scripts SSH séparés

4. **Versions Go supportées**: Go 1.18+ (pour generics si besoin)?

## Ordre d'exécution recommandé

1. ✅ Setup projet (Phase 1)
2. ✅ Structures de données (Phase 1)
3. ✅ Parser Compose (Phase 2)
4. ✅ Docker client (Phase 3)
5. ✅ Backup local uniquement (Phase 4 - sans SSH d'abord)
6. ✅ Restore avec fix symlinks (Phase 5)
7. ✅ CLI basique (Phase 6)
8. ✅ Tests unitaires (au fur et à mesure)
9. ✅ Tests d'intégration (Phase 7)
10. ⏳ SSH support si nécessaire (Phase 4 complète)
11. ✅ Build et packaging (Phase 8)
12. ✅ Documentation (Phase 9)

## Estimation

- **Phase 1-3**: ~2-3h (setup, structures, parser)
- **Phase 4-5**: ~4-5h (backup/restore avec fix symlinks)
- **Phase 6**: ~2h (CLI)
- **Phase 7**: ~3-4h (tests intégration)
- **Phase 8-9**: ~1-2h (build, doc)

**Total estimé**: ~12-16h de développement

## Risques et mitigations

### Risque 1: Compatibilité Docker API
- **Mitigation**: Utiliser SDK officiel, même API que Python

### Risque 2: Comportement différent tar
- **Mitigation**: Tests extensifs avec fixtures identiques

### Risque 3: Symlinks sur Windows
- **Mitigation**: Tester sur Windows, documenter limitations

### Risque 4: SSH complexe en Go
- **Mitigation**: Commencer sans SSH, ajouter plus tard si nécessaire
