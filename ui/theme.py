"""Application palette and color roles shared by component stylesheets."""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory


# Light and dark values, respectively. Widget geometry stays in its original stylesheet.
COLORS = {
    "page": ("#f4f6f7", "#222627"),
    "surface": ("white", "#303536"),
    "alternate": ("#f8fafb", "#292e2f"),
    "empty": ("#f8fafb", "#252a2b"),
    "text": ("#303438", "#ebece7"),
    "muted": ("#737c80", "#b1bbb7"),
    "disabledText": ("#9ba3a6", "#98a29e"),
    "disabledSurface": ("#f5f6f7", "#292e2f"),
    "border": ("#d7dade", "#525b59"),
    "divider": ("#dfe4e5", "#434b49"),
    "subtle": ("#f6f7f8", "#292e30"),
    "selection": ("#eaf1e5", "#394c3f"),
    "highlight": ("#45623a", "#526b55"),
    "hover": ("#f0f5ec", "#39433d"),
    "pressed": ("#e3eddc", "#46594a"),
    "hoverBorder": ("#a3b598", "#7d9381"),
    "focus": ("#6d895b", "#a3bd92"),
    "accentText": ("#45623a", "#c1d6b6"),
    "secondary": ("#536348", "#bacab9"),
    "quality": ("#536348", "#ddc38a"),
    "primary": ("#45623a", "#506c52"),
    "primaryHover": ("#567849", "#5f7a60"),
    "onPrimary": ("white", "#f8fbf6"),
    "scrollThumb": ("#c3ccc0", "#65716a"),
    "scrollHover": ("#9aab92", "#849389"),
    "preview": ("#252b27", "#252b27"),
    "danger": ("#b00020", "#efa99f"),
    "warningText": ("#793b31", "#f0bab3"),
    "warningSurface": ("#f3e4de", "#523835"),
    "arrow": ("#7b8389", "#b2beb6"),
}

# The built-in pale chevron is legible on a charcoal control. Its darker
# counterpart becomes the disabled glyph without a second set of assets.
_CHEVRONS = {"chevron": ("", "-disabled"), "disabledChevron": ("-disabled", "")}
_TOKENS = {**COLORS, **_CHEVRONS}
_TOKEN = re.compile(r"@([A-Za-z]+)@")


def theme_color(role):
    return COLORS[role][bool(QApplication.instance().property("darkMode"))]


def _render(template, dark):
    return _TOKEN.sub(lambda match: _TOKENS[match[1]][dark], template)


def set_themed_style(widget, template):
    """Keep the source on its Qt owner so existing and future widgets use the same rules."""
    widget.setProperty("themeTemplate", template)
    widget.setStyleSheet(_render(template, bool(QApplication.instance().property("darkMode"))))


class _DarkStyle(QProxyStyle):
    """Use Fusion's palette-aware painting with the original style's layout metrics."""

    def __init__(self, native_style):
        super().__init__("Fusion")
        self.metrics = QStyleFactory.create(native_style)
        self.metrics.setParent(self)

    def pixelMetric(self, metric, option=None, widget=None):
        return self.metrics.pixelMetric(metric, option, widget)

    def sizeFromContents(self, contents, option, size, widget=None):
        return self.metrics.sizeFromContents(contents, option, size, widget)

    def subElementRect(self, element, option, widget=None):
        return self.metrics.subElementRect(element, option, widget)

    def layoutSpacing(self, first, second, orientation, option=None, widget=None):
        return self.metrics.layoutSpacing(first, second, orientation, option, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_MainWindow_SpaceBelowMenuBar:
            return self.metrics.styleHint(hint, option, widget, returnData)
        return super().styleHint(hint, option, widget, returnData)


def apply_theme(dark):
    app = QApplication.instance()
    if app.property("lightStyle") is None:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
        app.setProperty("lightStyle", app.style().objectName())
        app.setProperty("lightPalette", QPalette(app.palette()))
    if bool(app.property("darkMode")) == dark:
        return

    app.setProperty("darkMode", dark)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    if dark:
        # The native Windows renderer ignores palette brushes for menus,
        # form fields and message boxes. Fusion paints those from QPalette.
        if app.property("lightStyle").lower() != "fusion":
            app.setStyle(_DarkStyle(app.property("lightStyle")))
        palette = QPalette()
        for role, token in {
            QPalette.Window: "page", QPalette.WindowText: "text",
            QPalette.Base: "surface", QPalette.AlternateBase: "alternate",
            QPalette.Text: "text", QPalette.Button: "surface", QPalette.ButtonText: "text",
            QPalette.BrightText: "onPrimary", QPalette.Highlight: "highlight",
            QPalette.HighlightedText: "text", QPalette.Accent: "focus",
            QPalette.Light: "border", QPalette.Midlight: "divider", QPalette.Mid: "border",
            QPalette.Dark: "empty", QPalette.Shadow: "page",
            QPalette.PlaceholderText: "muted", QPalette.ToolTipBase: "surface",
            QPalette.ToolTipText: "text", QPalette.Link: "accentText", QPalette.LinkVisited: "muted",
        }.items():
            palette.setColor(role, QColor(theme_color(token)))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText, QPalette.HighlightedText):
            palette.setColor(QPalette.Disabled, role, QColor(theme_color("disabledText")))
        app.setPalette(palette)
    else:
        if app.style().objectName() != app.property("lightStyle"):
            app.setStyle(app.property("lightStyle"))
        app.setPalette(app.property("lightPalette"))

    for widget in app.allWidgets():
        template = widget.property("themeTemplate")
        if template:
            widget.setStyleSheet(_render(template, dark))
