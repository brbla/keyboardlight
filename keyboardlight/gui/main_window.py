"""Main window – layout inspired by the vendor app: navigation left, keyboard on top, settings panel below."""
from __future__ import annotations

import colorsys
import json
import os
import random
import time

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QMainWindow, QMessageBox, QDialog, QDialogButtonBox, QLineEdit, QPushButton, QRadioButton, QSlider, QSpinBox, QStackedWidget,
                             QVBoxLayout, QWidget)

from keyboardlight.devices.odyssey import BACKUP_DIR, Lighting, Odyssey, OdysseyError
from keyboardlight.devices.odyssey_layout import (CONSUMER, DISABLED_ENTRY, EFFECT_CUSTOM, EFFECTS, EVDEV_MODIFIER,
                                                  EVDEV_TO_HID, FN_SLOT, HID_NAMES, KEY_BY_SLOT, KEYS, MODIFIERS,
                                                  PRESET_COLORS, consumer_entry, describe, keyboard_entry)
from keyboardlight import aula_profiles, battery, firmware, i18n, kde_shortcuts, profiles
from keyboardlight.devices import odyssey_macros
from keyboardlight.devices.odyssey_layout import (DIRECTION_LABELS, EFFECT_OFF, FIXED_COLORS, NO_SPEED,
                                                  WITH_DIRECTION, macro_entry)
from keyboardlight.devices.odyssey_macros import MODES
from keyboardlight.gui.keyboard_widget import KeyboardWidget
from keyboardlight.gui.macro_page import MacroPage
from keyboardlight.gui.aula_page import AulaPage
from keyboardlight.gui.widgets import nav_only, stepped
from keyboardlight.devices import aula as aula_dev
from keyboardlight.devices import detect
from keyboardlight.i18n import _

STYLE = """
QMainWindow, QDialog { background: #0f2326; }
QWidget { background: transparent; color: #e6f2f2; font-size: 13px; }
QComboBox QAbstractItemView { background: #163236; selection-background-color: #18d6d6; selection-color: #0f2326; }
QStatusBar { background: #0f2326; }
QFrame#side { background: #1d3c40; border-radius: 6px; }
QFrame#panel { background: #23474b; border-radius: 6px; }
QPushButton { background: #163236; border: 1px solid #2f5a5f; border-radius: 4px; padding: 6px 10px; }
QPushButton:hover { border-color: #18d6d6; }
QPushButton:disabled { color: #6b8588; }
QPushButton#nav { text-align: left; border: none; padding: 10px 14px; font-size: 14px; background: transparent; }
QPushButton#nav:checked { background: #0f2326; color: #18d6d6; }
QPushButton#swatch { border: 2px solid #0f2326; padding: 0; min-width: 26px; min-height: 26px; }
QPushButton#swatch:hover { border-color: #ffffff; }
QComboBox { background: #163236; border: 1px solid #2f5a5f; padding: 5px; }
QSlider::groove:horizontal { height: 6px; background: #163236; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #18d6d6; border-radius: 3px; }
QSlider::handle:horizontal { background: #e6f2f2; width: 14px; margin: -5px 0; border-radius: 7px; }
QLabel#title { font-size: 15px; font-weight: bold; }
QLabel#hint { color: #9fb8ba; }
"""


