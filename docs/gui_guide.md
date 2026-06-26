# Guide des interfaces graphiques

Ce document décrit le lancement des interfaces graphiques de CGN-model, la gestion des bases SQLite locales et les variables d'environnement disponibles.

Les interfaces graphiques sont des applications Dash lancées localement depuis l'environnement Python du projet. Elles ouvrent un serveur local, généralement accessible à l'adresse :

```text
http://127.0.0.1:8050/
```

## Interfaces disponibles

Deux commandes sont installées avec le package :

```cmd
cgnmodel-gui
cgnmodel-mvp
```

`cgnmodel-gui` lance l'interface principale actuelle. C'est l'interface à utiliser en priorité.

`cgnmodel-mvp` lance une interface plus ancienne, conservée comme prototype et comme référence historique. Elle n'est pas l'interface recommandée pour un nouvel usage.

## Lancement standard

Avant de lancer une interface, activer l'environnement Conda du projet :

```cmd
conda activate cgnmodel
```

Puis lancer l'interface principale :

```cmd
cgnmodel-gui
```

Au démarrage, le terminal affiche l'adresse locale de l'interface et le chemin de la base SQLite utilisée :

```text
Interface CGN disponible sur http://127.0.0.1:8050/
Base SQLite utilisee: C:\Users\<Utilisateur>\AppData\Local\CGN-model\ui_v2.db
```

L'interface MVP se lance de la même manière :

```cmd
cgnmodel-mvp
```

Elle utilise sa propre base SQLite :

```text
Base SQLite utilisee: C:\Users\<Utilisateur>\AppData\Local\CGN-model\mvp.db
```

## Bases SQLite locales

Les interfaces enregistrent les composants, configurations et schémas créés par l'utilisateur dans des bases SQLite locales.

Les fichiers utilisés à l'exécution ne sont pas stockés dans le code du projet. Ils sont créés automatiquement au premier lancement depuis des fichiers templates inclus dans le package :

```text
ui_v2_template.db -> ui_v2.db
mvp_template.db   -> mvp.db
```

Par défaut, sous Windows, les bases utilisateur sont placées dans :

```text
%LOCALAPPDATA%\CGN-model\
```

Exemple :

```text
C:\Users\<Utilisateur>\AppData\Local\CGN-model\ui_v2.db
C:\Users\<Utilisateur>\AppData\Local\CGN-model\mvp.db
```

Si le dossier `%LOCALAPPDATA%` n'est pas disponible, CGN-model utilise le dossier suivant :

```text
~/.cgn-model/
```

Dans ce chemin, `~/` désigne le dossier utilisateur courant. Sous Windows, cela correspond généralement à :

```text
C:\Users\<Utilisateur>\
```

Si aucun dossier local n'est accessible en écriture, le lancement échoue avec une erreur explicite demandant de définir la variable `CGN_MODEL_DATA_DIR`.

## Utiliser un dossier de données personnalisé

La variable d'environnement `CGN_MODEL_DATA_DIR` permet de choisir le dossier dans lequel les bases SQLite seront stockées.

Cette option est utile si :

- l'utilisateur veut placer les bases dans un dossier plus visible, par exemple `Documents` ;
- le dossier `AppData` est restreint par l'environnement informatique ;
- plusieurs jeux de bases doivent être conservés séparément.

### Dans Anaconda Prompt ou CMD

Pour définir temporairement le dossier dans la fenêtre terminal courante :

```cmd
set CGN_MODEL_DATA_DIR=C:\Users\<Utilisateur>\Documents\CGN-model-data
cgnmodel-gui
```

Pour vérifier la valeur utilisée :

```cmd
echo %CGN_MODEL_DATA_DIR%
```

Cette définition temporaire disparaît lorsque la fenêtre terminal est fermée.

Pour définir la variable de manière permanente sous Windows :

```cmd
setx CGN_MODEL_DATA_DIR "C:\Users\<Utilisateur>\Documents\CGN-model-data"
```

Après `setx`, ouvrir un nouveau terminal pour que la variable soit prise en compte.

### Dans PowerShell

Pour définir temporairement le dossier dans la fenêtre PowerShell courante :

```powershell
$env:CGN_MODEL_DATA_DIR = "C:\Users\<Utilisateur>\Documents\CGN-model-data"
cgnmodel-gui
```

