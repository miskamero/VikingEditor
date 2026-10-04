from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QScrollArea, QFrame, QFormLayout,
    QTableWidget, QAbstractItemView, QComboBox, QListView,
)


DETAIL_STYLE = """
    QWidget { color: #303438; font-size: 12px; }
    QWidget#detailPage, QWidget#detailContent { background: #f4f6f7; }
    QLabel { background: transparent; }
    QLabel#pageTitle { font-size: 24px; font-weight: 600; color: #252b29; }
    QLabel#pageDescription { color: #737c80; }
    QLabel#metric { font-size: 24px; font-weight: 600; color: #45623a; }
    QLabel#badge { background: #eaf1e5; color: #45623a; border-radius: 5px; padding: 7px 12px; }
    QGroupBox { background: white; border: 1px solid #dfe4e5;
        border-radius: 8px; margin-top: 14px; padding: 18px 12px 12px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; color: #536348; }
    QLineEdit, QDoubleSpinBox, QComboBox { background: white; color: #303438;
        border: 1px solid #d7dde0; border-radius: 5px; padding: 6px 9px; min-height: 20px; }
    QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #7a9567; }
    QLineEdit[readOnly="true"] { background: #f5f7f8; color: #667175; }
    QDoubleSpinBox, QComboBox { padding-right: 34px; }
    QComboBox { combobox-popup: 0; }
    QDoubleSpinBox:hover, QComboBox:hover { border-color: #a3b598; }
    QDoubleSpinBox:disabled { color: #9ba3a6; background: #f5f6f7; }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border; width: 28px; border: none;
        border-left: 1px solid #e5e9e3; background: #f5f8f2;
    }
    QDoubleSpinBox::up-button { subcontrol-position: top right; margin-top: 1px;
        margin-right: 1px; border-top-right-radius: 4px; }
    QDoubleSpinBox::down-button { subcontrol-position: bottom right; margin-bottom: 1px;
        margin-right: 1px; border-bottom-right-radius: 4px; }
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #e6efdf; }
    QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed { background: #d5e4cb; }
    QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled { background: #f5f6f7; }
    QDoubleSpinBox::up-arrow { image: url("@ASSETS@/chevron-up.png"); width: 12px; height: 12px; }
    QDoubleSpinBox::down-arrow { image: url("@ASSETS@/chevron-down.png"); width: 12px; height: 12px; }
    QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:off {
        image: url("@ASSETS@/chevron-up-disabled.png"); }
    QDoubleSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:off {
        image: url("@ASSETS@/chevron-down-disabled.png"); }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
        width: 28px; border: none; border-left: 1px solid #e5e9e3;
        border-top-right-radius: 4px; border-bottom-right-radius: 4px; background: #f5f8f2; }
    QComboBox::drop-down:hover { background: #e6efdf; }
    QComboBox::drop-down:on { background: #d5e4cb; }
    QComboBox::down-arrow { image: url("@ASSETS@/chevron-down.png"); width: 12px; height: 12px; }
    QComboBox::down-arrow:on { image: url("@ASSETS@/chevron-up.png"); }
    QComboBox::down-arrow:disabled { image: url("@ASSETS@/chevron-down-disabled.png"); }
    QComboBox::drop-down:disabled { background: #f5f6f7; }
    QComboBox QAbstractItemView { background: white; color: #303438;
        border: 1px solid #d7dde0; border-radius: 6px; padding: 4px;
        outline: none; selection-background-color: #eaf1e5; selection-color: #303438; }
    QComboBox QAbstractItemView::item { min-height: 26px; padding: 4px 10px; border-radius: 4px; }
    QScrollBar:vertical { background: #f0f3f1; width: 10px; margin: 0; border-radius: 5px; }
    QScrollBar::handle:vertical { background: #c3ccc0; min-height: 28px; border-radius: 5px; }
    QScrollBar::handle:vertical:hover { background: #9aab92; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal { background: #f0f3f1; height: 10px; margin: 0; border-radius: 5px; }
    QScrollBar::handle:horizontal { background: #c3ccc0; min-width: 28px; border-radius: 5px; }
    QScrollBar::handle:horizontal:hover { background: #9aab92; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
    QPushButton { background: white; color: #303438; border: 1px solid #d7dade;
        border-radius: 6px; padding: 7px 14px; min-height: 20px; font-weight: 500; }
    QPushButton:hover { background: #f0f5ec; border-color: #a3b598; }
    QPushButton:pressed { background: #e3eddc; }
    QPushButton:focus { border-color: #6d895b; }
    QPushButton:disabled, QComboBox:disabled { color: #9ba3a6; background: #f5f6f7; }
    QCheckBox { spacing: 8px; padding: 5px 0; }
    QTableWidget, QListWidget { background: white; alternate-background-color: #f8fafb;
        color: #303438; border: 1px solid #dfe4e5; border-radius: 7px;
        selection-background-color: #eaf1e5; selection-color: #263422; }
    QTableWidget::item { padding: 6px 10px; border: none; }
    QListWidget::item { padding: 9px 12px; border-bottom: 1px solid #f0f2f3; }
    QListWidget::item:selected { background: #eaf1e5; color: #263422; }
    QHeaderView::section { background: #f6f7f8; color: #686d72; border: none;
        border-bottom: 1px solid #e2e5e8; padding: 9px 10px; font-size: 11px; font-weight: 600; }
    QTabWidget::pane { background: white; border: 1px solid #dfe4e5; border-radius: 6px; }
    QTabBar::tab { background: #eef1f2; color: #687276; padding: 10px 14px; margin-right: 3px; }
    QTabBar::tab:selected { background: white; color: #45623a; border-bottom: 2px solid #7a9567; }
    QTabBar::tab:hover { color: #303438; background: #eaf1e5; }
""".replace("@ASSETS@", (Path(__file__).resolve().parent.parent / "assets").as_posix())


def detail_layout(widget, title, description, scroll=False):
    widget.setObjectName("detailPage")
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setStyleSheet(DETAIL_STYLE)
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(20, 18, 20, 18)
    outer.setSpacing(8)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    outer.addWidget(heading)
    subtitle = QLabel(description)
    subtitle.setObjectName("pageDescription")
    subtitle.setWordWrap(True)
    outer.addWidget(subtitle)
    outer.addSpacing(8)
    content = QWidget()
    content.setObjectName("detailContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)
    if scroll:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(content)
        outer.addWidget(area, 1)
    else:
        outer.addWidget(content, 1)
    return layout


def polish_forms(widget):
    for combo in widget.findChildren(QComboBox):
        polish_combo(combo)
    for form in widget.findChildren(QFormLayout):
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)


def polish_combo(combo):
    # Use a scrollable list instead of the platform's menu-style popup.
    combo.setView(QListView())
    combo.setMaxVisibleItems(10)
    combo.view().setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)


def polish_table(table):
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(42)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
