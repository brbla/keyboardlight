"""Macro editor page: list of macros, event table, recording from the keyboard, text insertion."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)

from keyboardlight.devices.odyssey_layout import EVDEV_MODIFIER, EVDEV_TO_HID
from keyboardlight.devices.odyssey_macros import (COMMON_LAYOUTS, MAX_EVENTS, system_layout, TYPE_KEY, TYPE_MODS, TYPE_MOUSE, Macro, MacroEvent,
                                                  MOUSE_BUTTONS, build_block, text_to_events)
from keyboardlight.i18n import _


class MacroPage(QFrame):
    macrosChanged = pyqtSignal()          # names / count changed (key page combo must refresh)
    macroDeleted = pyqtSignal(int)        # index of a deleted macro
    saveRequested = pyqtSignal(bytes)     # binary block to write to the keyboard

    def __init__(self, macros: list[Macro], persist, parent=None):
        super().__init__(parent)
        self.setObjectName('panel')
        self.macros = macros
        self.persist = persist            # callable(list[Macro]) -> None
        self.dirty = False
        self._rec_last: float | None = None
        self._rec_mods = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        g = QGridLayout(self)
        # ---- left: macro list
        left = QVBoxLayout()
        left.addWidget(QLabel(_('Makra'), objectName='title'))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load_events)
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in [(_('Nové'), self._new), (_('Přejmenovat'), self._rename), (_('Smazat'), self._delete)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        left.addLayout(row)
        g.addLayout(left, 0, 0, 2, 1)

        # ---- right: events
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([_('Akce'), _('Klávesa / tlačítko'), _('Prodleva po (ms)')])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.itemChanged.connect(self._delay_edited)
        self.table.setStyleSheet('QTableWidget { background: #163236; gridline-color: #2f5a5f; }'
                                 'QHeaderView::section { background: #1d3c40; color: #e6f2f2; border: none; }')
        g.addWidget(self.table, 0, 1)

        tools = QGridLayout()
        self.rec_btn = QPushButton(_('⏺ Nahrát z klávesnice'))
        self.rec_btn.setCheckable(True)
        self.rec_btn.toggled.connect(self._record_toggled)
        tools.addWidget(self.rec_btn, 0, 0)
        self.text_edit = QLineEdit(placeholderText=_('text k napsání, např. Ahoj!'))
        tools.addWidget(self.text_edit, 0, 1, 1, 2)
        b = QPushButton(_('Vložit text'))
        b.clicked.connect(self._insert_text)
        tools.addWidget(b, 0, 3)
        self.layout_cb = QComboBox()
        sys_key = system_layout()
        self.layout_cb.addItem(_('Rozložení: {name}').format(name=sys_key.replace(':', ' – ')) + _(' (systém)'),
                               sys_key)
        for key in COMMON_LAYOUTS:
            if key != sys_key:
                self.layout_cb.addItem(_('Rozložení: {name}').format(name=key.replace(':', ' – ')), key)
        self.layout_cb.setToolTip(_('rozložení klávesnice nastavené v systému – podle něj se text převede na klávesy'))
        tools.addWidget(self.layout_cb, 3, 0, 1, 2)

        self.mouse_cb = QComboBox()
        for code, name in MOUSE_BUTTONS.items():
            self.mouse_cb.addItem(name, code)
        tools.addWidget(self.mouse_cb, 1, 0)
        b = QPushButton(_('Vložit klik myši'))
        b.clicked.connect(self._insert_click)
        tools.addWidget(b, 1, 1)
        tools.addWidget(QLabel(_('Prodleva vybraných:')), 1, 2)
        self.delay_spin = QSpinBox(minimum=0, maximum=65535, value=20, suffix=' ms')
        self.delay_spin.editingFinished.connect(self._set_delay_selected)
        tools.addWidget(self.delay_spin, 1, 3)

        b = QPushButton(_('Smazat vybrané akce'))
        b.clicked.connect(self._delete_events)
        tools.addWidget(b, 2, 0)
        b = QPushButton(_('Vymazat makro'))
        b.clicked.connect(self._clear_events)
        tools.addWidget(b, 2, 1)
        self.save_btn = QPushButton(_('Uložit makra do klávesnice'))
        self.save_btn.clicked.connect(self._save)
        tools.addWidget(self.save_btn, 2, 3)
        g.addLayout(tools, 1, 1)
        hint = QLabel(_('Makro posílá kódy kláves – výsledný znak určuje rozložení klávesnice v systému, proto '
                      'u „Vložit text“ vyber stejné rozložení, jaké používáš. Makro přiřadíš klávese na stránce '
                      'Klávesy (Funkce „Makro“ → „Použít na klávesu“).'),
                      objectName='hint', wordWrap=True)
        g.addWidget(hint, 2, 0, 1, 2)
        g.setColumnStretch(1, 3)
        g.setColumnStretch(0, 1)
        self._reload_list()

    # ---------------------------------------------------------------- helpers
    def current(self) -> Macro | None:
        r = self.list.currentRow()
        return self.macros[r] if 0 <= r < len(self.macros) else None

    def _changed(self, names=False):
        self.persist(self.macros)
        self.dirty = True
        self.save_btn.setText(_('Uložit makra do klávesnice *'))
        if names:
            self.macrosChanged.emit()

    def _reload_list(self, select: int | None = None):
        row = self.list.currentRow() if select is None else select
        self.list.blockSignals(True)
        self.list.clear()
        for i, m in enumerate(self.macros):
            self.list.addItem(_('{i}. {name}  ({n} akcí)').format(i=i + 1, name=m.name, n=len(m.events)))
        self.list.blockSignals(False)
        if self.macros:
            self.list.setCurrentRow(max(0, min(row, len(self.macros) - 1)))
        self._load_events()

    def _load_events(self, *_args):
        m = self.current()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for e in (m.events if m else []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, text in enumerate([_('stisk ⬇') if e.down else _('uvolnění ⬆'), e.label(), str(e.delay)]):
                it = QTableWidgetItem(text)
                if c < 2:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        self.table.scrollToBottom()

    def _append(self, evs: list[MacroEvent]):
        m = self.current()
        if not m:
            self._new()
            m = self.current()
            if not m:
                return
        room = MAX_EVENTS - len(m.events)
        if len(evs) > room:
            QMessageBox.warning(self, _('Makra'), _('Makro může mít nejvýše {n} akcí.').format(n=MAX_EVENTS))
            evs = evs[:room]
        m.events += evs
        self._changed()
        self._reload_list()

    # ---------------------------------------------------------------- list ops
    def _new(self):
        name, ok = QInputDialog.getText(self, _('Nové makro'), _('Název:'), text=f'Makro {len(self.macros) + 1}')
        if ok and name.strip():
            self.macros.append(Macro(name.strip()))
            self._changed(names=True)
            self._reload_list(len(self.macros) - 1)

    def _rename(self):
        m = self.current()
        if m:
            name, ok = QInputDialog.getText(self, _('Přejmenovat makro'), _('Název:'), text=m.name)
            if ok and name.strip():
                m.name = name.strip()
                self._changed(names=True)
                self._reload_list()

    def _delete(self):
        r = self.list.currentRow()
        if r < 0 or QMessageBox.question(self, _('Smazat makro'), f'Smazat makro „{self.macros[r].name}“?') \
                != QMessageBox.StandardButton.Yes:
            return
        del self.macros[r]
        self._changed(names=True)
        self.macroDeleted.emit(r)
        self._reload_list(r)

    # ---------------------------------------------------------------- event ops
    def _insert_text(self):
        evs, skipped = text_to_events(self.text_edit.text(), self.delay_spin.value(), self.layout_cb.currentData())
        if skipped:
            QMessageBox.information(self, _('Makra'), _('Tyto znaky makro neumí napsat a byly vynechány: {chars}').format(chars=skipped))
        if evs:
            self._append(evs)
            self.text_edit.clear()

    def _insert_click(self):
        code, d = self.mouse_cb.currentData(), self.delay_spin.value()
        self._append([MacroEvent(TYPE_MOUSE, code, True, d), MacroEvent(TYPE_MOUSE, code, False, d)])

    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _delete_events(self):
        m = self.current()
        if m:
            for r in reversed(self._selected_rows()):
                del m.events[r]
            self._changed()
            self._reload_list()

    def _clear_events(self):
        m = self.current()
        if m and m.events:
            m.events.clear()
            self._changed()
            self._reload_list()

    def _set_delay_selected(self):
        m = self.current()
        rows = self._selected_rows()
        if m and rows:
            for r in rows:
                m.events[r].delay = self.delay_spin.value()
            self._changed()
            self._load_events()

    def _delay_edited(self, item: QTableWidgetItem):
        m = self.current()
        if not m or item.column() != 2:
            return
        try:
            m.events[item.row()].delay = max(0, min(65535, int(item.text())))
        except ValueError:
            pass
        self._changed()
        self._load_events()

    # ---------------------------------------------------------------- recording
    def _record_toggled(self, on: bool):
        self.rec_btn.setText(_('⏹ Zastavit nahrávání') if on else _('⏺ Nahrát z klávesnice'))
        if on:
            if not self.current():
                self._new()
            if not self.current():
                self.rec_btn.setChecked(False)
                return
            self._rec_last, self._rec_mods = None, 0
            self.setFocus()
            self.grabKeyboard()
        else:
            self.releaseKeyboard()

    def _record(self, e, down: bool):
        if e.isAutoRepeat():
            return
        code = e.nativeScanCode() - 8
        now = time.monotonic()
        m = self.current()
        if m.events and self._rec_last is not None:
            m.events[-1].delay = max(1, min(65535, int((now - self._rec_last) * 1000)))
        self._rec_last = now
        if code in EVDEV_MODIFIER:
            ev = MacroEvent(TYPE_MODS, EVDEV_MODIFIER[code], down, 20)
        elif code in EVDEV_TO_HID:
            ev = MacroEvent(TYPE_KEY, EVDEV_TO_HID[code], down, 20)
        else:
            return
        if len(m.events) >= MAX_EVENTS:
            self.rec_btn.setChecked(False)
            return
        m.events.append(ev)
        self._changed()
        self._reload_list()

    def keyPressEvent(self, e):
        if self.rec_btn.isChecked():
            self._record(e, True)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.rec_btn.isChecked():
            self._record(e, False)
        else:
            super().keyReleaseEvent(e)

    # ---------------------------------------------------------------- save
    def _save(self):
        if self.rec_btn.isChecked():
            self.rec_btn.setChecked(False)
        self.saveRequested.emit(build_block(self.macros))

    def mark_saved(self):
        self.dirty = False
        self.save_btn.setText(_('Uložit makra do klávesnice'))
