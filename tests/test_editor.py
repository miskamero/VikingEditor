from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.support import ITEMS, item, create_empty_player_data, create_new_character
from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtTest import QTest
from ui.inventoryTab import InventoryTab
from ui.itemEditDialog import ItemEditDialog
from ui.statsTab import StatsTab
from ui.appearanceTab import AppearanceTab
from ui.progressTab import ProgressTab
from ui.statisticsTab import StatisticsTab
from ui.characterTab import CharacterTab
from ui.worldsTab import WorldsTab
from ui.skillsTab import SkillsTab


class QtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.data = create_empty_player_data()
        self.root = create_new_character("Test Viking")
        self.widgets = []
        self.addCleanup(self.cleanup_widgets)
        for name in ("warning", "information", "question"):
            mock = patch.object(QMessageBox, name, return_value=QMessageBox.No)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)
        database = patch("ui.itemSearchWidget.load_item_database", return_value=ITEMS)
        database.start()
        self.addCleanup(database.stop)
        icons = patch("ui.inventorySlot.get_item_icon_path", return_value=None)
        icons.start()
        self.addCleanup(icons.stop)
        picker_icons = patch("ui.itemSearchWidget.get_item_icon_path", return_value=None)
        picker_icons.start()
        self.addCleanup(picker_icons.stop)

    def widget(self, factory, *args):
        widget = factory(*args)
        self.widgets.append(widget)
        return widget

    def cleanup_widgets(self):
        for widget in reversed(self.widgets):
            widget.close()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()


class InventoryTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.data["inventory"] = [item(cheated=True), item(grid_x=1), item(grid_y=5, cheated=True)]
        self.tab = self.widget(InventoryTab)
        self.tab.load_data(self.data)

    def test_clear_cheated_flags_including_hidden_rows(self):
        self.question.return_value = QMessageBox.Yes
        self.tab.clear_cheated_button.click()
        self.assertTrue(all(not value["cheated"] for value in self.data["inventory"]))
        self.assertTrue(self.tab.slots[(0, 0)].cheated_label.isHidden())
        self.assertIn("2 item(s)", self.question.call_args.args[2])

    def test_cancel_clear_preserves_inventory(self):
        before = deepcopy(self.data)
        self.tab.clear_all_cheated_flags()
        self.assertEqual(self.data, before)

    def test_save_switch_reuses_slots_without_duplicate_click_handlers(self):
        original = self.tab.slots[(0, 0)]
        for _ in range(3):
            self.tab.load_data(create_empty_player_data())
        self.assertIs(self.tab.slots[(0, 0)], original)
        with patch.object(self.tab, "add_item_to_slot") as add:
            original.click()
        add.assert_called_once_with(original)

    def test_switch_back_then_apply_three_amber_pearls(self):
        import gc
        for _ in range(5):
            save1 = create_empty_player_data()
            save2 = create_empty_player_data()
            save2["uniques"] = ["invrows 6"]
            for data in (save1, save2, save1):
                self.tab.load_data(data)
                self.app.processEvents()
            errors = []

            def apply_item():
                dialog = self.app.activeModalWidget()
                try:
                    dialog.prefab_input.set_prefab("AmberPearl")
                    dialog.stack_input.setValue(3)
                    gc.collect()
                    dialog.apply_button.click()
                except Exception as exc:
                    errors.append(exc)
                    if dialog:
                        dialog.reject()

            QTimer.singleShot(0, apply_item)
            self.tab.slots[(0, 0)].click()
            self.assertEqual(errors, [])
            self.assertEqual(len(save1["inventory"]), 1)
            self.assertEqual(save1["inventory"][0]["prefab"], "AmberPearl")
            self.assertEqual(save1["inventory"][0]["stack"], 3)
            self.assertEqual(save2["inventory"], [])
            self.app.sendPostedEvents(None, QEvent.DeferredDelete)
            self.assertEqual(self.tab.findChildren(ItemEditDialog), [])

    def test_dialog_cannot_apply_to_a_different_save(self):
        replacement = create_empty_player_data()
        slot = self.tab.slots[(2, 0)]
        with patch("ui.inventoryTab.ItemEditDialog") as dialog_type:
            dialog = dialog_type.return_value
            def switch_save():
                self.tab.load_data(replacement)
                return QDialog.Accepted
            dialog.exec.side_effect = switch_save
            self.tab.add_item_to_slot(slot)
            dialog.get_updated_data.assert_not_called()
            dialog.deleteLater.assert_called_once()
        self.assertEqual(replacement["inventory"], [])

    def test_removed_slots_are_deleted_on_qt_event_loop(self):
        from shiboken6 import isValid
        self.tab.deeper_pockets_checkbox.setChecked(True)
        removed = self.tab.slots[(0, 5)]
        self.tab.wider_pockets_checkbox.setChecked(False)
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(isValid(removed))

    def test_no_flags_shows_information(self):
        for value in self.data["inventory"]:
            value["cheated"] = False
        self.tab.clear_all_cheated_flags()
        self.information.assert_called_once()
        self.question.assert_not_called()

    def test_marker_updates_and_clears(self):
        slot = self.tab.slots[(0, 0)]
        self.assertFalse(slot.cheated_label.isHidden())
        self.assertIn("Spawned in with cheats: Yes", slot.toolTip())
        slot.clear_item()
        self.assertTrue(slot.cheated_label.isHidden())
        self.assertEqual(slot.toolTip(), "Empty Slot")

    def test_dialog_cancel_does_not_mutate_item(self):
        value = self.data["inventory"][0]
        before = deepcopy(value)
        dialog = self.widget(ItemEditDialog, value)
        dialog.cheated_input.setChecked(False)
        dialog.stack_input.setValue(12)
        dialog.reject()
        self.assertEqual(value, before)

    def test_dialog_returns_cheated_toggle(self):
        dialog = self.widget(ItemEditDialog, self.data["inventory"][0])
        dialog.cheated_input.setChecked(False)
        dialog.validate_and_accept()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertIs(dialog.get_updated_data()["cheated"], False)

    def test_expansion_preserves_unrelated_discoveries(self):
        self.data["uniques"] = ["defeated_eikthyr", "invrows 5", "invslot1"]
        self.tab.deeper_pockets_checkbox.setChecked(True)
        self.tab.save_changes()
        self.assertEqual(len(self.tab.slots), 48)
        self.assertIn("defeated_eikthyr", self.data["uniques"])
        self.assertIn("invrows 6", self.data["uniques"])
        self.tab.wider_pockets_checkbox.setChecked(False)
        self.tab.save_changes()
        self.assertEqual(self.data["uniques"], ["defeated_eikthyr"])
        self.assertEqual(len(self.data["inventory"]), 3)


class StatsTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.tab = self.widget(StatsTab)
        self.tab.load_data(self.data, self.root)

    def test_food_buttons_limit_and_remove(self):
        for _ in range(4):
            self.tab.btn_add_food.click()
        self.assertEqual(self.tab.food_table.rowCount(), 3)
        self.assertEqual(self.tab.food_table.item(0, 0).text(), "Bread")
        self.assertFalse(self.tab.btn_add_food.isEnabled())
        self.tab.food_table.selectRow(1)
        self.tab.btn_remove_food.click()
        self.assertEqual(self.tab.food_table.rowCount(), 2)
        self.assertTrue(self.tab.btn_add_food.isEnabled())

    def test_save_updates_vitals_food_and_root_flag(self):
        self.tab.health_spin.setValue(75)
        self.tab.used_cheats_check.setChecked(True)
        self.tab.add_food_row("Bread", 300)
        self.tab.save_changes()
        self.assertEqual(self.data["health"], 75)
        self.assertEqual(self.data["foods"], [{"name": "Bread", "time": 300}])
        self.assertTrue(self.root["used_cheats"])

    def test_styled_spinbox_keyboard(self):
        spin = self.tab.health_spin
        spin.setValue(50)
        QTest.keyClick(spin, Qt.Key_Up)
        self.assertEqual(spin.value(), 51)
        QTest.keyClick(spin, Qt.Key_Down)
        self.assertEqual(spin.value(), 50)


class AppearanceTests(QtTestCase):
    def test_load_save_preserves_known_styles_and_precise_colors(self):
        self.data.update(hair="Hair1", beard="Beard1", skin_color=[0.12345, 0.45, 0.789], hair_color=[0.2, 0.3, 0.4])
        before = deepcopy(self.data)
        tab = self.widget(AppearanceTab)
        tab.load_data(self.data)
        tab.save_changes()
        self.assertEqual(self.data, before)

    def test_female_model_disables_beard(self):
        tab = self.widget(AppearanceTab)
        tab.model_combo.setCurrentIndex(tab.model_combo.findData(1))
        self.assertFalse(tab.beard_combo.isEnabled())
        tab.model_combo.setCurrentIndex(tab.model_combo.findData(0))
        self.assertTrue(tab.beard_combo.isEnabled())


