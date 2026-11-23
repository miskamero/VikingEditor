# VikingEditor showcase

Captured from the actual application with a synthetic character named Astrid.

| Media | Info |
| --- | --- |
| [Animated tour](showcase.gif) | GitHub README, showing five tabs in a 16-second loop |
| [Item editor](item-editor.png) | Item editing interface |
| [Inventory](inventory.png) | Responsive grid, equipment indicators, and stacks |
| [Inventory in Dark Mode](inventory-dark.png) | The same inventory in the dark theme |
| [Skills](skills.png) | Skill editing |
| [Vitals](vitals.png) | Health, stamina, food buffs, and character flags |
| [Progress](progress.png) | Discovery summaries and search |
| [Statistics](statistics.png) | Lifetime activity |

## Regenerating

From the repository root, with the project dependencies installed:

```sh
.\venv\Scripts\python.exe tools\createShowcase.py
```

The script renders the application in Qt’s offscreen mode and reads the existing local item database and icon cache. Run **File → Update Item Database** first if you want to show icons extracted from an installed game. Pass an output directory as the first argument to review a new capture before replacing the gallery. Windows captures use Segoe UI when installed.

The GIF is an automated tab tour, not a recording of live gameplay. Static PNGs are available for readers who prefer no animation. Valheim item artwork shown within the application belongs to its respective rights holders.
