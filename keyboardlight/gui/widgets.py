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


def stepped(slider, labels: list[str]):
    """Slider with a short tick under every step, exactly where the handle stops; text only at both ends."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QPainter
    from PyQt6.QtWidgets import QStyle, QStyleOptionSlider, QVBoxLayout, QWidget

    class Ticks(QWidget):
        def __init__(self):
            super().__init__()
            self.setFixedHeight(22)

        def paintEvent(self, _ev):
            opt = QStyleOptionSlider()
            slider.initStyleOption(opt)
            handle = slider.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                                  QStyle.SubControl.SC_SliderHandle, slider)
            hw = handle.width() or 16
            n = slider.maximum() - slider.minimum()
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            fg = self.palette().windowText().color()
            dim = QColor(fg)
            dim.setAlpha(150)
            for i in range(n + 1):
                x = hw / 2 + (slider.width() - hw) * i / max(1, n)
                p.setPen(fg if slider.value() - slider.minimum() == i else dim)
                p.drawLine(int(x), 1, int(x), 6)
            p.setPen(dim)
            f = p.font()
            f.setPointSizeF(f.pointSizeF() * 0.85)
            p.setFont(f)
            p.drawText(QRectF(0, 7, self.width() / 2, 15), Qt.AlignmentFlag.AlignLeft, labels[0])
            p.drawText(QRectF(self.width() / 2, 7, self.width() / 2, 15), Qt.AlignmentFlag.AlignRight, labels[-1])

    from PyQt6.QtCore import QEvent, QObject

    class _JumpToClick(QObject):
        """A click anywhere on the slider moves it straight to the nearest step (the handle can be dragged on)."""
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                opt = QStyleOptionSlider()
                slider.initStyleOption(opt)
                handle = slider.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                                      QStyle.SubControl.SC_SliderHandle, slider)
                if not handle.contains(ev.position().toPoint()):
                    hw = handle.width() or 16
                    span = max(1, slider.width() - hw)
                    frac = min(1.0, max(0.0, (ev.position().x() - hw / 2) / span))
                    slider.setValue(round(slider.minimum() + frac * (slider.maximum() - slider.minimum())))
            return False

    slider._jump = _JumpToClick(slider)
    slider.installEventFilter(slider._jump)
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    v.addWidget(slider)
    ticks = Ticks()
    v.addWidget(ticks)
    slider.valueChanged.connect(lambda _v: ticks.update())
    return box
