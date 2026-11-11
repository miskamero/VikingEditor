from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QDoubleSpinBox,
    QHeaderView,
    QLabel,
    QGroupBox
)

from PySide6.QtGui import QPainter, QPen, QColor, QDoubleValidator

from PySide6.QtCore import Qt

from data.skills import VALHEIM_SKILLS


class ModernSpinBox(QDoubleSpinBox):
    def textFromValue(self, value):
        # Compact display without rounding the stored float32 to fixed decimals.
        return self.locale().toString(value, "g", 17)

    def valueFromText(self, text):
        return self.locale().toDouble(text)[0]

    def validate(self, text, position):
        validator = QDoubleValidator(self.minimum(), self.maximum(), 149)
        validator.setLocale(self.locale())
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        return validator.validate(text, position)

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        arrow_x = width - 15

        painter.setPen(
            QPen(
                QColor("#7b8389"),
                1.5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )

        painter.drawLine(
            arrow_x - 3,
            height // 2 - 4,
            arrow_x,
            height // 2 - 7,
        )

        painter.drawLine(
            arrow_x,
            height // 2 - 7,
            arrow_x + 3,
            height // 2 - 4,
        )

        painter.drawLine(
            arrow_x - 3,
            height // 2 + 4,
            arrow_x,
            height // 2 + 7,
        )

        painter.drawLine(
            arrow_x,
            height // 2 + 7,
            arrow_x + 3,
            height // 2 + 4,
        )

class SkillsTab(QWidget):
    def __init__(self):
        super().__init__()

        self.player_data = None

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        toolbar_group = QGroupBox("Skill Actions")
        toolbar = QHBoxLayout(toolbar_group)
        toolbar.setContentsMargins(14, 12, 14, 12)
        toolbar.setSpacing(8)

        self.btn_max_all = QPushButton("Maximize All")
        self.btn_max_all.setMinimumHeight(34)
        self.btn_max_all.setToolTip("Maximize unlocked vanilla skills. Custom skills are unchanged.")

        self.btn_set_all0 = QPushButton("Reset All")
        self.btn_set_all0.setMinimumHeight(34)
        self.btn_set_all0.setToolTip("Reset unlocked vanilla levels to zero. Custom skills are unchanged.")

        self.skill_count_label = QLabel("Skills: 0")
        self.skill_count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight |
            Qt.AlignmentFlag.AlignVCenter
        )

        toolbar.addWidget(self.btn_max_all)
        toolbar.addWidget(self.btn_set_all0)
        toolbar.addStretch()
        toolbar.addWidget(self.skill_count_label)

        layout.addWidget(toolbar_group)

        self.table = QTableWidget()
        self.table.setColumnCount(4)

        self.table.setHorizontalHeaderLabels([
            "Skill",
            "Level",
            "XP Progress",
            "Status",
        ])
        self.xp_tooltip = (
            "XP earned toward the next skill level, not a percentage. "
            "Fractional skill levels are separate and can result from skill loss on death. "
            "Mods may use different progression rules."
        )
        self.table.horizontalHeaderItem(2).setToolTip(self.xp_tooltip)

        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)

        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )

        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch
        )

        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents
        )

        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.Fixed
        )
        header.resizeSection(3, 110)

        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft |
            Qt.AlignmentFlag.AlignVCenter
        )

        for column in (1, 2, 3):
            header_item = self.table.horizontalHeaderItem(column)

            if header_item:
                header_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #fafafa;
                border: 1px solid #e2e5e8;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #eef6e8;
                selection-color: #202420;
                outline: none;
            }

            QTableWidget::item {
                padding: 6px 10px;
                border: none;
                color: #252525;
            }

            QTableWidget::item:selected {
                background-color: #eef6e8;
                color: #202525;
            }

            QHeaderView::section {
                background-color: #f6f7f8;
                color: #686d72;
                border: none;
                border-bottom: 1px solid #e2e5e8;
                padding: 8px 10px;
                font-size: 11px;
                font-weight: 600;
            }

            QHeaderView::section:first {
                border-top-left-radius: 7px;
            }

            QHeaderView::section:last {
                border-top-right-radius: 7px;
            }
        """)

        layout.addWidget(self.table)

        self.btn_max_all.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #303438;
                border: 1px solid #d7dade;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #f5f7f8;
                border-color: #bfc4c9;
            }

            QPushButton:pressed {
                background-color: #eceff1;
            }
        """)

        self.btn_set_all0.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #303438;
                border: 1px solid #d7dade;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 500;
            }

            QPushButton:hover {
                background-color: #f5f7f8;
                border-color: #bfc4c9;
            }

            QPushButton:pressed {
                background-color: #eceff1;
            }
        """)

        self.skill_count_label.setStyleSheet("""
            QLabel {
                color: #777d82;
                font-size: 11px;
                font-weight: 500;
            }
        """)

        self.btn_max_all.clicked.connect(
            self.maximize_all_skills
        )

        self.btn_set_all0.clicked.connect(
            self.set_all_skills0
        )

    def load_data(self, player_data):
        self.player_data = player_data

        self.table.setRowCount(0)
        self.skill_records = []
        saved_skills = player_data.get("skills", [])
        saved_rows = {}
        new_rows = []

        # Keep the built-in ordering and offer missing vanilla skills to unlock.
        for skill_id, skill_name in VALHEIM_SKILLS.items():
            if skill_id == 0:
                continue

            index = next((i for i, skill in enumerate(saved_skills)
                          if i not in saved_rows and skill.get("id") == skill_id), None)
            skill_data = saved_skills[index] if index is not None else None
            if index is not None:
                saved_rows[index] = self.table.rowCount()
            else:
                new_rows.append(self.table.rowCount())

            self.add_skill_row(
                skill_id,
                skill_name,
                skill_data
            )

        # Include unknown IDs (even 0) and duplicate records without collapsing
        # them. The game stores no skill names; optional imported names survive.
        for index, skill in enumerate(saved_skills):
            if index not in saved_rows:
                skill_id = skill["id"]
                name = skill.get("name")
                if not isinstance(name, str) or not name.strip():
                    name = VALHEIM_SKILLS.get(skill_id) if skill_id else None
                saved_rows[index] = self.table.rowCount()
                self.add_skill_row(skill_id, name or f"Unknown Skill (ID: {skill_id})", skill)
        self.save_order = [saved_rows[i] for i in range(len(saved_skills))] + new_rows
        self.update_skill_count()

    def add_skill_row(
        self,
        skill_id,
        skill_name,
        skill_data=None
    ):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.skill_records.append(dict(skill_data) if skill_data is not None
                                  else {"id": skill_id, "level": 0.0, "xp": 0.0})
        vanilla = skill_id != 0 and skill_id in VALHEIM_SKILLS

        skill_item = QTableWidgetItem(skill_name)

        skill_item.setData(
            Qt.ItemDataRole.UserRole,
            skill_id
        )

        skill_item.setFlags(
            skill_item.flags()
            & ~Qt.ItemFlag.ItemIsEditable
        )

        self.table.setItem(
            row,
            0,
            skill_item
        )

        level_spin = ModernSpinBox()

        # 149 fractional places cover every finite binary32 value, including
        # subnormals. Custom skill limits cannot be inferred from the save.
        float_max = 3.4028234663852886e38
        level_spin.setDecimals(149)
        level_spin.setRange(-float_max, float_max)
        if vanilla:
            level = skill_data.get("level", 0.0) if skill_data is not None else 0.0
            level_spin.setRange(min(0.0, level), max(100.0, level))
        level_spin.setSingleStep(1.0)
        level_spin.setMinimumWidth(120)

        level_spin.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.style_spinbox(level_spin)

        if skill_data is not None:
            level_spin.setValue(
                skill_data.get("level", 1.0)
            )
        else:
            level_spin.setValue(0.0)

        self.table.setCellWidget(
            row,
            1,
            level_spin
        )

        xp_spin = ModernSpinBox()

        xp_spin.setDecimals(149)
        xp_spin.setRange(-float_max, float_max)
        xp_spin.setToolTip(self.xp_tooltip)
        xp_spin.setSingleStep(1.0)
        xp_spin.setMinimumWidth(160)

        xp_spin.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.style_spinbox(xp_spin)

        if skill_data is not None:
            xp_spin.setValue(
                skill_data.get("xp", 0.0)
            )
        else:
            xp_spin.setValue(0.0)

        self.table.setCellWidget(
            row,
            2,
            xp_spin
        )
        # Only edited properties replace original values; other record data and
        # untouched values survive unrelated edits without widget normalization.
        level_spin.valueChanged.connect(lambda value, r=row: self.skill_records[r].update(level=value))
        xp_spin.valueChanged.connect(lambda value, r=row: self.skill_records[r].update(xp=value))

        unlocked = skill_data is not None
        status_button = QPushButton("Lock" if unlocked else "Unlock")
        status_button.setCheckable(True)
        status_button.setChecked(unlocked)
        status_button.setFixedWidth(88)
        status_button.setMinimumHeight(29)
        status_button.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #587544;
                border: 1px solid #bfd2b2;
                border-radius: 5px;
                padding: 4px 12px;
                font-size: 10px;
                font-weight: 600;
            }

            QPushButton:checked {
                background-color: #edf6e7;
                color: #55743e;
                border-color: #c9dfba;
            }

            QPushButton:hover {
                background-color: #f2f8ee;
                border-color: #9fbd8d;
            }

            QPushButton:pressed {
                background-color: #e8f1e2;
            }
        """)
        status_button.setToolTip(
            "Unlocked: lock to remove this skill and clear its level and XP."
            if unlocked else "Locked: unlock at level 1 with zero XP."
        )
        if not vanilla:
            status_button.setToolTip("Lock to protect this custom skill from edits. Its saved data is retained.")
        status_button.toggled.connect(
            lambda checked, r=row: self._on_skill_toggled(r, checked)
        )
        self.table.setCellWidget(row, 3, status_button)
        level_spin.setEnabled(unlocked)
        xp_spin.setEnabled(unlocked)

    def is_skill_unlocked(self, row):
        status_button = self.table.cellWidget(row, 3)
        return isinstance(status_button, QPushButton) and status_button.isChecked()

    def is_vanilla_skill(self, row):
        skill_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return skill_id != 0 and skill_id in VALHEIM_SKILLS

    def _on_skill_toggled(self, row, unlocked):
        level_widget = self.table.cellWidget(row, 1)
        xp_widget = self.table.cellWidget(row, 2)
        status_button = self.table.cellWidget(row, 3)

        if self.is_vanilla_skill(row):
            level_widget.setValue(1.0 if unlocked else 0.0)
            xp_widget.setValue(0.0)
        level_widget.setEnabled(unlocked)
        xp_widget.setEnabled(unlocked)
        status_button.setText("Lock" if unlocked else "Unlock")
        status_button.setToolTip(
            "Unlocked: lock to remove this skill and clear its level and XP."
            if unlocked else "Locked: unlock at level 1 with zero XP."
        )
        if not self.is_vanilla_skill(row):
            status_button.setToolTip(
                "Lock to protect this custom skill from edits. Its saved data is retained."
                if unlocked else "Unlock to edit this custom skill. Its saved data is retained."
            )

    def style_spinbox(self, widget):
        widget.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #ffffff;
                color: #303438;
                border: 1px solid #d9dde1;
                border-radius: 6px;
                padding: 3px 26px 3px 8px;
            }

            QDoubleSpinBox:hover {
                border-color: #b9bec3;
            }

            QDoubleSpinBox:focus {
                border-color: #9caf8d;
            }

            QDoubleSpinBox:disabled {
                background-color: #f5f6f7;
                color: #aeb3b7;
                border-color: #e4e6e8;
            }

            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button {
                width: 22px;
                border: none;
                background: transparent;
            }

            QDoubleSpinBox::up-button:hover,
            QDoubleSpinBox::down-button:hover {
                background-color: #f1f4ef;
            }

            QDoubleSpinBox::up-button:pressed,
            QDoubleSpinBox::down-button:pressed {
                background-color: #e7eee3;
            }
        """)

    def unlock_skill(self, row):
        if 0 <= row < self.table.rowCount():
            self.table.cellWidget(row, 3).setChecked(True)

    def lock_skill(self, row):
        if 0 <= row < self.table.rowCount():
            self.table.cellWidget(row, 3).setChecked(False)

    def maximize_all_skills(self):
        for row in range(self.table.rowCount()):
            level_widget = self.table.cellWidget(row, 1)

            if (
                isinstance(level_widget, QDoubleSpinBox)
                and self.is_skill_unlocked(row)
                and self.is_vanilla_skill(row)
            ):
                level_widget.setValue(100.0)

    def set_all_skills0(self):
        for row in range(self.table.rowCount()):
            level_widget = self.table.cellWidget(row, 1)

            if (
                isinstance(level_widget, QDoubleSpinBox)
                and self.is_skill_unlocked(row)
                and self.is_vanilla_skill(row)
            ):
                level_widget.setValue(0.0)

    def save_changes(self):
        if self.player_data is None:
            return

        updated_skills = []

        for row in self.save_order:
            skill_item = self.table.item(row, 0)

            level_widget = self.table.cellWidget(row, 1)

            xp_widget = self.table.cellWidget(row, 2)

            if (
                not skill_item
                or not isinstance(
                    level_widget,
                    QDoubleSpinBox
                )
                or not isinstance(
                    xp_widget,
                    QDoubleSpinBox
                )
            ):
                continue

            # Vanilla locking retains its existing removal behavior. Custom
            # locking only prevents editing because mod reset rules are unknown.
            if not self.is_skill_unlocked(row) and self.is_vanilla_skill(row):
                continue

            updated_skills.append(dict(self.skill_records[row]))

        self.player_data["skills"] = updated_skills

    def update_skill_count(self):
        count = self.table.rowCount()

        self.skill_count_label.setText(
            f"Skills: {count}"
        )
