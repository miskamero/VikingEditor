from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QComboBox,
    QPushButton,
    QColorDialog,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
)
from PySide6.QtGui import QColor, QPalette
from data.beards import VALHEIM_BEARDS
from data.hairs import VALHEIM_HAIRS
from ui.tabStyle import detail_layout, polish_forms
from ui.theme import set_themed_style

class AppearanceTab(QWidget):
    def __init__(self):
        super().__init__()
        self.player_data = None
        self.edits = {}

        main_layout = detail_layout(self, scroll=True)

        # 1. Model & Style Group
        style_group = QGroupBox("Physical Customization")
        style_layout = QFormLayout(style_group)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Male (Model 0)", 0)
        self.model_combo.addItem("Female (Model 1)", 1)

        self.hair_combo = QComboBox()

        for hair_id, hair_name in VALHEIM_HAIRS.items():
            self.hair_combo.addItem(hair_name, hair_id)

        self.beard_combo = QComboBox()

        for beard_id, beard_name in VALHEIM_BEARDS.items():
            self.beard_combo.addItem(beard_name, beard_id)

        style_layout.addRow("Character Model:", self.model_combo)
        style_layout.addRow("Hair Style:", self.hair_combo)
        style_layout.addRow("Beard Style:", self.beard_combo)
        main_layout.addWidget(style_group)

        color_group = QGroupBox("Color Customization")
        color_layout = QHBoxLayout(color_group)

        # Skin Color selection
        skin_vbox = QVBoxLayout()
        skin_vbox.addWidget(QLabel("Skin Tone:"))
        self.btn_skin_color = QPushButton("Pick Skin Color")
        self.skin_preview = QWidget()
        self.skin_preview.setMinimumHeight(100)
        self.skin_preview.setAutoFillBackground(True)
        skin_vbox.addWidget(self.skin_preview)
        self.skin_color_label = QLabel()
        skin_vbox.addWidget(self.skin_color_label)
        skin_vbox.addWidget(self.btn_skin_color)
        color_layout.addLayout(skin_vbox)

        color_layout.addSpacing(40)

        # Hair Color selection
        hair_vbox = QVBoxLayout()
        hair_vbox.addWidget(QLabel("Hair/Beard Color:"))
        self.btn_hair_color = QPushButton("Pick Hair Color")
        self.hair_preview = QWidget()
        self.hair_preview.setMinimumHeight(100)
        self.hair_preview.setAutoFillBackground(True)
        hair_vbox.addWidget(self.hair_preview)
        self.hair_color_label = QLabel()
        hair_vbox.addWidget(self.hair_color_label)
        hair_vbox.addWidget(self.btn_hair_color)
        color_layout.addLayout(hair_vbox)

        main_layout.addWidget(color_group)
        main_layout.addStretch()

        # Placeholders for RGB values (0.0 - 1.0 floats)
        self.current_skin_rgb = [1.0, 1.0, 1.0]
        self.current_hair_rgb = [1.0, 1.0, 1.0]

        self.btn_skin_color.clicked.connect(self.choose_skin_color)
        self.btn_hair_color.clicked.connect(self.choose_hair_color)

        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        for field, combo in (("model_index", self.model_combo), ("hair", self.hair_combo),
                             ("beard", self.beard_combo)):
            combo.currentIndexChanged.connect(
                lambda _, key=field, selector=combo: self.edits.update({key: selector.currentData()})
            )
        polish_forms(self)
        self.update_color_preview(self.skin_preview, self.current_skin_rgb)
        self.update_color_preview(self.hair_preview, self.current_hair_rgb)

    def on_model_changed(self):
        selected_model = self.model_combo.currentData()
        # no beard for female model (1), disable beard combo
        self.beard_combo.setEnabled(selected_model == 0)

    def load_data(self, player_data):
        self.player_data = player_data
        self.edits.clear()
        data = player_data or {}
        for field, combo, count in (("model_index", self.model_combo, 2),
                                    ("hair", self.hair_combo, len(VALHEIM_HAIRS)),
                                    ("beard", self.beard_combo, len(VALHEIM_BEARDS))):
            with QSignalBlocker(combo):
                if combo.count() > count:
                    combo.removeItem(count)
                value = data.get(field, combo.itemData(0))
                if combo.findData(value) == -1:
                    label = f"Unlisted model ({value})" if field == "model_index" else value
                    combo.addItem(label, value)
                combo.setCurrentIndex(combo.findData(value))
        self.on_model_changed()

        self.current_skin_rgb = data.get("skin_color", [1.0, 1.0, 1.0])
        self.current_hair_rgb = data.get("hair_color", [1.0, 1.0, 1.0])

        self.update_color_preview(self.skin_preview, self.current_skin_rgb)
        self.update_color_preview(self.hair_preview, self.current_hair_rgb)

    def update_color_preview(self, widget, rgb_list):
        color = self.display_color(rgb_list)
        r, g, b, _ = color.getRgb()
        palette = widget.palette()
        palette.setColor(QPalette.Window, color)
        widget.setPalette(palette)
        set_themed_style(
            widget,
            f"background-color: {color.name()}; border: 1px solid @border@; border-radius: 8px;"
        )
        label = self.skin_color_label if widget is self.skin_preview else self.hair_color_label
        label.setText(f"{color.name().upper()}   ·   RGB {r}, {g}, {b}")

    @staticmethod
    def display_color(rgb):
        return QColor(*(int(max(0.0, min(1.0, channel)) * 255) for channel in rgb))

    def choose_skin_color(self):
        initial = self.display_color(self.current_skin_rgb)
        color = QColorDialog.getColor(initial, self, "Select Skin Color")
        if color.isValid() and color != initial:
            self.current_skin_rgb = [color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0]
            self.edits["skin_color"] = self.current_skin_rgb
            self.update_color_preview(self.skin_preview, self.current_skin_rgb)

    def choose_hair_color(self):
        initial = self.display_color(self.current_hair_rgb)
        color = QColorDialog.getColor(initial, self, "Select Hair/Beard Color")
        if color.isValid() and color != initial:
            self.current_hair_rgb = [color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0]
            self.edits["hair_color"] = self.current_hair_rgb
            self.update_color_preview(self.hair_preview, self.current_hair_rgb)

    def save_changes(self, player_data=None):
        target = self.player_data if player_data is None else player_data
        if target:
            target.update(self.edits)
