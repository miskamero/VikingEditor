from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_editor import QtTestCase
from tests.support import item
from ui.itemSearchWidget import ItemSearchWidget, rank_items
from ui.itemEditDialog import ItemEditDialog


class ItemPickerTests(QtTestCase):
    def test_search_matches_words_in_any_order(self):
        for query in ("iron sword", "sword iron", "SWORDIRON"):
            self.assertEqual(rank_items(["Wood", "SwordIron", "SwordIronFire"], query)[0], "SwordIron")

    def test_search_does_not_replace_selection(self):
        picker = self.widget(ItemSearchWidget, "Wood")
        picker.search.setText("sword")
        self.assertEqual(picker.get_prefab(), "Wood")
        picker.select_first_result()
        self.assertEqual(picker.get_prefab(), "SwordIron")

    def test_automatic_current_row_change_does_not_select_item(self):
        picker = self.widget(ItemSearchWidget, "AmberPearl")
        picker.results.setCurrentRow(0)
        self.assertEqual(picker.get_prefab(), "AmberPearl")

    def test_mouse_and_keyboard_still_select_items(self):
        picker = self.widget(ItemSearchWidget, "AmberPearl")
        picker.resize(500, 500)
        picker.show()
        self.app.processEvents()
        first = picker.results.item(0)
        QTest.mouseClick(picker.results.viewport(), Qt.LeftButton,
                         pos=picker.results.visualItemRect(first).center())
        self.assertEqual(picker.get_prefab(), first.data(Qt.UserRole))
        QTest.keyClick(picker.results, Qt.Key_Down)
        self.assertEqual(picker.get_prefab(), picker.results.item(1).data(Qt.UserRole))

    def test_no_matches_preserves_custom_prefab(self):
        picker = self.widget(ItemSearchWidget, "Mod_CustomItem")
        picker.search.setText("no match")
        self.assertEqual(picker.results.count(), 0)
        self.assertEqual(picker.get_prefab(), "Mod_CustomItem")

    def test_enter_selects_without_accepting_dialog(self):
        dialog = self.widget(ItemEditDialog, item())
        dialog.prefab_input.search.setText("sword")
        with patch.object(dialog, "accept") as accept:
            QTest.keyClick(dialog.prefab_input.search, Qt.Key_Return)
            self.assertEqual(dialog.prefab_input.get_prefab(), "SwordIron")
            accept.assert_not_called()

    def test_preview_updates_and_empty_prefab_disables_apply(self):
        dialog = self.widget(ItemEditDialog, item())
        dialog.prefab_input.set_prefab("SwordIron")
        dialog.variant_input.setValue(2)
        self.assertEqual(dialog.preview_name.text(), "Iron Sword")
        self.assertIn("variant 2", dialog.preview_summary.text())
        dialog.prefab_input.set_prefab("")
        self.assertFalse(dialog.apply_button.isEnabled())
