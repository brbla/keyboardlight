"""Small shared GUI helpers."""
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QComboBox

_NAV_KEYS = {Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape,
             Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_Tab,
             Qt.Key.Key_Backtab}


class _NavOnly(QObject):
    """Let a combo box (and its popup list) react only to navigation keys – typing never changes it."""

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride):
            if ev.key() not in _NAV_KEYS or ev.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                              | Qt.KeyboardModifier.AltModifier):
                ev.ignore()
                return True
        return False


def nav_only(combo: QComboBox) -> QComboBox:
    combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    f = _NavOnly(combo)
    combo.installEventFilter(f)
    combo.view().installEventFilter(f)
    combo._nav_filter = f            # keep a reference
    return combo
