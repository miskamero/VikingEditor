from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QFormLayout,
    QTableWidget, QAbstractItemView, QComboBox, QListView,
)
from ui.theme import set_themed_style


DETAIL_STYLE = """
    QWidget { color: @text@; font-size: 12px; }
    QWidget#detailPage, QWidget#detailContent { background: @page@; }
    QLabel { background: transparent; }
    QLabel#pageTitle { font-size: 24px; font-weight: 600; color: @text@; }
    QLabel#pageDescription { color: @muted@; }
    QLabel#metric { font-size: 24px; font-weight: 600; color: @accentText@; }
    QLabel#badge { background: @selection@; color: @accentText@; border-radius: 5px; padding: 7px 12px; }
    QGroupBox { background: @surface@; border: 1px solid @divider@;
        border-radius: 8px; margin-top: 14px; padding: 18px 12px 12px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; color: @secondary@; }
    QLineEdit, QDoubleSpinBox, QComboBox { background: @surface@; color: @text@;
        border: 1px solid @border@; border-radius: 5px; padding: 6px 9px; min-height: 20px; }
    QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: @focus@; }
    QLineEdit[readOnly="true"] { background: @subtle@; color: @muted@; }
    QDoubleSpinBox, QComboBox { padding-right: 34px; }
    QComboBox { combobox-popup: 0; }
    QDoubleSpinBox:hover, QComboBox:hover { border-color: @hoverBorder@; }
    QDoubleSpinBox:disabled { color: @disabledText@; background: @disabledSurface@; }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border; width: 28px; border: none;
        border-left: 1px solid @divider@; background: @hover@;
    }
    QDoubleSpinBox::up-button { subcontrol-position: top right; margin-top: 1px;
        margin-right: 1px; border-top-right-radius: 4px; }
    QDoubleSpinBox::down-button { subcontrol-position: bottom right; margin-bottom: 1px;
        margin-right: 1px; border-bottom-right-radius: 4px; }
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: @selection@; }
    QDoubleSpinBox::up-button:pressed, QDoubleSpinBox::down-button:pressed { background: @pressed@; }
    QDoubleSpinBox::up-button:disabled, QDoubleSpinBox::down-button:disabled { background: @disabledSurface@; }
    QDoubleSpinBox::up-arrow { image: url("@ASSETS@/chevron-up@chevron@.png"); width: 12px; height: 12px; }
    QDoubleSpinBox::down-arrow { image: url("@ASSETS@/chevron-down@chevron@.png"); width: 12px; height: 12px; }
    QDoubleSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:off {
        image: url("@ASSETS@/chevron-up@disabledChevron@.png"); }
    QDoubleSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:off {
        image: url("@ASSETS@/chevron-down@disabledChevron@.png"); }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
        width: 28px; border: none; border-left: 1px solid @divider@;
        border-top-right-radius: 4px; border-bottom-right-radius: 4px; background: @hover@; }
    QComboBox::drop-down:hover { background: @selection@; }
    QComboBox::drop-down:on { background: @pressed@; }
    QComboBox::down-arrow { image: url("@ASSETS@/chevron-down@chevron@.png"); width: 12px; height: 12px; }
    QComboBox::down-arrow:on { image: url("@ASSETS@/chevron-up@chevron@.png"); }
    QComboBox::down-arrow:disabled { image: url("@ASSETS@/chevron-down@disabledChevron@.png"); }
    QComboBox::drop-down:disabled { background: @disabledSurface@; }
    QComboBox QAbstractItemView { background: @surface@; color: @text@;
        border: 1px solid @border@; border-radius: 6px; padding: 4px;
        outline: none; selection-background-color: @selection@; selection-color: @text@; }
    QComboBox QAbstractItemView::item { min-height: 26px; padding: 4px 10px; border-radius: 4px; }
    QScrollBar:vertical { background: @subtle@; width: 10px; margin: 0; border-radius: 5px; }
    QScrollBar::handle:vertical { background: @scrollThumb@; min-height: 28px; border-radius: 5px; }
    QScrollBar::handle:vertical:hover { background: @scrollHover@; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal { background: @subtle@; height: 10px; margin: 0; border-radius: 5px; }
    QScrollBar::handle:horizontal { background: @scrollThumb@; min-width: 28px; border-radius: 5px; }
    QScrollBar::handle:horizontal:hover { background: @scrollHover@; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
    QPushButton { background: @surface@; color: @text@; border: 1px solid @border@;
        border-radius: 6px; padding: 7px 14px; min-height: 20px; font-weight: 500; }
    QPushButton:hover { background: @hover@; border-color: @hoverBorder@; }
    QPushButton:pressed { background: @pressed@; }
    QPushButton:focus { border-color: @focus@; }
    QPushButton:disabled, QComboBox:disabled { color: @disabledText@; background: @disabledSurface@; }
    QCheckBox { spacing: 8px; padding: 5px 0; }
    QTableWidget, QListWidget { background: @surface@; alternate-background-color: @alternate@;
        color: @text@; border: 1px solid @divider@; border-radius: 7px;
        selection-background-color: @selection@; selection-color: @text@; }
    QTableWidget::item { padding: 6px 10px; border: none; }
    QListWidget::item { padding: 9px 12px; border-bottom: 1px solid @divider@; }
    QListWidget::item:selected { background: @selection@; color: @text@; }
    QHeaderView::section { background: @subtle@; color: @muted@; border: none;
        border-bottom: 1px solid @divider@; padding: 9px 10px; font-size: 11px; font-weight: 600; }
    QTabWidget::pane { background: @surface@; border: 1px solid @divider@; border-radius: 6px; }
    QTabBar::tab { background: @subtle@; color: @muted@; padding: 10px 14px; margin-right: 3px; }
    QTabBar::tab:selected { background: @surface@; color: @accentText@; border-bottom: 2px solid @focus@; }
    QTabBar::tab:hover { color: @text@; background: @selection@; }
""".replace("@ASSETS@", (Path(__file__).resolve().parent.parent / "assets").as_posix())


def detail_layout(widget, scroll=False):
    widget.setObjectName("detailPage")
    widget.setAttribute(Qt.WA_StyledBackground, True)
    set_themed_style(widget, DETAIL_STYLE)
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(20, 18, 20, 18)
    outer.setSpacing(8)
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
