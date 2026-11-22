"""Main window – layout inspired by the vendor app: navigation left, keyboard on top, settings panel below."""
from __future__ import annotations

import colorsys
import json
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QMainWindow, QMessageBox, QDialog, QDialogButtonBox, QLineEdit, QPushButton, QRadioButton, QSlider, QSpinBox, QStackedWidget,
                             QVBoxLayout, QWidget)

from keyboardlight.devices.odyssey import BACKUP_DIR, Lighting, Odyssey, OdysseyError
from keyboardlight.devices.odyssey_layout import (CONSUMER, DISABLED_ENTRY, EFFECT_CUSTOM, EFFECTS, EVDEV_MODIFIER,
                                                  EVDEV_TO_HID, FN_SLOT, HID_NAMES, KEY_BY_SLOT, KEYS, MODIFIERS,
                                                  PRESET_COLORS, consumer_entry, describe, keyboard_entry)
from keyboardlight import battery, i18n, kde_shortcuts, profiles
from keyboardlight.devices import odyssey_macros
from keyboardlight.devices.odyssey_layout import EFFECT_OFF, NO_SPEED, WITH_DIRECTION, macro_entry
from keyboardlight.devices.odyssey_macros import MODES
from keyboardlight.gui.keyboard_widget import KeyboardWidget
from keyboardlight.gui.macro_page import MacroPage
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

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)

        # ---- sidebar
        side = QFrame(objectName='side')
        side.setFixedWidth(200)
        sl = QVBoxLayout(side)
        self.dev_label = QLabel('Odyssey', objectName='title', wordWrap=True)
        sl.addWidget(self.dev_label)
        self.battery_label = QLabel('', objectName='hint', wordWrap=True)
        sl.addWidget(self.battery_label)
        self._battery_timer = QTimer(self, interval=60000, timeout=self._update_battery)
        self._battery_timer.start()
        sl.addSpacing(10)
        self.nav = QButtonGroup(self)
        self.pages = QStackedWidget()
        for i, name in enumerate([_('💡  Podsvícení'), _('⌨  Klávesy'), _('⏺  Makra'), _('⚙  Další')]):
            b = QPushButton(name, objectName='nav', checkable=True)
            self.nav.addButton(b, i)
            sl.addWidget(b)
        sl.addStretch()
        sl.addWidget(QLabel(_('Profily'), objectName='title'))
        self.profile_cb = QComboBox()
        sl.addWidget(self.profile_cb)
        prow = QHBoxLayout()
        self.profile_load_btn = QPushButton(_('Načíst'))
        self.profile_load_btn.clicked.connect(self._load_profile)
        prow.addWidget(self.profile_load_btn)
        b = QPushButton(_('Uložit…'))
        b.clicked.connect(self._save_profile)
        prow.addWidget(b)
        sl.addLayout(prow)
        b = QPushButton(_('Smazat profil'))
        b.clicked.connect(self._delete_profile)
        sl.addWidget(b)
        self.profiles = profiles.load_all()
        self._refresh_profiles()
        sl.addSpacing(16)
        self.reconnect_btn = QPushButton(_('Znovu připojit'))
        self.reconnect_btn.clicked.connect(self.connect_device)
        sl.addWidget(self.reconnect_btn)
        lay.addWidget(side)

        # ---- content
        content = QVBoxLayout()
        self.kbd = KeyboardWidget()
        self.kbd.selectionChanged.connect(self._selection_changed)
        content.addWidget(self.kbd, 3)
        content.addWidget(self.pages, 2)
        lay.addLayout(content, 1)

        self.pages.addWidget(self._build_lighting())
        self.pages.addWidget(self._build_keys())
        self.pages.addWidget(self._build_macros())
        self.pages.addWidget(self._build_other())
        self.nav.idClicked.connect(self._switch_page)
        self.nav.button(0).setChecked(True)

        self.connect_device()

    # ================================================================ device
    def connect_device(self):
        if self.dev:
            self.dev.close()
            self.dev = None
        try:
            self.dev = Odyssey()
            self.light = self.dev.read_lighting()
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
        self._refresh_keyboard()
        self.statusBar().showMessage(_('Připojeno – nastavení načteno z klávesnice'), 4000)
        self._update_battery()

    def _update_battery(self):
        pct = battery.bluetooth_battery()
        self.battery_label.setText(_('Baterie: {pct} %').format(pct=pct) if pct is not None else '')
        self.battery_label.setToolTip(_('Stav baterie hlásí klávesnice jen přes Bluetooth.'))

    # ================================================================ profiles
    def _refresh_profiles(self, select: str | None = None):
        cur = select or self.profile_cb.currentText()
        self.profile_cb.clear()
        for p in self.profiles:
            self.profile_cb.addItem(p.name)
            self.profile_cb.setItemData(self.profile_cb.count() - 1, p.summary(), Qt.ItemDataRole.ToolTipRole)
        i = self.profile_cb.findText(cur)
        if i >= 0:
            self.profile_cb.setCurrentIndex(i)

    def _save_profile(self):
        if not self.light:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(_('Uložit profil'))
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(_('Název profilu (např. Den, Noc, Hry):')))
        name = QLineEdit(self.profile_cb.currentText() or _('Den'))
        v.addWidget(name)
        v.addWidget(QLabel(_('Uložit kromě podsvícení také:')))
        c_colors = QCheckBox(_('barvy jednotlivých kláves'), checked=True)
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
        i = self.profile_cb.currentIndex()
        if i < 0:
            return
        if QMessageBox.question(self, _('Profil'), f'Smazat profil „{self.profiles[i].name}“?') \
                == QMessageBox.StandardButton.Yes:
            del self.profiles[i]
            profiles.save_all(self.profiles)
            self._refresh_profiles()

    def _set_enabled(self, on: bool):
        for i in (0, 1, 3):
            self.pages.widget(i).setEnabled(on)

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
    def _switch_page(self, i):
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

    def _refresh_keyboard(self):
        page = self.pages.currentIndex()
        self.kbd.colors, self.kbd.labels, self.kbd.marked = {}, {}, set()
        if page == 0 and self.light:
            if self.light.effect == EFFECT_CUSTOM:
                self.kbd.colors = {k.slot: QColor(*self.key_colors[k.slot]) for k in KEYS
                                   if any(self.key_colors[k.slot])}
            elif self.light.effect != 20 and self.light.brightness > 0:
                for k in KEYS:
                    if self.light.rainbow:
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
        jas.addWidget(self.bright, 1)
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
        self.speed.setToolTip('vlevo pomalu, vpravo rychle')
        self.speed.valueChanged.connect(self._lighting_changed)
        g.addWidget(self.speed, 2, 1)

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
        g.setRowStretch(5, 1)
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
        for wdg in (self.speed_lbl, self.speed):
            wdg.setVisible(eff not in NO_SPEED)
        for wdg in (self.dir_lr, self.dir_rl):
            wdg.setVisible(eff in WITH_DIRECTION)
        self.rainbow.setVisible(not custom and not off)
        self.color_panel.setVisible(not off)
        self.color_preview.setVisible(not custom)
        # one "Jas" control: hardware brightness for effects, per-key intensity for custom colours
        self.bright.setVisible(not custom and not off)
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
        self._refresh_macro_combo()
        return self.macro_page

    def _refresh_macro_combo(self):
        cur = self.macro_cb.currentIndex()
        self.macro_cb.clear()
        for i, m in enumerate(self.macro_page.macros):
            self.macro_cb.addItem(f'{i + 1}. {m.name}')
        if 0 <= cur < self.macro_cb.count():
            self.macro_cb.setCurrentIndex(cur)

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
        b = QPushButton(_('Tovární barvy kláves (WASD + šipky bíle)'))
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
