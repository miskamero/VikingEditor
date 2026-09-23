# VikingEditor 2.1.4

An interactive desktop application written in Python and PySide6 for safely decompiling, editing, creating, and recompiling Valheim character save files (`.fch`).

VikingEditor provides a modern graphical interface for editing character data without requiring a hex editor or manually handling Valheim's save-file integrity hash.

**VikingEditor 2.0** introduces a significantly expanded character editor, automatic backups, character creation, improved save management, and dedicated views for character progress, statistics, and world data.

---

## Table of Contents

* [Features](#features)
* [Installation & Setup](#installation--setup)
* [How to Use](#how-to-use)
* [Creating a New Character](#creating-a-new-character)
* [Backups](#backups)
* [How to Find Your `.fch` Files](#how-to-find-your-fch-files)
* [Project Structure](#project-structure)
* [Contributing](#contributing)
* [Disclaimer](#disclaimer)
* [License](#license)

---

## Features

### Character Editing

* **Inventory**

  * Edit items in your character's inventory.
  * Modify stack sizes, durability, quality, variants, equipped state, and other supported item data.
  * Search and select items using the integrated item database.
  * Supports custom item data and Valheim item metadata.

* **Skills**

  * View all supported Valheim skills.
  * Edit skill levels and experience.
  * Unlock skills that are not yet present on the character.
  * Reset or maximize unlocked skills.
  * Supports both combat and non-combat skills.

* **Stats**

  * Edit character health, stamina, Eitr, and other supported player attributes.
  * Cheats Flag toggling

* **Appearance**

  * Edit character appearance data.
  * Change hair and beard styles.
  * Customize skin and hair colors.
  * Edit supported character model settings.

* **Progress**

  * View character progression data.

### Character Management

* **Progress**

    * View character progression data.
    * View known recipes, stations, materials, and biomes.
    * View Trophies
    * View Unique Discoveries

* **Statistics**

    * Enemies defeated
    * Items picked up
    * Items crafted
    * Pickables collected
    * Pieces placed

  **Search statistics quickly using the built-in filter.**

* **Character**

  * Change the character's name.
  * View Player ID.
  * View character start seed.
  * View character creation date.
  * View whether cheats have been used.
  * View save version and player-data version.

* **Worlds**

  * View worlds known by the character.
  * View time spent in known worlds.
  * View stored spawn, logout, death, and home locations.
  * Copy world and location information directly from the editor.

### New Character Creation

Create a completely fresh Valheim character directly from VikingEditor.

New characters are generated with:

* A unique Player ID
* A new character start seed
* Current save format
* Default health and stamina
* Default appearance
* Empty inventory
* Empty progression data
* Empty world data
* Empty statistics
* No cheats enabled

The generated character can then be edited normally and saved as a standard Valheim `.fch` file.

### Save Management

* **Automatic SHA-512 integrity hashing**

  * Edited saves are rehashed during compilation so Valheim can accept the resulting file.

* **Automatic backups**

  * Original character saves can automatically be backed up before saving.
  * Backups are organized by character.
  * Old backups can be automatically cleaned up according to the configured limit.

* **Backup Manager**

  * Browse character backups.
  * Inspect backup information.
  * Open backups.
  * Restore backups to the currently loaded character.
  * Restore backups directly to Valheim's character save directory.
  * Delete individual backups or all backups for a character.
  * Open the backup directory.

* **Backup-aware save handling**

  * Restored backups are tracked so the editor can suggest an appropriate restored filename.

### Item Database

VikingEditor scans the installed Valheim game files to build/update its item database.

This allows the editor to work with Valheim's actual item prefabs rather than relying solely on a manually maintained list.

---

## Installation & Setup

VikingEditor can be used in two ways:

1. **Download and run the pre-built distribution:** recommended for normal users.
2. **Clone and run the source code:** recommended for development and contributors.

### Prerequisites

Both options require:

* **Windows**
* A local installation of **Valheim**

The source-code option additionally requires:

* **Python 3.9 or newer**

---

### Option 1: Pre-built Distribution

The easiest way to use VikingEditor is to download the latest **`dist` release** from [https://github.com/miskamero/VikingEditor/releases/latest](https://github.com/miskamero/VikingEditor/releases/latest).

Then extract the contents of the downloaded `.zip` file to a folder of your choice and run `VikingEditor.exe`.

No Python installation or dependency installation is required when using the pre-built distribution.

On first launch, VikingEditor will attempt to locate your Valheim installation automatically. If it cannot find it, you can select the Valheim installation directory manually.

> **Tip:** Keep the entire extracted `dist` folder together. Do not move or delete individual files from the distribution.

---

### Option 2: Run from Source

This option is intended for developers, contributors, or users who want to run the latest source code directly.

#### 1. Clone the Repository

```bash
git clone https://github.com/miskamero/VikingEditor.git

cd VikingEditor
```

#### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

```powershell
.\venv\Scripts\Activate.ps1
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Run VikingEditor

```bash
python main.py
```

On first launch, VikingEditor will attempt to locate your Valheim installation automatically. If it cannot find it, the application will allow you to select the Valheim installation directory manually.


On first launch, VikingEditor will attempt to locate your Valheim installation automatically.

If it cannot find it, the application will allow you to select the Valheim installation directory manually.

---

## How to Use

### Opening an Existing Character

1. Launch VikingEditor.
2. Select **File → Open Save File** or click **Open Save**.
3. Select your Valheim `.fch` character file.
4. The character data will be decompiled and loaded into the editor.
5. Navigate through the tabs and make your desired changes.
6. Click **Save Savefile**.
7. Choose where to save the resulting `.fch` file.
8. Place the saved character file in your Valheim character directory if necessary.
9. Launch Valheim and load the character.

VikingEditor does **not** modify the original save file when you save your changes to a different location.

---

## Creating a New Character

VikingEditor can create a brand-new Valheim character without first having an existing `.fch` file.

1. Select **File → New Character...**
2. Enter the desired character name.
3. The editor generates a fresh character.
4. Edit the character using the normal editor tabs.
5. Select **Save Savefile**.
6. Choose where to save the new `.fch` file.
7. Place the file in your Valheim character directory.
8. Launch Valheim and use the new character.

The generated character format has been tested by loading the resulting `.fch` file in Valheim.

---

## Backups

VikingEditor includes automatic backup functionality to help protect your characters from accidental data loss.

By default, backups are stored in the same directory as VikingEditor.

Before saving an existing character, VikingEditor can automatically create a timestamped backup of the original `.fch` file.

Backups can be managed through:

**File → Manage Backups...**

From the Backup Manager you can:

* Browse backups by character.
* Open a backup.
* Restore a backup to the current character.
* Restore a backup directly to Valheim.
* Delete individual backups.
* Delete all backups for a character.
* Open the backup folder.

### Important

Although VikingEditor includes automatic backups, **you should still maintain your own independent backups of important characters**.

---

## How to Find Your `.fch` Files

Valheim character saves are stored separately from world saves.

If you are using local character saves, they can generally be found under:

```text
%USERPROFILE%\AppData\LocalLow\IronGate\Valheim\characters\
```

If your character is stored in Steam Cloud, they usually are found under:

```text
C:\Program Files (x86)\Steam\userdata\<your-user-id>\892970\remote\characters
```

> **⚠️ CRITICAL SAFETY WARNING**
>
> Always keep an independent backup of important `.fch` files.
>
> Even though VikingEditor provides automatic backups, save files are valuable and should not be treated as disposable.

---

## Project Structure

```text
VikingEditor/
│
├── assets/
│   ├── armor.png
│   ├── arrow.png
│   ├── axe.png
│   ├── bow.png
│   ├── food.png
│   ├── material.png
│   ├── metal.png
│   ├── pickaxe.png
│   ├── plant.png
│   ├── potion.png
│   ├── shield.png
│   ├── sword.png
│   └── tool.png
│
├── data/
│   ├── beards.py
│   ├── hairs.py
│   ├── info.py
│   ├── powers.py
│   └── skills.py
│
├── subscripts/
│   ├── fchUtil.py
│   ├── itemDatabase.py
│   ├── itemValidation.py
│   ├── newCharacter.py
│   └── playerDataUtil.py
│
├── ui/
│   ├── appearanceTab.py
│   ├── backupManagerDialog.py
│   ├── characterTab.py
│   ├── inventorySlot.py
│   ├── inventoryTab.py
│   ├── itemEditDialog.py
│   ├── itemSearchWidget.py
│   ├── mainWindow.py
│   ├── progressTab.py
│   ├── settingsDialog.py
│   ├── skillsTab.py
│   ├── statisticsTab.py
│   ├── statsTab.py
│   ├── valheim_detection.py
│   └── worldsTab.py
│
├── main.py
├── LICENSE
├── NOTICE
├── README.md
└── requirements.txt
```

### Key Components

* `main.py` — Application entry point.
* `ui/mainWindow.py` — Main application window and save/load controller.
* `ui/inventoryTab.py` — Inventory editor.
* `ui/skillsTab.py` — Skills editor.
* `ui/statsTab.py` — Character stats editor.
* `ui/appearanceTab.py` — Character appearance editor.
* `ui/progressTab.py` — Character progression editor.
* `ui/statisticsTab.py` — Character statistics viewer.
* `ui/characterTab.py` — Character metadata and name editor.
* `ui/worldsTab.py` — Character world and location information.
* `ui/backupManagerDialog.py` — Backup management and restoration.
* `subscripts/fchUtil.py` — Outer `.fch` container parsing, compilation, and SHA-512 integrity hashing.
* `subscripts/playerDataUtil.py` — Nested Valheim player-data parsing and serialization.
* `subscripts/newCharacter.py` — Fresh character generation.
* `subscripts/itemDatabase.py` — Valheim item database management.
* `subscripts/itemValidation.py` — Item validation.
* `data/` — Static Valheim data such as skills, hair, beard, and powers.
* `assets/` — UI and item-category graphics.


---

## What VikingEditor Does Not Edit

VikingEditor is specifically focused on **character `.fch` files**.

It does not modify world `.db` files or world-generation settings.

World-specific settings such as:

* Resource rates
* World level
* Event rates
* World modifiers
* Portal settings
* Raid settings
* World generation settings

are intentionally outside the scope of this application.

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome!

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

- [Report a bug](https://github.com/miskamero/VikingEditor/issues/new?template=bug_report.yml)
- [Request a feature](https://github.com/miskamero/VikingEditor/issues/new?template=feature_request.yml)

---

## Disclaimer

VikingEditor is an unofficial, community-made tool.

It is **not affiliated with, authorized by, or endorsed by Iron Gate Studio or Coffee Stain Publishing**.

Valheim save-file formats may change between game updates. Although VikingEditor attempts to preserve save integrity and includes backup functionality, **no save-editing software can guarantee that data will never be lost or corrupted**.

Always keep independent backups of important characters.

Use VikingEditor at your own risk.

---

## License

See [`LICENSE`](LICENSE) for the full license text.