Pour vérifier la valeur utilisée :

```powershell
echo $env:CGN_MODEL_DATA_DIR
```

## Archivage ou changement de base

Les bases SQLite sont de simples fichiers `.db`. Pour archiver un état de l'interface, il suffit de copier ou renommer le fichier correspondant.

Exemple :

```text
ui_v2.db -> ui_v2_archive_2026-06.db
```

Au lancement suivant, si `ui_v2.db` n'existe plus dans le dossier de données courant, CGN-model recrée automatiquement une base vierge depuis le template.

Pour revenir à une ancienne base, il suffit de lui redonner le nom attendu :

```text
ui_v2_archive_2026-06.db -> ui_v2.db
```

Le même principe s'applique à l'interface MVP avec `mvp.db`.

## Variables d'environnement de lancement

Les variables suivantes permettent d'ajuster le comportement des interfaces au lancement. Elles sont optionnelles.

### Variables communes

| Variable | Rôle |
| --- | --- |
| `CGN_MODEL_DATA_DIR` | Dossier utilisé pour les bases SQLite locales. |

### Interface principale `cgnmodel-gui`

| Variable | Valeur par défaut | Rôle |
| --- | --- | --- |
| `CGN_GUI_DEBUG` | `0` | Active le mode debug Dash/Flask. |
| `CGN_GUI_OPEN_BROWSER` | `0` | Ouvre automatiquement le navigateur au lancement. |
| `CGN_GUI_QUIET` | `1` en mode stable | Réduit les logs serveur dans le terminal. |

Exemples CMD / Anaconda Prompt :

```cmd
set CGN_GUI_OPEN_BROWSER=1
cgnmodel-gui
```

```cmd
set CGN_GUI_DEBUG=1
set CGN_GUI_QUIET=0
cgnmodel-gui
```

Exemples PowerShell :

```powershell
$env:CGN_GUI_OPEN_BROWSER = "1"
cgnmodel-gui
```

```powershell
$env:CGN_GUI_DEBUG = "1"
$env:CGN_GUI_QUIET = "0"
cgnmodel-gui
```

### Interface MVP `cgnmodel-mvp`

| Variable | Valeur par défaut | Rôle |
| --- | --- | --- |
| `CGN_MVP_DEBUG` | `0` | Active le mode debug Dash/Flask. |
| `CGN_MVP_OPEN_BROWSER` | `0` | Ouvre automatiquement le navigateur au lancement. |
| `CGN_MVP_QUIET` | `1` en mode stable | Réduit les logs serveur dans le terminal. |

Exemples CMD / Anaconda Prompt :

```cmd
set CGN_MVP_OPEN_BROWSER=1
cgnmodel-mvp
```

```cmd
set CGN_MVP_DEBUG=1
set CGN_MVP_QUIET=0
cgnmodel-mvp
```

## Remarques sur le mode debug

Le mode debug est utile pendant le développement, mais il n'est pas recommandé pour une utilisation standard.

En mode debug, Dash/Flask peut utiliser un mécanisme de rechargement automatique. Ce mécanisme lance un processus supplémentaire, ce qui peut produire certains affichages en double dans le terminal si le code n'est pas protégé contre ce comportement.

Les interfaces CGN-model limitent cet effet pour les messages principaux, mais le mode stable reste le mode conseillé pour l'utilisateur final.

## Lancement par fichier `.bat`

Sous Windows, le fichier `Lancer_CGN_GUI.bat` peut être utilisé pour lancer l'interface principale.

Ce fichier exécute les commandes du flux de lancement standard : activation de l'environnement Conda, lancement de `cgnmodel-gui`, puis ouverture de l'interface locale dans le navigateur.

Avant utilisation, vérifier dans ce fichier le chemin vers Conda, par exemple :

```bat
%UserProfile%\miniconda\condabin\conda.bat
```

Selon l'installation locale, ce chemin peut devoir être adapté, par exemple :

```bat
C:\Users\<Utilisateur>\miniconda3\condabin\conda.bat
```

Le fichier `.bat` peut être modifié avec un éditeur de texte simple, par exemple le Bloc-notes Windows.

Dans certains environnements d'entreprise, l'exécution des fichiers `.bat` peut être bloquée. Dans ce cas, utiliser directement les commandes dans Anaconda Prompt.