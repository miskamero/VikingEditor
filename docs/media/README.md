# VikingEditor showcase

Captured from the actual application with a synthetic character named Astrid.

| Media | Info |
| --- | --- |
| [Animated tour](showcase.gif) | GitHub README, showing five tabs in a 16-second loop |
| [Item editor](item-editor.png) | Item editing interface |
| [Inventory](inventory.png) | Item icons, equipment, and stacks |
| [Skills](skills.png) | Skill editing |
| [Stats](stats.png) | Vitals and food buffs |
| [Progress](progress.png) | Discovery summaries and search |
| [Statistics](statistics.png) | Lifetime activity |

## Regenerating

From the repository root, with the project dependencies installed:

```sh
.\venv\Scripts\python.exe tools\createShowcase.py
```

The script uses Qt offscreen rendering and reads the existing local item database and icon cache. Run **File... Update Item Database** first for real Valheim icons. It writes only the showcase files in this directory; configuration and character saves are not modified. Windows captures use Segoe UI when installed; other systems use Qt's available fonts, so rendering may differ.

The GIF is an automated tab tour, not a recording of live gameplay. Static PNGs are available for readers who prefer no animation. Valheim item artwork shown within the application belongs to its respective rights holders.
