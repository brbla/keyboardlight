"""Clickable keyboard picture: shows per-key colours / remaps, supports single and multi selection."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from keyboardlight.devices.odyssey_layout import HEIGHT_U, KEYS, WIDTH_U

KEY_BG = QColor('#2b3b3f')
KEY_BG_RGB = (0x2b, 0x3b, 0x3f)
KEY_EDGE = QColor('#4b6166')
SELECT = QColor('#18d6d6')
MARK = QColor('#ffa000')


class KeyboardWidget(QWidget):
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.colors: dict[int, QColor] = {}      # slot -> fill colour (lit key); missing = unlit
        self.labels: dict[int, str] = {}         # slot -> override label (remapped keys)
        self.marked: set[int] = set()            # slots drawn with an orange outline
        self.selected: set[int] = set()
        self.multi = False                       # allow multi-selection / drag painting
        self._drag_add: bool | None = None

    # ---- geometry ----------------------------------------------------------
    def _unit(self) -> float:
        return min((self.width() - 24) / WIDTH_U, (self.height() - 24) / (HEIGHT_U + 0.1))

    def _rect(self, k) -> QRectF:
        u = self._unit()
        ox = (self.width() - WIDTH_U * u) / 2
        oy = (self.height() - HEIGHT_U * u) / 2 + 0.1 * u
        pad = u * 0.06
        return QRectF(ox + k.x * u + pad, oy + k.y * u + pad, k.w * u - 2 * pad, u - 2 * pad)

    def key_at(self, pos: QPointF):
        for k in KEYS:
            if self._rect(k).contains(pos):
                return k
        return None

    # ---- selection ---------------------------------------------------------
    def set_selected(self, slots) -> None:
        self.selected = set(slots)
        self.update()
        self.selectionChanged.emit()

    def mousePressEvent(self, e):
        k = self.key_at(e.position())
        if not k:
            if not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.set_selected(set())
            return
        if self.multi and e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self._drag_add = k.slot not in self.selected
            self.set_selected(self.selected ^ {k.slot})
        elif self.multi:
            self._drag_add = True
            self.set_selected({k.slot})
        else:
            self.set_selected({k.slot})

    def mouseMoveEvent(self, e):
        if self._drag_add is None or not self.multi:
            return
        k = self.key_at(e.position())
        if k and ((k.slot in self.selected) != self._drag_add):
            self.set_selected(self.selected | {k.slot} if self._drag_add else self.selected - {k.slot})

    def mouseReleaseEvent(self, e):
        self._drag_add = None

    # ---- painting ----------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        u = self._unit()
        ox = (self.width() - WIDTH_U * u) / 2
        oy = (self.height() - HEIGHT_U * u) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#11191b'))
        p.drawRoundedRect(QRectF(ox - 10, oy - 10, WIDTH_U * u + 20, HEIGHT_U * u + 20), 14, 14)
        font = QFont()
        for k in KEYS:
            r = self._rect(k)
            lit = self.colors.get(k.slot)
            fill = KEY_BG
            if lit is not None and lit.value() > 0:
                # show hue at full strength, blended with the key colour by intensity, so dim keys stay visible
                m = max(lit.red(), lit.green(), lit.blue())
                a = 0.35 + 0.65 * m / 255
                fill = QColor(*(round(KEY_BG_RGB[i] * (1 - a) + ch * 255 / m * a)
                                for i, ch in enumerate((lit.red(), lit.green(), lit.blue()))))
            p.setBrush(fill)
            if k.slot in self.selected:
                p.setPen(QPen(SELECT, max(2.0, u * 0.07)))
            elif k.slot in self.marked:
                p.setPen(QPen(MARK, max(2.0, u * 0.06)))
            else:
                p.setPen(QPen(KEY_EDGE, 1))
            if k.round:
                p.drawEllipse(r)
            else:
                p.drawRoundedRect(r, u * 0.12, u * 0.12)
            label = self.labels.get(k.slot, k.label)
            lum = 0.299 * fill.red() + 0.587 * fill.green() + 0.114 * fill.blue()
            p.setPen(QColor('#101010') if lum > 150 else QColor('#e8f0f0'))
            font.setPixelSize(max(8, int(u * (0.22 if len(label) > 4 else 0.3))))
            p.setFont(font)
            p.drawText(r.adjusted(2, 2, -2, -2), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, label)
        p.end()
