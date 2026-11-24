# EquipmentAndQuickSlots support

VikingEditor recognizes saved equipment from the eight-column EquipmentAndQuickSlots 3.2 layout when the saved visible-row count agrees with the mod’s backup header and the equipment’s position, slot marker, and owner agree. A slot marker alone is insufficient to establish where an item is stored. A recognized slot describes the save and does not indicate whether a mod is currently installed or enabled.

The Inventory tab shows recognized equipment separately. For editable entries, you can change quality, durability, style variant, the item cheat flag, and crafter attribution. Item type, quantity, position, and equipped state are retained. Entries with unresolved item IDs or unsupported values stay read-only.

Quick slots and the mod’s internal backup payload are outside the editable equipment view. The editor does not decode or restore the mod’s internal backup. When the layout cannot be established, affected mod storage remains outside that view. VikingEditor disables pocket changes and **Clear All Cheated Flags** when it detects relevant slot-mod markers.

**Review Stored Positions** lists records outside the editable grid, records sharing a coordinate, and records with recognized slot-mod metadata. Conflicting and mod-marked ordinary cells are read-only. When the slot-mod layout is unverified, the editor also disables placement, removal, prefab replacement, and equipment toggles in the ordinary grid. It can still edit in-place properties of an unmarked, uniquely occupied cell.

EquipmentAndQuickSlots options, other slot mods, and different versions can produce different layouts. Use a disposable copy and check it with the same mods installed in Valheim before editing an important save.
