"""AULA WIN68 HE page: lighting, actuation overview, backup / restore."""
from __future__ import annotations

import glob
import os
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QMessageBox, QPushButton, QSlider, QTabWidget, QVBoxLayout, QWidget)

from keyboardlight.devices import aula_layout as L
from keyboardlight.devices.aula import BACKUP_DIR, Aula, AulaError, full_backup, restore
from keyboardlight.gui.keyboard_widget import KeyboardWidget
from keyboardlight.gui.widgets import nav_only
from keyboardlight.i18n import _

NO_SPEED = {0, 10}            # static, custom colours
NO_COLOR = {10}               # custom colours use the per-key table


class AulaPage(QWidget):
    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.status = status                      # callable(str) -> show a status-bar message
        self.dev: Aula | None = None
        self.light = bytearray()
        self.act: dict[int, float | None] = {}
        self._loading = False
        self._timer = QTimer(self, singleShot=True, interval=400, timeout=self._write_light)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.kbd = KeyboardWidget(keys=L.KEYS, width_u=L.WIDTH_U, height_u=L.HEIGHT_U)
        v.addWidget(self.kbd, 3)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet('QTabBar::tab { background: #163236; padding: 6px 14px; } '
                                'QTabBar::tab:selected { background: #23474b; color: #18d6d6; }')
        self.tabs.addTab(self._build_light(), _('Podsvícení'))
        self.tabs.addTab(self._build_act(), _('Spínače'))
        self.tabs.addTab(self._build_backup(), _('Záloha'))
        self.tabs.currentChanged.connect(lambda _i: self._refresh_kbd())
        v.addWidget(self.tabs, 2)

    # ------------------------------------------------------------------ device
    def connect_device(self) -> bool:
        if self.dev:
            self.dev.close()
            self.dev = None
        try:
            self.dev = Aula()
            info = self.dev.info()
            self.light = bytearray(self.dev.read_lighting_raw())
            self.act = {k.slot: Aula.decode_actuation(self.dev.read_key_block(k.slot)) for k in L.KEYS}
        except (AulaError, OSError) as e:
            self.status(str(e))
            if self.dev:
                self.dev.close()
            self.dev = None
            return False
        self.info_lbl.setText(_('{name} – firmware {ver} ({build})').format(name=info.name, ver=info.version,
                                                                          build=info.build))
        self._load_light_ui()
        self._refresh_kbd()
        self._ensure_first_backup()
        return True

    def _ensure_first_backup(self):
        """Before the app ever writes to this keyboard, keep one untouched copy of its settings."""
        if glob.glob(os.path.join(BACKUP_DIR, 'original_*.json')):
            return
        path = os.path.join(BACKUP_DIR, time.strftime('original_%Y%m%d_%H%M%S.json'))
        full_backup(self.dev, path)
        self.status(_('Původní nastavení klávesnice zálohováno: {path}').format(path=path))

    # ------------------------------------------------------------------ lighting
    def _build_light(self):
        w = QFrame(objectName='panel')
        g = QGridLayout(w)
        self.info_lbl = QLabel('', objectName='hint')
        g.addWidget(self.info_lbl, 0, 0, 1, 3)
        g.addWidget(QLabel(_('Efekt')), 1, 0)
        self.effect_cb = QComboBox()
        for val, name in L.EFFECTS:
            self.effect_cb.addItem(name, val)
        self.effect_cb.currentIndexChanged.connect(self._light_changed)
        g.addWidget(self.effect_cb, 1, 1)
        g.addWidget(QLabel(_('Jas')), 2, 0)
        self.bright = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=4, pageStep=1)
        self.bright.valueChanged.connect(self._light_changed)
        g.addWidget(self.bright, 2, 1)
        self.speed_lbl = QLabel(_('Rychlost'))
        g.addWidget(self.speed_lbl, 3, 0)
        self.speed = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=4, pageStep=1)
        self.speed.valueChanged.connect(self._light_changed)
        g.addWidget(self.speed, 3, 1)
        self.rainbow = QCheckBox(_('Duhové barvy'))
        self.rainbow.toggled.connect(self._light_changed)
        g.addWidget(self.rainbow, 4, 1)
        row = QHBoxLayout()
        self.c1 = QPushButton(_('Barva'))
        self.c1.clicked.connect(lambda: self._pick(3))
        self.c2 = QPushButton(_('Druhá barva'))
        self.c2.clicked.connect(lambda: self._pick(6))
        row.addWidget(self.c1)
        row.addWidget(self.c2)
        row.addStretch()
        g.addLayout(row, 1, 2)
        self.custom_hint = QLabel(_('Vlastní barvy jednotlivých kláves zůstávají tak, jak jsou uložené v klávesnici '
                                    '(úprava po klávesách přibude).'), objectName='hint', wordWrap=True)
        g.addWidget(self.custom_hint, 2, 2, 2, 1)
        nav_only(self.effect_cb)
        for wdg in (self.bright, self.speed, self.rainbow):
            wdg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(2, 1)
        g.setRowStretch(5, 1)
        return w

    def _load_light_ui(self):
        if len(self.light) < 11:
            return
        self._loading = True
        i = self.effect_cb.findData(self.light[0])
        if i < 0:
            self.effect_cb.addItem(_('Efekt {n}').format(n=self.light[0]), self.light[0])
            i = self.effect_cb.count() - 1
        self.effect_cb.setCurrentIndex(i)
        self.speed.setValue(self.light[1])
        self.bright.setValue(self.light[2])
        self.rainbow.setChecked(bool(self.light[10]))
        self._loading = False
        self._update_widgets()

    def _update_widgets(self):
        eff = self.light[0] if self.light else 0
        for wdg in (self.speed_lbl, self.speed):
            wdg.setVisible(eff not in NO_SPEED)
        for wdg in (self.c1, self.c2, self.rainbow):
            wdg.setVisible(eff not in NO_COLOR)
        self.custom_hint.setVisible(eff in NO_COLOR)
        if len(self.light) >= 9:
            for btn, off in ((self.c1, 3), (self.c2, 6)):
                r, g_, b = self.light[off:off + 3]
                btn.setStyleSheet(f'background: rgb({r},{g_},{b}); color: {"#000" if r + g_ + b > 380 else "#fff"};')

    def _light_changed(self, *_a):
        if self._loading or len(self.light) < 11:
            return
        self.light[0] = self.effect_cb.currentData()
        self.light[1] = self.speed.value()
        self.light[2] = self.bright.value()
        self.light[10] = 1 if self.rainbow.isChecked() else 0
        self._update_widgets()
        self._timer.start()

    def _pick(self, off: int):
        c = QColorDialog.getColor(QColor(*self.light[off:off + 3]), self)
        if c.isValid():
            self.light[off:off + 3] = bytes([c.red(), c.green(), c.blue()])
            self._light_changed()

    def _write_light(self):
        if not self.dev:
            return
        try:
            self.dev.write_lighting_raw(bytes(self.light))
            self.status(_('Podsvícení uloženo do klávesnice'))
        except (AulaError, OSError) as e:
            QMessageBox.warning(self, 'AULA', str(e))

    # ------------------------------------------------------------------ actuation
    def _build_act(self):
        w = QFrame(objectName='panel')
        g = QGridLayout(w)
        self.act_title = QLabel(_('Vyber klávesy na obrázku (Ctrl = přidat/odebrat, tažením více)'), objectName='title')
        g.addWidget(self.act_title, 0, 0, 1, 4)

        def spin(lo, hi, val):
            sb = QDoubleSpinBox(minimum=lo, maximum=hi, singleStep=0.01, decimals=2, value=val, suffix=' mm')
            return sb
        g.addWidget(QLabel(_('Bod sepnutí')), 1, 0)
        self.press = spin(0.01, 3.40, 1.20)
        g.addWidget(self.press, 1, 1)
        g.addWidget(QLabel(_('menší = citlivější (sepne dřív)'), objectName='hint'), 1, 2, 1, 2)
        self.rapid = QCheckBox(_('Rapid trigger (klávesa se uvolní hned při pohybu nahoru)'))
        self.rapid.toggled.connect(self._rapid_toggled)
        g.addWidget(self.rapid, 2, 0, 1, 4)
        self.rt_lbl1 = QLabel(_('Citlivost stisku'))
        g.addWidget(self.rt_lbl1, 3, 0)
        self.rt_press = spin(0.01, 2.00, 0.10)
        g.addWidget(self.rt_press, 3, 1)
        self.rt_lbl2 = QLabel(_('Citlivost uvolnění'))
        g.addWidget(self.rt_lbl2, 3, 2)
        self.rt_release = spin(0.01, 2.00, 0.10)
        g.addWidget(self.rt_release, 3, 3)
        row = QHBoxLayout()
        b = QPushButton(_('Vybrat vše'))
        b.clicked.connect(lambda: self.kbd.set_selected({k.slot for k in L.KEYS}))
        row.addWidget(b)
        self.apply_act_btn = QPushButton(_('Použít na vybrané klávesy'))
        self.apply_act_btn.clicked.connect(self._apply_act)
        row.addWidget(self.apply_act_btn)
        row.addStretch()
        g.addLayout(row, 4, 0, 1, 4)
        g.setColumnStretch(3, 1)
        g.setRowStretch(5, 1)
        self.kbd.selectionChanged.connect(self._act_selection)
        self._rapid_toggled(False)
        return w

    def _rapid_toggled(self, on: bool):
        for wdg in (self.rt_lbl1, self.rt_press, self.rt_lbl2, self.rt_release):
            wdg.setEnabled(on)

    def _act_selection(self):
        if self.tabs.currentIndex() != 1:
            return
        sel = sorted(self.kbd.selected)
        self.apply_act_btn.setEnabled(bool(sel) and self.dev is not None)
        if not sel:
            self.act_title.setText(_('Vyber klávesy na obrázku (Ctrl = přidat/odebrat, tažením více)'))
            return
        self.act_title.setText(_('Vybráno kláves: {n}').format(n=len(sel)))
        cur = self.act.get(sel[0])
        if cur:
            rapid, p, _r, rp, rr = cur
            self.press.setValue(p)
            self.rapid.setChecked(rapid)
            self.rt_press.setValue(rp)
            self.rt_release.setValue(rr)

    def _apply_act(self):
        sel = sorted(self.kbd.selected)
        if not sel or not self.dev:
            return
        p = self.press.value()
        try:
            self.dev.write_actuation(sel, self.rapid.isChecked(), p, p, self.rt_press.value(), self.rt_release.value())
        except (AulaError, OSError) as e:
            QMessageBox.warning(self, 'AULA', str(e))
        for idx in sel:
            self.act[idx] = Aula.decode_actuation(self.dev.read_key_block(idx))
        self._refresh_kbd()
        self.status(_('Spínače uloženy do klávesnice ({n} kláves)').format(n=len(sel)))

    def _refresh_kbd(self):
        self.kbd.colors, self.kbd.labels, self.kbd.marked = {}, {}, set()
        self.kbd.multi = self.tabs.currentIndex() == 1
        if self.tabs.currentIndex() == 1:
            for k in L.KEYS:
                cur = self.act.get(k.slot)
                if cur:
                    self.kbd.labels[k.slot] = f'{k.label}\n{cur[1]:.2f}' + (' RT' if cur[0] else '')
        else:
            self.kbd.set_selected(set())
        self.kbd.update()

    # ------------------------------------------------------------------ backup
    def _build_backup(self):
        w = QFrame(objectName='panel')
        v = QVBoxLayout(w)
        v.addWidget(QLabel(_('Záloha a obnova'), objectName='title'))
        v.addWidget(QLabel(_('Při prvním připojení aplikace sama uloží původní nastavení klávesnice. „Vrátit '
                             'nastavení ze zálohy“ zapíše zpět podsvícení, barvy kláves a spínače (bod sepnutí, '
                             'rapid trigger); ostatní nastavení (SOCD…) aplikace nemění.'),
                           objectName='hint', wordWrap=True))
        row = QHBoxLayout()
        b = QPushButton(_('Zálohovat teď'))
        b.clicked.connect(self._backup_now)
        row.addWidget(b)
        b = QPushButton(_('Vrátit nastavení ze zálohy…'))
        b.clicked.connect(self._restore)
        row.addWidget(b)
        row.addStretch()
        v.addLayout(row)
        self.backup_lbl = QLabel(_('Zálohy: {dir}').format(dir=BACKUP_DIR), objectName='hint', wordWrap=True)
        self.backup_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.backup_lbl)
        v.addStretch()
        return w

    def _backup_now(self):
        if not self.dev:
            return
        path = os.path.join(BACKUP_DIR, time.strftime('aula_%Y%m%d_%H%M%S.json'))
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            full_backup(self.dev, path)
        finally:
            self.unsetCursor()
        self.status(_('Záloha uložena: {path}').format(path=path))

    def _restore(self):
        if not self.dev:
            return
        originals = sorted(glob.glob(os.path.join(BACKUP_DIR, 'original_*.json')))
        start = originals[0] if originals else BACKUP_DIR
        path, _f = QFileDialog.getOpenFileName(self, _('Vyberte zálohu'), start, 'JSON (*.json)')
        if not path:
            return
        try:
            done = restore(self.dev, path)
        except (AulaError, OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, 'AULA', str(e))
            return
        self.light = bytearray(self.dev.read_lighting_raw())
        self._load_light_ui()
        QMessageBox.information(self, 'AULA', _('Obnoveno: {what}').format(what=', '.join(done)) if done
                                else _('Klávesnice už odpovídá záloze – nebylo co měnit.'))