class ProgressTests(QtTestCase):
    def test_filter_and_category_change(self):
        self.data.update(known_recipes=["SwordIron", "ArmorWolfChest"], known_stations={"forge": 4})
        tab = self.widget(ProgressTab)
        tab.load_data(self.data)
        tab.search.setText(" SWORD ")
        self.assertEqual(tab.results_label.text(), "1 of 2 discoveries")
        tab.category_combo.setCurrentIndex(tab.category_combo.findData("known_stations"))
        tab.search.clear()
        self.assertIn("Level 4", tab.discoveries_list.item(0).text())
        tab.load_data({})
        self.assertEqual(tab.discoveries_list.count(), 0)
        self.assertEqual(tab.count_labels["known_recipes"].text(), "0")


class StatisticsTests(QtTestCase):
    def test_aggregates_profiles_and_filters(self):
        self.root["profiles"][0]["enemy_stats"] = [{"Troll": 2}, {"Troll": 3}]
        self.root["profiles"][1]["enemy_stats"] = [{"Troll": 4, "Boar": 1}]
        tab = self.widget(StatisticsTab)
        tab.load_data(self.data, self.root)
        self.assertEqual(tab.enemies_total.text(), "Total: 10")
        self.assertEqual(tab.enemies_table.item(0, 1).text(), "9")
        tab.enemies_search.setText("boar")
        self.assertTrue(tab.enemies_table.isRowHidden(0))
        self.assertFalse(tab.enemies_table.isRowHidden(1))

    def test_empty_reload_resets_totals(self):
        self.root["profiles"][0]["item_pickup_stats"] = {"Wood": 12}
        tab = self.widget(StatisticsTab)
        tab.load_data(self.data, self.root)
        tab.load_data({}, {})
        self.assertEqual(tab.pickups_total.text(), "Total: 0")
        self.assertEqual(tab.pickups_table.rowCount(), 0)


class CharacterTests(QtTestCase):
    def test_rename_updates_both_dictionaries(self):
        tab = self.widget(CharacterTab)
        tab.load_data(self.data, self.root)
        tab.name_input.setText("  Åsa  ")
        tab.save_changes()
        self.assertEqual(self.data["character_name"], "Åsa")
        self.assertEqual(self.root["character_name"], "Åsa")

    def test_empty_name_is_rejected(self):
        tab = self.widget(CharacterTab)
        tab.load_data(self.data, self.root)
        tab.name_input.setText("  ")
        tab.save_changes()
        self.warning.assert_called_once()
        self.assertEqual(self.root["character_name"], "Test Viking")


class WorldsTests(QtTestCase):
    def test_world_times_aggregate_and_search(self):
        self.root["profiles"][0]["known_worlds"] = {"Midgard": 3600}
        self.root["profiles"][1]["known_worlds"] = {"Midgard": 65}
        tab = self.widget(WorldsTab)
        tab.load_data(self.root)
        self.assertEqual(tab.world_list.count(), 1)
        self.assertIn("1h 1m 5s", tab.time_played_label.text())
        tab.world_search.setText("missing")
        self.assertTrue(tab.world_list.item(0).isHidden())

    def test_fallback_records_and_empty_copy_states(self):
        self.root["worlds"] = [dict(world_id=42, have_custom_spawn=True, spawn_point=[1, 2, 3])]
        tab = self.widget(WorldsTab)
        tab.load_data(self.root)
        self.assertEqual(tab.world_id_label.text(), "42")
        self.assertTrue(tab.copy_spawn_button.isEnabled())
        self.assertFalse(tab.copy_death_button.isEnabled())
        tab.load_data({})
        self.assertFalse(tab.copy_spawn_button.isEnabled())
        self.assertFalse(tab.copy_world_id_button.isEnabled())


class SkillsTests(QtTestCase):
    def test_maximize_and_reset_do_not_unlock_other_skills(self):
        self.data["skills"] = [{"id": 1, "level": 12, "xp": 3}]
        tab = self.widget(SkillsTab)
        tab.load_data(self.data)
        tab.maximize_all_skills()
        tab.save_changes()
        self.assertEqual(self.data["skills"], [{"id": 1, "level": 100, "xp": 3}])
        tab.set_all_skills0()
        tab.save_changes()
        self.assertEqual(self.data["skills"], [{"id": 1, "level": 0, "xp": 3}])
