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

class AppearanceTab(QWidget):
    def __init__(self):
        super().__init__()
        self.player_data = None

        main_layout = detail_layout(
            self, "Appearance", "Customize your Viking's model, hairstyle, and colors.", scroll=True
        )

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

        style_layout.addRow("Gender Model:", self.model_combo)
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

        # no female beard, klinoff is questioning?
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        polish_forms(self)
        self.update_color_preview(self.skin_preview, self.current_skin_rgb)
        self.update_color_preview(self.hair_preview, self.current_hair_rgb)

    def on_model_changed(self, index):
        selected_model = self.model_combo.currentData()
        # no beard for female model (1), disable beard combo
        self.beard_combo.setEnabled(selected_model == 0)

    def load_data(self, player_data):
        self.player_data = player_data
        if not self.player_data:
            return

        # 1. Model index
        model_idx = self.player_data.get("model_index", 0)
        index = self.model_combo.findData(model_idx)
        if index != -1:
            self.model_combo.setCurrentIndex(index)
        self.beard_combo.setEnabled(model_idx == 0)

        # 2. Hair and Beard styles
        hair_style = self.player_data.get("hair", "HairNone")
        hair_idx = self.hair_combo.findData(hair_style)

        if hair_idx != -1:
            self.hair_combo.setCurrentIndex(hair_idx)
        else:
            self.hair_combo.setCurrentIndex(0)

        beard_style = self.player_data.get("beard", "BeardNone")
        beard_idx = self.beard_combo.findData(beard_style)

        if beard_idx != -1:
            self.beard_combo.setCurrentIndex(beard_idx)
        else:
            self.beard_combo.setCurrentIndex(0)

        # 3. Colors (0.0 - 1.0 floats to 0 - 255 ints)
        self.current_skin_rgb = self.player_data.get("skin_color", [1.0, 1.0, 1.0])
        self.current_hair_rgb = self.player_data.get("hair_color", [1.0, 1.0, 1.0])

        self.update_color_preview(self.skin_preview, self.current_skin_rgb)
        self.update_color_preview(self.hair_preview, self.current_hair_rgb)

    def update_color_preview(self, widget, rgb_list):
        r = int(max(0.0, min(1.0, rgb_list[0])) * 255)
        g = int(max(0.0, min(1.0, rgb_list[1])) * 255)
        b = int(max(0.0, min(1.0, rgb_list[2])) * 255)
        
        palette = widget.palette()
        palette.setColor(QPalette.Window, QColor(r, g, b))
        widget.setPalette(palette)
        color = QColor(r, g, b)
        widget.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #d7dde0; border-radius: 8px;"
        )
        label = self.skin_color_label if widget is self.skin_preview else self.hair_color_label
        label.setText(f"{color.name().upper()}   ·   RGB {r}, {g}, {b}")

    def choose_skin_color(self):
        r = int(self.current_skin_rgb[0] * 255)
        g = int(self.current_skin_rgb[1] * 255)
        b = int(self.current_skin_rgb[2] * 255)
        
        color = QColorDialog.getColor(QColor(r, g, b), self, "Select Skin Color")
        if color.isValid():
            self.current_skin_rgb = [color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0]
            self.update_color_preview(self.skin_preview, self.current_skin_rgb)

    def choose_hair_color(self):
        r = int(self.current_hair_rgb[0] * 255)
        g = int(self.current_hair_rgb[1] * 255)
        b = int(self.current_hair_rgb[2] * 255)
        
        color = QColorDialog.getColor(QColor(r, g, b), self, "Select Hair/Beard Color")
        if color.isValid():
            self.current_hair_rgb = [color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0]
            self.update_color_preview(self.hair_preview, self.current_hair_rgb)

    def save_changes(self):
        if not self.player_data:
            return

        self.player_data["model_index"] = self.model_combo.currentData()
        self.player_data["hair"] = self.hair_combo.currentData()
        self.player_data["beard"] = self.beard_combo.currentData()
        self.player_data["skin_color"] = self.current_skin_rgb
        self.player_data["hair_color"] = self.current_hair_rgb