def swatch(color: str, cb) -> QPushButton:
    b = QPushButton()
    b.setObjectName('swatch')
    b.setStyleSheet(f'background: {color};')
    b.setToolTip(color)
    b.clicked.connect(lambda: cb(QColor(color)))
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def panel() -> QFrame:
    f = QFrame()
    f.setObjectName('panel')
    return f


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('KeyBoardLight – Yenkee Odyssey')
        self.setStyleSheet(STYLE)
        self.resize(1100, 720)
        self.dev: Odyssey | None = None
        self.light: Lighting | None = None
        self.key_colors: list[tuple[int, int, int]] = [(0, 0, 0)] * 128
        self.colors_dirty = False
        self.keymap_default: list[bytes] = []
        self.keymap: list[bytes] = []
        self._loading = False
        self._write_timer = QTimer(self, singleShot=True, interval=400, timeout=self._write_lighting)
        self._colors_timer = QTimer(self, singleShot=True, interval=700, timeout=self._save_colors)
        # follow changes made on the keyboard itself (Fn+Home, Fn+arrows, Fn+Space) – read-only, ~10 ms
        self._poll_timer = QTimer(self, interval=2000, timeout=self._poll_lighting)
        self._poll_timer.start()

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)

        # ---- sidebar
        side = QFrame(objectName='side')
        side.setFixedWidth(200)
        sl = QVBoxLayout(side)
        self.device_cb = QComboBox()
        self.device_cb.addItem('Yenkee Odyssey', 'odyssey')
        self.device_cb.addItem('AULA WIN68 HE', 'aula')
        self.device_cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sl.addWidget(self.device_cb)
        self.dev_label = QLabel('Odyssey', objectName='title', wordWrap=True)
        sl.addWidget(self.dev_label)
        self.battery_label = QLabel('', objectName='hint', wordWrap=True)
        sl.addWidget(self.battery_label)
        self._battery_timer = QTimer(self, interval=60000, timeout=self._update_battery)
        self._battery_timer.start()
        sl.addSpacing(10)
        self.nav = QButtonGroup(self)
        self.pages = QStackedWidget()
        # button ids stay 0..4 (pages); the AULA settings button (id 4) is shown first in the menu
        for i, name in [(4, _('🎛  Nastavení')), (0, _('💡  Podsvícení')), (1, _('⌨  Klávesy')), (2, _('⏺  Makra')),
                        (3, _('⚙  Další'))]:
            b = QPushButton(name, objectName='nav', checkable=True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.nav.addButton(b, i)
            sl.addWidget(b)
        sl.addStretch()
        self.profiles_title = QLabel(_('Profily'), objectName='title')
        sl.addWidget(self.profiles_title)
        self.profile_cb = QComboBox()
        sl.addWidget(self.profile_cb)
        prow = QHBoxLayout()
        self.profile_load_btn = QPushButton(_('Načíst'))
        self.profile_load_btn.clicked.connect(self._load_profile)
        prow.addWidget(self.profile_load_btn)
        self.profile_save_btn = QPushButton(_('Uložit…'))
        self.profile_save_btn.clicked.connect(self._save_profile)
        prow.addWidget(self.profile_save_btn)
        sl.addLayout(prow)
        self.profile_del_btn = QPushButton(_('Smazat profil'))
        self.profile_del_btn.clicked.connect(self._delete_profile)
        sl.addWidget(self.profile_del_btn)
        self.profiles = profiles.load_all()
        self._refresh_profiles()
        sl.addSpacing(16)
        self.reconnect_btn = QPushButton(_('Znovu připojit'))
        self.reconnect_btn.clicked.connect(lambda: self._set_device(self.device_cb.currentData()))
        sl.addWidget(self.reconnect_btn)
        lay.addWidget(side)

        # ---- content: Odyssey pages (with its keyboard picture) or the AULA page
        self.content_stack = QStackedWidget()
        ody = QWidget()
        content = QVBoxLayout(ody)
        content.setContentsMargins(0, 0, 0, 0)
        self.kbd = KeyboardWidget()
        self.kbd.selectionChanged.connect(self._selection_changed)
        content.addWidget(self.kbd, 3)
        content.addWidget(self.pages, 2)
        self.content_stack.addWidget(ody)
        self.aula_page = AulaPage(lambda m: self.statusBar().showMessage(m, 5000))
        self.content_stack.addWidget(self.aula_page)
        lay.addWidget(self.content_stack, 1)

        self.pages.addWidget(self._build_lighting())
        self.pages.addWidget(self._build_keys())
        self.pages.addWidget(self._build_macros())
        self.pages.addWidget(self._build_other())
        self.nav.idClicked.connect(self._switch_page)
        self.nav.button(0).setChecked(True)
        self.device_cb.currentIndexChanged.connect(lambda _i: self._set_device(self.device_cb.currentData()))

        self.connect_device()
        # start with whichever supported keyboard is connected (Odyssey preferred), then watch hot-plugging
        self._present = detect.connected()
        self._update_device_list()
        if 'odyssey' not in self._present and 'aula' in self._present:
            self.device_cb.setCurrentIndex(1)
        else:
            self._set_device('odyssey')
        self._hotplug_timer = QTimer(self, interval=2000, timeout=self._check_hotplug)
        self._hotplug_timer.start()

    # ================================================================ device
    def connect_device(self):
        if self.dev:
            self.dev.close()
            self.dev = None
        try:
            self.dev = Odyssey()
            block = self.dev.read_config_block()
            self.light = Lighting.from_block(block)
            self._mac_mode = Odyssey.mac_mode_from_block(block)
            self.key_colors = self.dev.read_key_colors()
            self.keymap_default, self.keymap = self.dev.read_keymaps()
            info = self.dev.info()
        except OdysseyError as e:
            if self.dev:
                self.dev.close()
            self.dev = None
            self.dev_label.setText(_('Odyssey\n– nepřipojeno –'))
            self._set_enabled(False)
            if battery.bluetooth_battery() is not None:
                self.dev_label.setText(_('Yenkee Odyssey\npřes Bluetooth'))
                self.statusBar().showMessage(_('Přes Bluetooth nastavení měnit nejde – připojte klávesnici kabelem '
                                               'nebo přes USB přijímač (přepínač 2.4G). Uložené nastavení platí dál.'))
            else:
                self.statusBar().showMessage(str(e))
            self._update_battery()
            return
        self.dev_label.setText('Yenkee Odyssey\n' + (_('bezdrátově (2,4 GHz)') if self.dev.wireless else _('kabelem (USB)')))
        self.info_label.setText(_('Zařízení: {path}').format(path=self.dev.path) + f'\nInfo (0x03): {info.hex(" ")}\n'
                                + _('Zálohy před zápisy: {dir}').format(dir=BACKUP_DIR))
        self.colors_dirty = False
        self._set_enabled(True)
        self._load_lighting_ui()
        self._load_mode_ui(self._mac_mode)
        self._refresh_keyboard()
        self.statusBar().showMessage(_('Připojeno – nastavení načteno z klávesnice'), 4000)
        self._update_battery()

    def _poll_lighting(self):
        if (not self.dev or not self.light or self._aula_mode() or self._loading or self._write_timer.isActive()
                or not self.isVisible()):
            return
        try:
            block = self.dev.read_config_block()
        except (OdysseyError, OSError):
            return                                  # unplugged – the hot-plug check handles it
        now = Lighting.from_block(block)
        mac = Odyssey.mac_mode_from_block(block)
        if mac != getattr(self, '_mac_mode', mac) and self.mode_cb.isEnabled():
            self._mac_mode = mac
            self._load_mode_ui(mac)
            self.statusBar().showMessage(_('Na klávesnici přepnuto: {effect}').format(
                effect=self.mode_cb.currentText()), 4000)
        self._mac_mode = mac
        if now == self.light or self._write_timer.isActive():
            return
        changed_effect = now.effect != self.light.effect
        self.light = now
        self._load_lighting_ui()
        self._refresh_keyboard()
        if changed_effect:
            name = dict((e[0], e[1]) for e in EFFECTS).get(now.effect, str(now.effect))
            self.statusBar().showMessage(_('Na klávesnici přepnuto: {effect}').format(effect=name), 4000)
        else:
            self.statusBar().showMessage(_('Nastavení změněno na klávesnici – načteno'), 3000)

    def _update_battery(self):
        pct = battery.bluetooth_battery()
        self.battery_label.setText(_('Baterie: {pct} %').format(pct=pct) if pct is not None else '')
        self.battery_label.setToolTip(_('Stav baterie hlásí klávesnice jen přes Bluetooth.'))

    # ================================================================ profiles
    def _aula_mode(self) -> bool:
        return hasattr(self, 'device_cb') and self.device_cb.currentData() == 'aula'

    def _refresh_profiles(self, select: str | None = None):
        cur = select or self.profile_cb.currentData()
        self.profile_cb.clear()
        if self._aula_mode():
            for name, d in aula_profiles.load_all().items():
                self.profile_cb.addItem(aula_profiles.label(name, d), name)
            i = self.profile_cb.findData(cur)
            if i >= 0:
                self.profile_cb.setCurrentIndex(i)
            return
        for p in self.profiles:
            self.profile_cb.addItem(f'{p.name} – {p.effect_label()}', p.name)
            self.profile_cb.setItemData(self.profile_cb.count() - 1, p.summary(), Qt.ItemDataRole.ToolTipRole)
        i = self.profile_cb.findData(cur)
        if i >= 0:
            self.profile_cb.setCurrentIndex(i)

    def _save_profile(self):
        if self._aula_mode():
            dev = self.aula_page.dev
            if not dev:
                return
            from PyQt6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getText(self, _('Uložit profil'), _('Název profilu (např. Den, Noc, Hry):'),
                                            text=self.profile_cb.currentData() or _('Hry'))
            name = name.strip()
            if not ok or not name:
                return
            if name in aula_profiles.load_all() and QMessageBox.question(
                    self, _('Profil'), _('Profil „{name}“ už existuje. Přepsat?').format(name=name)) \
                    != QMessageBox.StandardButton.Yes:
                return
            self.setCursor(Qt.CursorShape.WaitCursor)
            try:
                aula_profiles.save(dev, name)
            finally:
                self.unsetCursor()
            self._refresh_profiles(name)
            self.statusBar().showMessage(_('Profil „{name}“ uložen ({what})').format(
                name=name, what=_('podsvícení, barvy kláves, spínače, SOCD')), 4000)
            return
        if not self.light:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_('Uložit profil'))
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(_('Název profilu (např. Den, Noc, Hry):')))
        name = QLineEdit(self.profile_cb.currentData() or _('Den'))
        v.addWidget(name)
        v.addWidget(QLabel(_('Uložit kromě podsvícení také:')))
        c_colors = QCheckBox(_('barvy jednotlivých kláves'), checked=True)
        # per-key colours only matter for the custom-colours effect
        c_colors.setVisible(self.light.effect == EFFECT_CUSTOM)
        c_colors.setChecked(self.light.effect == EFFECT_CUSTOM)
        c_keys = QCheckBox(_('mapu kláves a makra'), checked=False)
        v.addWidget(c_colors)
        v.addWidget(c_keys)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted or not name.text().strip():
            return
        n = name.text().strip()
        if self.macro_page.dirty and c_keys.isChecked():
            QMessageBox.information(self, _('Profil'), _('Makra mají neuložené změny – do profilu se uloží tak, '
                                                    'jak jsou teď v editoru.'))
        p = profiles.capture(n, self.light,
                             self.key_colors if c_colors.isChecked() else None,
                             self.keymap if c_keys.isChecked() else None,
                             self.macro_page.macros if c_keys.isChecked() else None)
        existing = [i for i, q in enumerate(self.profiles) if q.name == n]
        if existing:
            if QMessageBox.question(self, _('Profil'), _('Profil „{name}“ už existuje. Přepsat?').format(name=n)) \
                    != QMessageBox.StandardButton.Yes:
                return
            self.profiles[existing[0]] = p
        else:
            self.profiles.append(p)
        profiles.save_all(self.profiles)
        self._refresh_profiles(n)
        self.statusBar().showMessage(_('Profil „{name}“ uložen ({what})').format(name=n, what=p.summary()), 4000)

    def _load_profile(self):
        if self._aula_mode():
            name, dev = self.profile_cb.currentData(), self.aula_page.dev
            if not name or not dev:
                return
            self.setCursor(Qt.CursorShape.WaitCursor)
            try:
                written = aula_profiles.apply(dev, name)
            except (aula_dev.AulaError, OSError) as e:
                QMessageBox.warning(self, 'AULA', str(e))
                return
            finally:
                self.unsetCursor()
            self.aula_page.connect_device()
            self.statusBar().showMessage(_('Profil „{name}“ načten').format(name=name) +
                                         (_(' – zapsáno: {what}').format(what=', '.join(written)) if written
                                          else _(' – beze změny')), 5000)
            return
        i = self.profile_cb.currentIndex()
        if i < 0 or not self.dev:
            return
        p = self.profiles[i]
        written = []
        if not self._guard(lambda: written.extend(profiles.apply(self.dev, p))):
            return
        if p.macros is not None:
            self.macro_page.macros[:] = profiles.profile_macros(p)
            self.macro_page.mark_saved()
            self.macro_page._reload_list(0)
            self._refresh_macro_combo()
        self.connect_device()
        self.statusBar().showMessage(_('Profil „{name}“ načten').format(name=p.name) +
                                     (_(' – zapsáno: {what}').format(what=', '.join(written)) if written
                                      else _(' – beze změny')), 5000)

    def _delete_profile(self):
        if self._aula_mode():
            name = self.profile_cb.currentData()
            if name and QMessageBox.question(self, _('Profil'), _('Smazat profil „{name}“?').format(name=name)) \
                    == QMessageBox.StandardButton.Yes:
                aula_profiles.delete(name)
                self._refresh_profiles()
            return
        i = self.profile_cb.currentIndex()
        if i < 0:
            return
        if QMessageBox.question(self, _('Profil'), _('Smazat profil „{name}“?').format(name=self.profiles[i].name)) \
                == QMessageBox.StandardButton.Yes:
            del self.profiles[i]
            profiles.save_all(self.profiles)
            self._refresh_profiles()

    def _load_mode_ui(self, mac: bool):
        self.mode_cb.blockSignals(True)
        self.mode_cb.setCurrentIndex(1 if mac else 0)
        self.mode_cb.blockSignals(False)

    def _mode_changed(self):
        mac = bool(self.mode_cb.currentData())
        if self._guard(self.dev.write_mac_mode, mac) if self.dev else False:
            self._mac_mode = mac
            self.statusBar().showMessage(_('Režim kláves uložen: {mode}').format(mode=self.mode_cb.currentText()), 3000)

    def _set_enabled(self, on: bool):
        for i in (0, 1):
            self.pages.widget(i).setEnabled(on)
        # the "More" page stays usable (language, knob shortcut); only device actions depend on the keyboard
        self.factory_colors_btn.setEnabled(on)
        self.mode_cb.setEnabled(on)

    def _guard(self, fn, *a):
        if not self.dev:
            self.statusBar().showMessage(_('Klávesnice není připojená'))
            return False
        try:
            fn(*a)
            return True
        except (OdysseyError, OSError) as e:
            QMessageBox.warning(self, _('Chyba komunikace'), str(e) + '\n\n' + _('Zkuste „Znovu připojit“.'))
            return False

    # ================================================================ pages
    _HOW = {'usb': 'kabelem (USB)', '2.4g': 'bezdrátově (2,4 GHz)', 'bt': 'přes Bluetooth'}

    def _update_device_list(self):
        model = self.device_cb.model()
        for i in range(self.device_cb.count()):
            kind = self.device_cb.itemData(i)
            name = 'Yenkee Odyssey' if kind == 'odyssey' else 'AULA WIN68 HE'
            how = self._present.get(kind)
            self.device_cb.setItemText(i, f'{name}  ●' if how else f'{name}  ○')
            self.device_cb.setItemData(i, _(self._HOW[how]) if how else _('nepřipojeno'), Qt.ItemDataRole.ToolTipRole)
            item = model.item(i)
            if item is not None:
                item.setEnabled(bool(how) or kind == self.device_cb.currentData())

    def _check_hotplug(self):
        now = detect.connected()
        if now == self._present:
            return
        before, self._present = self._present, now
        self._update_device_list()
        cur = self.device_cb.currentData()
        other = 'aula' if cur == 'odyssey' else 'odyssey'
        names = {'odyssey': 'Yenkee Odyssey', 'aula': 'AULA WIN68 HE'}
        if cur in now and before.get(cur) != now.get(cur):
            self._set_device(cur)                       # current keyboard re-plugged / changed connection
            self.statusBar().showMessage(_('{name} připojena – nastavení načteno').format(name=names[cur]), 5000)
        elif cur not in now and other in now:
            self.device_cb.setCurrentIndex(self.device_cb.findData(other))   # switch to the one that is there
            self.statusBar().showMessage(_('{name} připojena – přepnuto na ni').format(name=names[other]), 5000)
        elif cur not in now:
            self._set_device(cur)                       # shows “not connected”
            self.statusBar().showMessage(_('{name} odpojena').format(name=names[cur]), 5000)
        elif other in now and other not in before:
            self.statusBar().showMessage(_('Připojena i {name} – přepnete vlevo nahoře').format(name=names[other]),
                                         8000)

    def _set_device(self, kind: str):
        aula = kind == 'aula'
        for i in (0, 1, 2):
            self.nav.button(i).setVisible(not aula)
        self.nav.button(4).setVisible(aula)
        self.battery_label.setVisible(not aula)
        self._refresh_profiles()
        if hasattr(self, '_present'):
            self._update_device_list()
        if aula:
            ok = self.aula_page.connect_device()
            if ok:
                self.statusBar().showMessage(_('Připojeno – nastavení načteno z klávesnice'), 4000)
            self.dev_label.setText('AULA WIN68 HE\n' + (_('kabelem (USB)') if ok else _('– nepřipojeno –')))
            self.nav.button(4).setChecked(True)
            self._switch_page(4)
        else:
            self.connect_device()
            self.nav.button(0).setChecked(True)
            self._switch_page(0)

    def _switch_page(self, i):
        if i == 4:
            self.content_stack.setCurrentIndex(1)
            return
        self.content_stack.setCurrentIndex(0)
        self.kbd.setVisible(i != 3 or self.device_cb.currentData() == 'odyssey')
        self.pages.setCurrentIndex(i)
        self.kbd.multi = (i == 0)
        self.kbd.set_selected(set())
        self._refresh_keyboard()

    def _selection_changed(self):
        if self.pages.currentIndex() == 1:
            self._load_key_ui()
        else:
            n = len(self.kbd.selected)
            self.sel_label.setText(_('Vybráno kláves: {n}').format(n=n) if n else
                                   _('Klikni na klávesy (Ctrl = přidat/odebrat, tažením malování)'))
            self._sync_intensity_slider()

    def _animating(self) -> bool:
        return (hasattr(self, 'animate') and self.animate.isChecked() and self.pages.currentIndex() == 0
                and bool(self.light) and self.light.effect != EFFECT_CUSTOM and not self._aula_mode())

    def _anim_tick(self):
        if not self._animating():
            self._anim_timer.stop()
            return
        from keyboardlight.gui.effect_preview import REACTIVE, frame
        t = time.monotonic() - self._anim_t0
        if self.light.effect in REACTIVE and time.monotonic() - self._last_real_press > 2.5:
            if not self._presses or t - self._presses[-1][1] > 0.9:     # demo presses when nobody types
                self._presses.append((random.choice(KEYS).slot, t))
        self._presses = [p for p in self._presses if t - p[1] < 6][-20:]
        self.kbd.colors = frame(self.light, t, self._presses)
        self.kbd.update()

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if obj is getattr(self, 'try_edit', None) and ev.type() == QEvent.Type.KeyPress:
            text = (ev.text() or '').upper()
            k = next((k for k in KEYS if k.label.upper() == text and text.strip()), None)
            if k is None and ev.key() == Qt.Key.Key_Space:
                k = max(KEYS, key=lambda k: k.w)
            if k is None:
                k = random.choice(KEYS)
            self._last_real_press = time.monotonic()
            self._presses.append((k.slot, time.monotonic() - self._anim_t0))
        return super().eventFilter(obj, ev)

    def _refresh_keyboard(self):
        page = self.pages.currentIndex()
        self.kbd.colors, self.kbd.labels, self.kbd.marked = {}, {}, set()
        if self._animating():
            if not self._anim_timer.isActive():
                self._anim_timer.start()
            self._anim_tick()
            return
        if hasattr(self, '_anim_timer'):
            self._anim_timer.stop()
        if page == 0 and self.light:
            if self.light.effect == EFFECT_CUSTOM:
                self.kbd.colors = {k.slot: QColor(*self.key_colors[k.slot]) for k in KEYS
                                   if any(self.key_colors[k.slot])}
            elif self.light.effect != 20 and self.light.brightness > 0:
                for k in KEYS:
                    if self.light.effect == 17:                     # transition reaction: white
                        self.kbd.colors[k.slot] = QColor(235, 235, 235)
                    elif self.light.rainbow or self.light.effect in FIXED_COLORS:
                        r, g, b = colorsys.hsv_to_rgb(k.x / 16.5, 1, 1)
                        self.kbd.colors[k.slot] = QColor(int(r * 255), int(g * 255), int(b * 255))
                    else:
                        self.kbd.colors[k.slot] = QColor(*self.light.color)
        elif page == 1 and self.keymap:
            for k in KEYS:
                if self.keymap[k.slot] != self.keymap_default[k.slot]:
                    self.kbd.marked.add(k.slot)
                    self.kbd.labels[k.slot] = describe(self.keymap[k.slot])
        self.kbd.update()

    # ---------------------------------------------------------- lighting page
    def _build_lighting(self):
        w = panel()
        g = QGridLayout(w)
        g.addWidget(QLabel(_('Efekt')), 0, 0)
        self.effect_cb = QComboBox()
        for val, name, note in EFFECTS:
            self.effect_cb.addItem(name + (f'  ({note})' if note else ''), val)
        self.effect_cb.currentIndexChanged.connect(self._lighting_changed)
        g.addWidget(self.effect_cb, 0, 1)

        g.addWidget(QLabel(_('Jas')), 1, 0)
        jas = QHBoxLayout()
        self.bright = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=4, pageStep=1)
        self.bright.setToolTip(_('jas celé klávesnice (0 = zhasnuto)'))
        self.bright.valueChanged.connect(self._lighting_changed)
        self.bright_box = stepped(self.bright, [_('zhasnuto'), _('max')])
        jas.addWidget(self.bright_box, 1)
        self.intensity = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=100, value=100)
        self.intensity.setToolTip(_('jas vybraných kláves nebo celé klávesnice – každá klávesa může mít jiný'))
        self.intensity.valueChanged.connect(self._intensity_changed)
        jas.addWidget(self.intensity, 1)
        self.intensity_lbl = QLabel('100 %')
        self.intensity_lbl.setFixedWidth(42)
        jas.addWidget(self.intensity_lbl)
        self.int_sel = QRadioButton(_('vybrané klávesy'), checked=True)
        self.int_all = QRadioButton(_('celá klávesnice'))
        grp = QButtonGroup(self)
        grp.addButton(self.int_sel)
        grp.addButton(self.int_all)
        self.int_all.toggled.connect(lambda _unused: self._sync_intensity_slider())
        jas.addWidget(self.int_sel)
        jas.addWidget(self.int_all)
        g.addLayout(jas, 1, 1)

        self.speed_lbl = QLabel(_('Rychlost'))
        g.addWidget(self.speed_lbl, 2, 0)
        self.speed = QSlider(Qt.Orientation.Horizontal, minimum=0, maximum=4, pageStep=1)
        self.speed.setToolTip(_('vlevo pomalu, vpravo rychle'))
        self.speed.valueChanged.connect(self._lighting_changed)
        self.speed_box = stepped(self.speed, [_('pomalu'), _('rychle')])
        g.addWidget(self.speed_box, 2, 1)

        dirs = QHBoxLayout()
        self.dir_lr = QRadioButton(_('Zleva doprava'))
        self.dir_rl = QRadioButton(_('Zprava doleva'))
        for b in (self.dir_lr, self.dir_rl):
            b.toggled.connect(self._lighting_changed)
            dirs.addWidget(b)
        self.rainbow = QCheckBox(_('Duhové barvy'))
        self.rainbow.toggled.connect(self._lighting_changed)
        dirs.addWidget(self.rainbow)
        g.addLayout(dirs, 3, 0, 1, 2)

        # colours
        self.color_panel = QFrame()
        colbox = QVBoxLayout(self.color_panel)
        colbox.setContentsMargins(0, 0, 0, 0)
        sw = QGridLayout()
        for i, c in enumerate(PRESET_COLORS):
            sw.addWidget(swatch(c, self._pick_color), i // 7, i % 7)
        colbox.addLayout(sw)
        row = QHBoxLayout()
        more = QPushButton(_('Jiná barva…'))
        more.clicked.connect(lambda: self._pick_color(QColorDialog.getColor(self._current_color(), self)))
        row.addWidget(more)
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(60, 26)
        row.addWidget(self.color_preview)
        colbox.addLayout(row)
        g.addWidget(self.color_panel, 0, 2, 4, 1)
        self.fixed_hint = QLabel(_('Tento efekt má vlastní pevné barvy – volba barvy ani duhy na něj nemá vliv.'),
                                 objectName='hint', wordWrap=True)
        g.addWidget(self.fixed_hint, 0, 2, 4, 1)

        # keyboard input must not change these controls while the user tries an effect on the keyboard
        nav_only(self.effect_cb)
        for wdg in (self.bright, self.speed, self.intensity, self.dir_lr, self.dir_rl,
                    self.rainbow, self.int_sel, self.int_all):
            wdg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.try_edit = QLineEdit(placeholderText=_('Vyzkoušejte efekt – pište sem (klávesnice reaguje na stisky)'))
        self.try_edit.setToolTip(_('Reaktivní efekty (Vlnky, Reakce na stisk…) reagují na skutečné stisky kláves. '
                                   'Pište sem – nic se tím nepřepne.'))
        g.addWidget(self.try_edit, 5, 0, 1, 3)
        self.stuck_hint = QLabel(_('Efekt nedělá, co má (např. zůstává tmavý)? Klávesnici odpojte a znovu připojte – '
                                   'kabel vytáhněte a zasuňte, u přijímače přepněte přepínač na OFF a zpět. '
                                   'Nastavení zůstane uložené.'), objectName='hint', wordWrap=True)
        g.addWidget(self.stuck_hint, 6, 0, 1, 3)
        self.show_all = QCheckBox(_('Zobrazit všechny volby (i ty, které u tohoto efektu podle testu nic nedělají)'))
        self.show_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.show_all.toggled.connect(self._update_lighting_widgets)
        g.addWidget(self.show_all, 7, 0, 1, 3)
        self.animate = QCheckBox(_('Animovaný náhled efektu (přibližná simulace)'), checked=True)
        self.animate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.animate.toggled.connect(self._refresh_keyboard)
        g.addWidget(self.animate, 8, 0, 1, 3)
        self._anim_t0 = time.monotonic()
        self._presses: list[tuple[int, float]] = []
        self._last_real_press = 0.0
        self._anim_timer = QTimer(self, interval=50, timeout=self._anim_tick)
        self.try_edit.installEventFilter(self)

        # per-key section
        self.custom_box = QFrame()
        cb = QHBoxLayout(self.custom_box)
        cb.setContentsMargins(0, 0, 0, 0)
        self.sel_label = QLabel(_('Klikni na klávesy (Ctrl = přidat/odebrat, tažením malování)'), objectName='hint')
        cb.addWidget(self.sel_label, 1)
        for text, fn in [(_('Vybrat vše'), lambda: self.kbd.set_selected({k.slot for k in KEYS})),
                         (_('Zhasnout vybrané'), lambda: self._paint_selected(QColor(0, 0, 0))),
                         (_('Zhasnout vše'), self._clear_all_colors),
                         (_('Vrátit'), self._reload_colors)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            cb.addWidget(b)
        self.save_colors_btn = QPushButton(_('Uloženo v klávesnici ✓'))
        self.save_colors_btn.setToolTip(_('změny barev kláves se ukládají automaticky; kliknutím uložíš hned'))
        self.save_colors_btn.clicked.connect(self._save_colors)
        cb.addWidget(self.save_colors_btn)
        g.addWidget(self.custom_box, 4, 0, 1, 3)
        g.setColumnStretch(1, 1)
        g.setRowStretch(9, 1)
        return w

    def _load_lighting_ui(self):
        if not self.light:
            return
        self._loading = True
        idx = self.effect_cb.findData(self.light.effect)
        if idx < 0:
            self.effect_cb.addItem(f'Efekt {self.light.effect}', self.light.effect)
            idx = self.effect_cb.count() - 1
        self.effect_cb.setCurrentIndex(idx)
        self.bright.setValue(self.light.brightness)
        self.speed.setValue(4 - self.light.speed)
        (self.dir_rl if self.light.direction else self.dir_lr).setChecked(True)
        self.rainbow.setChecked(self.light.rainbow)
        self._loading = False
        self._update_lighting_widgets()

    def _update_lighting_widgets(self):
        custom = bool(self.light and self.light.effect == EFFECT_CUSTOM)
        eff = self.light.effect if self.light else 6
        off = eff == EFFECT_OFF
        self.custom_box.setVisible(custom)
        # show only controls that do something for the current effect
        every = self.show_all.isChecked() and not custom and not off
        for wdg in (self.speed_lbl, self.speed_box):
            wdg.setVisible(eff not in NO_SPEED or every)
        for wdg in (self.dir_lr, self.dir_rl):
            wdg.setVisible(eff in WITH_DIRECTION or every)
        first, second = DIRECTION_LABELS.get(eff, (_('Zleva doprava'), _('Zprava doleva')))
        self.dir_lr.setText(first)
        self.dir_rl.setText(second)
        fixed = eff in FIXED_COLORS and not every
        self.rainbow.setVisible(not custom and not off and not fixed)
        self.color_panel.setVisible(not off and not fixed)
        self.fixed_hint.setText(_('Tento efekt je vždy duhový – barvu ani duhu nastavit nejde.') if eff == 18 else
                                _('Tento efekt svítí celou klávesnicí bíle – barvu, duhu, rychlost ani směr '
                                  'nastavit nejde (na psaní viditelně nereaguje).') if eff == 17 else
                                _('Tento efekt má vlastní pevné barvy – volba barvy ani duhy na něj nemá vliv.'))
        self.fixed_hint.setVisible(fixed)
        self.color_preview.setVisible(not custom)
        # one "Jas" control: hardware brightness for effects, per-key intensity for custom colours
        self.bright_box.setVisible(not custom and not off)
        for wdg in (self.intensity, self.intensity_lbl, self.int_sel, self.int_all):
            wdg.setVisible(custom)
        if custom:
            self._sync_intensity_slider()
        self.color_preview.setStyleSheet(f'background: {self._current_color().name()}; border: 1px solid #fff;')
        self.save_colors_btn.setText(_('Ukládám…') if self.colors_dirty else _('Uloženo v klávesnici ✓'))

    def _current_color(self) -> QColor:
        return QColor(*self.light.color) if self.light else QColor('#ffffff')

    def _lighting_changed(self):
        if self._loading or not self.light:
            return
        self.light.effect = self.effect_cb.currentData()
        self.light.brightness = self.bright.value()
        if self.light.effect == EFFECT_CUSTOM and self.light.brightness < 4:
            # custom colours: keep the shared hardware brightness at max, keys are dimmed individually
            self.light.brightness = 4
            self.bright.blockSignals(True)
            self.bright.setValue(4)
            self.bright.blockSignals(False)
        self.light.speed = 4 - self.speed.value()
        self.light.direction = 1 if self.dir_rl.isChecked() else 0
        self.light.rainbow = self.rainbow.isChecked()
        if self.light.effect == 18:          # centre transition: always rainbow, rings out / in by direction
            self.light.rainbow = True
        self._update_lighting_widgets()
        self._refresh_keyboard()
        self._write_timer.start()

    def _write_lighting(self):
        if self._guard(self.dev.write_lighting, self.light) if self.dev else False:
            self.statusBar().showMessage(_('Podsvícení uloženo do klávesnice'), 2500)

    def _pick_color(self, c: QColor):
        if not c.isValid() or not self.light:
            return
        if self.light.effect == EFFECT_CUSTOM:
            if not self.kbd.selected:
                self.statusBar().showMessage(_('Nejdřív vyber klávesy na obrázku'), 3000)
                return
            k = self.intensity.value() / 100
            self._paint_selected(QColor(int(c.red() * k), int(c.green() * k), int(c.blue() * k)))
            return
        self.light.color = (c.red(), c.green(), c.blue())
        if self.light.rainbow:
            self.rainbow.setChecked(False)      # triggers _lighting_changed
        else:
            self._lighting_changed()

    def _intensity_targets(self) -> list[int]:
        return [k.slot for k in KEYS] if self.int_all.isChecked() else list(self.kbd.selected)

    def _sync_intensity_slider(self):
        """Show the intensity of the brightest target key (without rescaling anything)."""
        lit = [max(self.key_colors[s_]) for s_ in self._intensity_targets() if any(self.key_colors[s_])]
        if lit:
            self.intensity.blockSignals(True)
            self.intensity.setValue(round(max(lit) / 255 * 100))
            self.intensity.blockSignals(False)
            self.intensity_lbl.setText(f'{self.intensity.value()} %')

    # per-key hue (colour at 100 %) so a key dimmed to 0 % keeps its colour for later
    HUES_FILE = os.path.expanduser('~/.config/keyboardlight/odyssey_key_hues.json')

    def _hue(self, slot: int):
        if not hasattr(self, '_hues'):
            try:
                self._hues = {int(k): tuple(v) for k, v in json.load(open(self.HUES_FILE)).items()}
            except (OSError, ValueError):
                self._hues = {}
        c = self.key_colors[slot]
        if any(c):
            m = max(c)
            hue = tuple(round(ch * 255 / m) for ch in c)
            if self._hues.get(slot) != hue:
                self._hues[slot] = hue
            return hue
        return self._hues.get(slot)

    def _save_hues(self):
        if hasattr(self, '_hues'):
            os.makedirs(os.path.dirname(self.HUES_FILE), exist_ok=True)
            with open(self.HUES_FILE, 'w') as f:
                json.dump({str(k): v for k, v in self._hues.items()}, f)

    def _intensity_changed(self, v: int):
        self.intensity_lbl.setText(f'{v} %')
        targets = self._intensity_targets()
        if not self.light or self.light.effect != EFFECT_CUSTOM or not targets:
            return
        changed = False
        for s_ in targets:
            c = self.key_colors[s_]
            hue = self._hue(s_)
            if hue is None:
                continue
            new = tuple(round(ch * v / 100) for ch in hue)
            if new != c:
                self.key_colors[s_] = new
                changed = True
        if changed:
            self._save_hues()
            self.colors_dirty = True
            self._colors_timer.start()
            self._update_lighting_widgets()
            self._refresh_keyboard()

    def _paint_selected(self, c: QColor):
        for s in self.kbd.selected:
            self.key_colors[s] = (c.red(), c.green(), c.blue())
            self._hue(s)                     # remember the new hue (no-op for black)
        self._save_hues()
        self.colors_dirty = True
        self._colors_timer.start()
        self._update_lighting_widgets()
        self._refresh_keyboard()

    def _clear_all_colors(self):
        self.key_colors = [(0, 0, 0)] * 128
        self.colors_dirty = True
        self._colors_timer.start()
        self._update_lighting_widgets()
        self._refresh_keyboard()

    def _reload_colors(self):
        def do():
            self.key_colors = self.dev.read_key_colors()
        if self._guard(do):
            self.colors_dirty = False
            self._update_lighting_widgets()
            self._refresh_keyboard()

    def _save_colors(self):
        if self._guard(self.dev.write_key_colors, self.key_colors) if self.dev else False:
            self.colors_dirty = False
            self._update_lighting_widgets()
            self.statusBar().showMessage(_('Barvy kláves uloženy do klávesnice'), 3000)

    # ---------------------------------------------------------- keys page
    def _build_keys(self):
        w = panel()
        g = QGridLayout(w)
        self.key_title = QLabel(_('Vyber klávesu na obrázku'), objectName='title')
        g.addWidget(self.key_title, 0, 0, 1, 3)
        self.key_info = QLabel('', objectName='hint')
        g.addWidget(self.key_info, 1, 0, 1, 3)

        g.addWidget(QLabel(_('Funkce')), 2, 0)
        self.func_cb = QComboBox()
        for t in [_('Výchozí funkce'), _('Běžná klávesa'), _('Multimediální klávesa'), _('Vypnout klávesu'), _('Makro')]:
            self.func_cb.addItem(t)
        self.func_cb.currentIndexChanged.connect(self._func_type_changed)
        g.addWidget(self.func_cb, 2, 1)

        self.std_box = QFrame()
        sb = QGridLayout(self.std_box)
        sb.setContentsMargins(0, 0, 0, 0)
        self.mod_checks = []
        for i, (m, name) in enumerate(MODIFIERS):
            c = QCheckBox(name)
            self.mod_checks.append((m, c))
            sb.addWidget(c, i // 4, i % 4)
        self.hid_cb = QComboBox()
        for u, name in sorted(HID_NAMES.items(), key=lambda kv: kv[0]):
            self.hid_cb.addItem(name, u)
        sb.addWidget(QLabel(_('+ klávesa')), 2, 0)
        sb.addWidget(self.hid_cb, 2, 1, 1, 2)
        self.capture_btn = QPushButton(_('Zachytit stiskem…'))
        self.capture_btn.setCheckable(True)
        self.capture_btn.toggled.connect(self._capture_toggled)
        sb.addWidget(self.capture_btn, 2, 3)
        g.addWidget(self.std_box, 3, 0, 1, 3)

        self.media_cb = QComboBox()
        for u, name in CONSUMER.items():
            self.media_cb.addItem(name, u)
        g.addWidget(self.media_cb, 4, 0, 1, 2)

        self.macro_box = QFrame()
        mb = QHBoxLayout(self.macro_box)
        mb.setContentsMargins(0, 0, 0, 0)
        self.macro_cb = QComboBox()
        self.macro_mode_cb = QComboBox()
        for t, mode, label in MODES:
            self.macro_mode_cb.addItem(label, (t, mode))
        self.macro_times = QSpinBox(minimum=1, maximum=255, value=1, suffix=' ×')
        self.macro_mode_cb.currentIndexChanged.connect(
            lambda: self.macro_times.setVisible(self.macro_mode_cb.currentData()[0] == 0x71))
        mb.addWidget(self.macro_cb, 1)
        mb.addWidget(self.macro_mode_cb, 2)
        mb.addWidget(self.macro_times)
        g.addWidget(self.macro_box, 4, 0, 1, 3)

        btns = QHBoxLayout()
        self.apply_key_btn = QPushButton(_('Použít na klávesu'))
        self.apply_key_btn.clicked.connect(self._apply_key)
        btns.addWidget(self.apply_key_btn)
        reset_all = QPushButton(_('Obnovit všechny klávesy na výchozí'))
        reset_all.clicked.connect(self._reset_keymap)
        btns.addWidget(reset_all)
        btns.addStretch()
        g.addLayout(btns, 5, 0, 1, 3)
        self.key_pending = QLabel('', objectName='hint')
        self.key_pending.setStyleSheet('color: #ffa000; font-weight: bold;')
        g.addWidget(self.key_pending, 6, 0, 1, 3)
        g.setColumnStretch(2, 1)
        g.setRowStretch(7, 1)
        for sig in (self.func_cb.currentIndexChanged, self.hid_cb.currentIndexChanged,
                    self.media_cb.currentIndexChanged, self.macro_cb.currentIndexChanged,
                    self.macro_mode_cb.currentIndexChanged, self.macro_times.valueChanged):
            sig.connect(self._key_edited)
        for _unused, c in self.mod_checks:
            c.toggled.connect(self._key_edited)
        self._loading_key = False
        self._func_type_changed()
        return w

    def _key_edited(self, *_args):
        if self._loading_key or not self.kbd.selected:
            return
        self.key_pending.setText(_('Změna ještě není v klávesnici → klikni „Použít na klávesu“'))
        self.apply_key_btn.setStyleSheet('background: #18d6d6; color: #0f2326; font-weight: bold;')

    def _key_clean(self):
        self.key_pending.setText('')
        self.apply_key_btn.setStyleSheet('')

    def _capture_toggled(self, on: bool):
        self.capture_btn.setText(_('Stiskni klávesu…') if on else _('Zachytit stiskem…'))
        if on:
            self.grabKeyboard()
        else:
            self.releaseKeyboard()

    def _func_type_changed(self):
        t = self.func_cb.currentIndex()
        self.std_box.setVisible(t == 1)
        self.media_cb.setVisible(t == 2)
        self.macro_box.setVisible(t == 4)
        self.macro_times.setVisible(t == 4 and self.macro_mode_cb.currentData()[0] == 0x71)

    def _load_key_ui(self):
        self._loading_key = True
        try:
            self._load_key_ui_inner()
        finally:
            self._loading_key = False
            self._key_clean()

    def _load_key_ui_inner(self):
        sel = next(iter(self.kbd.selected), None)
        enabled = sel is not None and sel != FN_SLOT and bool(self.keymap)
        for wdg in (self.func_cb, self.std_box, self.media_cb, self.macro_box, self.apply_key_btn):
            wdg.setEnabled(enabled)
        if sel is None:
            self.key_title.setText(_('Vyber klávesu na obrázku'))
            self.key_info.setText('')
            return
        k = KEY_BY_SLOT[sel]
        self.key_title.setText(_('Klávesa: {key}   (pozice {slot})').format(key=k.label or _('Mezerník'), slot=sel))
        if sel == FN_SLOT:
            self.key_info.setText(_('Klávesu Fn nelze přemapovat (ovládá zkratky klávesnice).'))
            return
        cur, dflt = self.keymap[sel], self.keymap_default[sel]
        self.key_info.setText(_('Výchozí: {d}      Aktuálně: {c}').format(d=describe(dflt), c=describe(cur)))
        if cur == dflt:
            self.func_cb.setCurrentIndex(0)
        elif cur == DISABLED_ENTRY:
            self.func_cb.setCurrentIndex(3)
        elif cur[0] == 0x30:
            self.func_cb.setCurrentIndex(2)
            i = self.media_cb.findData(cur[1] | cur[2] << 8)
            if i >= 0:
                self.media_cb.setCurrentIndex(i)
        elif cur[0] in (0x70, 0x71):
            self.func_cb.setCurrentIndex(4)
            if cur[1] < self.macro_cb.count():
                self.macro_cb.setCurrentIndex(cur[1])
            for i in range(self.macro_mode_cb.count()):
                t, mode = self.macro_mode_cb.itemData(i)
                if t == cur[0] and (mode is None or mode == cur[2]):
                    self.macro_mode_cb.setCurrentIndex(i)
            if cur[0] == 0x71:
                self.macro_times.setValue(cur[2])
        elif cur[0] == 0x20:
            self.func_cb.setCurrentIndex(1)
            for m, c in self.mod_checks:
                c.setChecked(bool(cur[1] & m))
            i = self.hid_cb.findData(cur[2])
            if i >= 0:
                self.hid_cb.setCurrentIndex(i)

    def keyPressEvent(self, e):
        if self.pages.currentIndex() == 1 and self.capture_btn.isChecked():
            code = e.nativeScanCode() - 8
            if code in EVDEV_MODIFIER:
                return          # wait for the non-modifier key
            usage = EVDEV_TO_HID.get(code)
            if usage is None:
                self.statusBar().showMessage(_('Neznámá klávesa (evdev {code})').format(code=code), 3000)
                return
            mods = 0
            qm = e.modifiers()
            for flag, m in ((Qt.KeyboardModifier.ControlModifier, 0x01), (Qt.KeyboardModifier.ShiftModifier, 0x02),
                            (Qt.KeyboardModifier.AltModifier, 0x04), (Qt.KeyboardModifier.MetaModifier, 0x08)):
                if qm & flag:
                    mods |= m
            for m, c in self.mod_checks:
                c.setChecked(bool(mods & m))
            self.hid_cb.setCurrentIndex(self.hid_cb.findData(usage))
            self.capture_btn.setChecked(False)
            return
        super().keyPressEvent(e)

    def _apply_key(self):
        sel = next(iter(self.kbd.selected), None)
        if sel is None or sel == FN_SLOT:
            return
        t = self.func_cb.currentIndex()
        if t == 0:
            entry = self.keymap_default[sel]
        elif t == 1:
            mods = sum(m for m, c in self.mod_checks if c.isChecked())
            entry = keyboard_entry(self.hid_cb.currentData(), mods)
        elif t == 2:
            entry = consumer_entry(self.media_cb.currentData())
        elif t == 4:
            if self.macro_cb.currentIndex() < 0:
                QMessageBox.information(self, _('Makro'), _('Nejdřív vytvoř makro na stránce Makra.'))
                return
            if self.macro_page.dirty:
                QMessageBox.information(self, _('Makro'), _('Makra mají neuložené změny – nejdřív je ulož do klávesnice '
                                                       '(stránka Makra), jinak by klávesa spouštěla starou verzi.'))
            kind, mode = self.macro_mode_cb.currentData()
            entry = macro_entry(self.macro_cb.currentIndex(), mode or 0,
                                self.macro_times.value() if kind == 0x71 else None)
        else:
            entry = DISABLED_ENTRY
        new = list(self.keymap)
        new[sel] = entry
        if self._guard(self.dev.write_keymap, new) if self.dev else False:
            self.keymap = new
            self.statusBar().showMessage(_('Klávesa {key}: {what} – uloženo').format(key=KEY_BY_SLOT[sel].label, what=describe(entry)), 4000)
            self._refresh_keyboard()
            self._load_key_ui()

    def _reset_keymap(self):
        if QMessageBox.question(self, _('Obnovit klávesy'), _('Vrátit všechny klávesy na výchozí funkce?')) \
                != QMessageBox.StandardButton.Yes:
            return
        if self._guard(self.dev.write_keymap, list(self.keymap_default)) if self.dev else False:
            self.keymap = list(self.keymap_default)
            self._refresh_keyboard()
            self._load_key_ui()
            self.statusBar().showMessage(_('Všechny klávesy obnoveny na výchozí'), 4000)

    # ---------------------------------------------------------- macros / other
    def _build_macros(self):
        self.macro_page = MacroPage(odyssey_macros.load(), odyssey_macros.save)
        self.macro_page.macrosChanged.connect(self._refresh_macro_combo)
        self.macro_page.macroDeleted.connect(self._macro_deleted)
        self.macro_page.saveRequested.connect(self._save_macros)
        self.macro_page.loadRequested.connect(self._load_macros)
        self._refresh_macro_combo()
        return self.macro_page

    def _refresh_macro_combo(self):
        cur = self.macro_cb.currentIndex()
        self.macro_cb.clear()
        for i, m in enumerate(self.macro_page.macros):
            self.macro_cb.addItem(f'{i + 1}. {m.name}')
        if 0 <= cur < self.macro_cb.count():
            self.macro_cb.setCurrentIndex(cur)

    def _load_macros(self):
        if not self.dev:
            self.statusBar().showMessage(_('Klávesnice není připojená'))
            return
        try:
            block = self.dev.read_macro_block()
        except (OdysseyError, OSError) as e:
            QMessageBox.warning(self, _('Chyba komunikace'), str(e))
            return
        mine = self.macro_page.macros
        if block == odyssey_macros.build_block(mine):
            QMessageBox.information(self, _('Makra'), _('Makra v klávesnici jsou stejná jako v aplikaci.'))
            return
        found = odyssey_macros.parse_block(block, [m.name for m in mine])
        if not found:
            QMessageBox.information(self, _('Makra'), _('V klávesnici nejsou uložená žádná makra '
                                                         '(např. po obnovení továrního nastavení).'))
            return
        if QMessageBox.question(self, _('Makra'), _('Makra v klávesnici (počet: {n}) se liší od maker v aplikaci. '
                                                     'Nahradit jimi makra v aplikaci? (Klávesnice si nepamatuje '
                                                     'názvy maker.)').format(n=len(found))) \
                == QMessageBox.StandardButton.Yes:
            self.macro_page.replace_macros(found)
            self.statusBar().showMessage(_('Makra načtena z klávesnice: {n}').format(n=len(found)), 4000)

    def _save_macros(self, block: bytes):
        if self._guard(self.dev.write_macros, block) if self.dev else False:
            self.macro_page.mark_saved()
            self.statusBar().showMessage(_('Makra uložena do klávesnice ({n} B)').format(n=len(block)), 4000)
            if self.keymap and not any(e[0] in (0x70, 0x71) for e in self.keymap):
                QMessageBox.information(self, _('Makra uložena'),
                                        _('Makra jsou v klávesnici, ale zatím je nespouští žádná klávesa.\n\n'
                                        'Přiřaď je na stránce Klávesy: klikni na klávesu → Funkce „Makro“ → '
                                        'vyber makro a režim → „Použít na klávesu“.'))

    def _macro_deleted(self, idx: int):
        """Keys pointing to the deleted macro go back to default, higher indexes shift down."""
        if not self.keymap:
            return
        new = list(self.keymap)
        for s, e in enumerate(new):
            if e[0] in (0x70, 0x71):
                if e[1] == idx:
                    new[s] = self.keymap_default[s]
                elif e[1] > idx:
                    new[s] = bytes([e[0], e[1] - 1, e[2]])
        if new != self.keymap and (self._guard(self.dev.write_keymap, new) if self.dev else False):
            self.keymap = new
            self._refresh_keyboard()
        if self.dev:
            self._save_macros(odyssey_macros.build_block(self.macro_page.macros))

    def _build_other(self):
        w = panel()
        v = QVBoxLayout(w)
        v.addWidget(QLabel(_('Další'), objectName='title'))
        self.info_label = QLabel('', objectName='hint', wordWrap=True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.info_label)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(_('Režim kláves:')))
        self.mode_cb = nav_only(QComboBox())
        self.mode_cb.addItem(_('Windows / Linux'), False)
        self.mode_cb.addItem(_('Mac (prohozené Alt a Win)'), True)
        self.mode_cb.currentIndexChanged.connect(self._mode_changed)
        mode_row.addWidget(self.mode_cb)
        mode_row.addStretch()
        v.addLayout(mode_row)
        v.addWidget(QLabel(_('Na klávesnici: Fn + A = Windows / Linux, Fn + S = Mac (modré kontrolky 3× bliknou). '
                             'Fn + Win zamyká klávesu Win (svítí modrá kontrolka) – to se do klávesnice neukládá '
                             'a aplikace to nevidí.'), objectName='hint', wordWrap=True))
        b = self.factory_colors_btn = QPushButton(_('Tovární barvy kláves (WASD + šipky bíle)'))
        b.clicked.connect(self._factory_colors)
        v.addWidget(b, alignment=Qt.AlignmentFlag.AlignLeft)
        self.knob_btn = QPushButton()
        self.knob_btn.clicked.connect(self._toggle_knob_brightness)
        v.addWidget(self.knob_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.knob_hint = QLabel(_('Knoflík ve firmwaru vždy mění hlasitost. S tímto nastavením mění Ctrl + knoflík '
                                  'jas obrazovky (KDE Plasma).'), objectName='hint', wordWrap=True)
        v.addWidget(self.knob_hint)
        self._update_knob_btn()
        v.addWidget(QLabel(_('Klávesnice nesvítí, i když je vše nastavené (ani Fn + Del nepomáhá)? Firmware se po '
                             'přepnutí z baterie na kabel někdy zasekne: odpojte kabel, přepněte přepínač na 2.4G '
                             'a zpět na TYP-C a kabel znovu zapojte.'), objectName='hint', wordWrap=True))
        fw_row = QHBoxLayout()
        self.fw_btn = QPushButton(_('Zkontrolovat aktualizace firmwaru'))
        self.fw_btn.clicked.connect(self._check_firmware)
        fw_row.addWidget(self.fw_btn)
        self.fw_link = QPushButton(_('Otevřít oficiální stažení'))
        self.fw_link.setVisible(False)
        self.fw_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._fw_url)))
        fw_row.addWidget(self.fw_link)
        fw_row.addStretch()
        v.addLayout(fw_row)
        self.fw_label = QLabel('', objectName='hint', wordWrap=True)
        self.fw_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self.fw_label)
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel('Jazyk / Language:'))
        self.lang_cb = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_cb.addItem(name, code)
        self.lang_cb.setCurrentIndex(self.lang_cb.findData(i18n.LANG))
        self.lang_cb.currentIndexChanged.connect(self._language_changed)
        lang_row.addWidget(self.lang_cb)
        lang_row.addStretch()
        v.addLayout(lang_row)
        v.addWidget(QLabel(_('Opakování kláves při držení nastavíte v KDE: Nastavení systému → Klávesnice.'),
                           objectName='hint'))
        v.addStretch()
        return w

    def _update_knob_btn(self):
        ok = kde_shortcuts.available()
        self.knob_btn.setVisible(ok)
        self.knob_hint.setVisible(ok)
        if ok:
            on = kde_shortcuts.is_enabled()
            self.knob_btn.setText(_('Zrušit: Ctrl + knoflík = jas obrazovky') if on
                                  else _('Nastavit: Ctrl + knoflík = jas obrazovky'))

    def _toggle_knob_brightness(self):
        try:
            on = not kde_shortcuts.is_enabled()
            kde_shortcuts.set_enabled(on)
        except (RuntimeError, OSError) as e:
            QMessageBox.warning(self, 'KeyBoardLight', str(e))
            return
        self._update_knob_btn()
        self.statusBar().showMessage(_('Ctrl + knoflík teď mění jas obrazovky') if on
                                     else _('Ctrl + knoflík už jas obrazovky nemění'), 4000)

    def _check_firmware(self):
        import threading
        self.fw_btn.setEnabled(False)
        self.fw_link.setVisible(False)
        self.fw_label.setText(_('Zjišťuji verze firmwaru…'))
        self._fw_result = None

        def work():
            lines, url = [], ''
            if self.dev:
                lines.append(_('Yenkee Odyssey: výrobce firmware veřejně nenabízí – aktualizace jsou jen online '
                               'v jeho aplikaci pro Windows.'))
            try:
                from keyboardlight.devices.aula import Aula, AulaError
                a = Aula()
                try:
                    info = a.info()
                finally:
                    a.close()
                state, offer = firmware.check_aula(info)
                line = _('{name}: nainstalováno {ver}.').format(name=info.name, ver=info.version) + ' '
                if state == 'newer':
                    line += _('Výrobce nabízí novější {ver} – aktualizujte oficiálním nástrojem ve Windows '
                              '(ne přes Wine), klávesnici na kabelu a nic během aktualizace neodpojujte.').format(
                        ver=offer.version)
                    url = offer.url
                elif state == 'current':
                    line += _('Výrobce nabízí {ver} – aktualizace není potřeba.').format(ver=offer.version)
                else:
                    line += _('Výrobce pro tento model firmware nenabízí.')
                lines.append(line)
            except AulaError:
                pass
            except OSError as e:
                lines.append(_('Kontrola online se nepovedla: {err}').format(err=e))
            if not lines:
                lines.append(_('Není připojená žádná podporovaná klávesnice.'))
            self._fw_result = ('\n'.join(lines), url)

        threading.Thread(target=work, daemon=True).start()
        self._fw_timer = QTimer(self, interval=300, timeout=self._firmware_done)
        self._fw_timer.start()

    def _firmware_done(self):
        if self._fw_result is None:
            return
        self._fw_timer.stop()
        text, url = self._fw_result
        self.fw_label.setText(text)
        self._fw_url = url
        self.fw_link.setVisible(bool(url))
        self.fw_btn.setEnabled(True)

    def _language_changed(self):
        code = self.lang_cb.currentData()
        i18n.save_setting('language', code)
        QMessageBox.information(self, 'KeyBoardLight',
                                'Jazyk se změní po restartu aplikace.' if code == 'cs'
                                else 'The language will change after restarting the app.')

    def _factory_colors(self):
        cols = [(0, 0, 0)] * 128
        for s in (32, 46, 47, 48, 73, 87, 88, 89):
            cols[s] = (255, 255, 255)
        if self._guard(self.dev.write_key_colors, cols) if self.dev else False:
            self.key_colors = cols
            self.colors_dirty = False
            self._refresh_keyboard()
            self.statusBar().showMessage(_('Tovární barvy kláves obnoveny'), 3000)
