from keyboardlight.devices.odyssey_layout import describe, macro_entry
from keyboardlight.devices.odyssey_macros import TYPE_KEY, TYPE_MODS, Macro, MacroEvent, build_block, text_to_events


def test_block_matches_verified_probe():
    # block that made the keyboard emit mouse/mods/'l' on 2026-11-22 (types 2, 3, 9, 0x0a)
    evs = []
    for typ, code in [(2, 0x0e), (3, 0x07), (9, 0x0d), (0x0a, 0x0f)]:
        evs += [MacroEvent(typ, code, True, 10), MacroEvent(typ, code, False, 10)]
    assert build_block([Macro('t', evs)]).hex(' ') == (
        'aa 55 36 00 01 00 00 00 00 00 00 00 00 00 00 00 12 00 08 00 00 00 0a 00 82 0e 0a 00 02 0e '
        '0a 00 83 07 0a 00 03 07 0a 00 89 0d 0a 00 09 0d 0a 00 8a 0f 0a 00 0a 0f')


def test_two_macros_offsets():
    blk = build_block([Macro('a', [MacroEvent(TYPE_KEY, 4, True)]), Macro('b', [])])
    assert blk[4] == 2 and blk[0x10:0x14] == bytes([0x14, 0, 0x1c, 0])
    assert int.from_bytes(blk[2:4], 'little') == len(blk)


def test_text_to_events_shift_and_skip():
    evs, skipped = text_to_events('Ab!č', 5, 'us')
    kinds = [(e.type, e.code, e.down) for e in evs]
    assert kinds[:4] == [(TYPE_MODS, 2, True), (TYPE_KEY, 4, True), (TYPE_KEY, 4, False), (TYPE_MODS, 2, False)]
    assert (TYPE_KEY, 0x1E, True) in kinds          # '!' = Shift + 1
    assert skipped == 'č'


def test_macro_entry_and_describe():
    assert macro_entry(0) == bytes([0x70, 0, 0])
    assert macro_entry(2, 1) == bytes([0x70, 2, 1])
    assert macro_entry(1, times=5) == bytes([0x71, 1, 5])
    assert describe(macro_entry(1, times=5)) == 'makro 2 ×5'


def test_czech_layout():
    from keyboardlight.devices.odyssey_macros import ALTGR, SHIFT
    evs, skipped = text_to_events('Ahoj!', 5, 'cz')
    k = [(e.type, e.code, e.down) for e in evs]
    assert (TYPE_MODS, SHIFT, True) in k and (TYPE_KEY, 0x34, True) in k     # '!' = Shift + § key on CZ
    assert not skipped
    evs, _ = text_to_events('z1ě@', 5, 'cz')
    k = [(e.type, e.code) for e in evs if e.down]
    assert k[:4] == [(TYPE_KEY, 0x1C), (TYPE_MODS, SHIFT), (TYPE_KEY, 0x1E), (TYPE_KEY, 0x1F)]
    assert k[4] == (TYPE_MODS, ALTGR) and k[5][1] in (0x19, 0x1F)      # '@' = AltGr+V or AltGr+2 on CZ
    assert text_to_events('z', 5, 'cz:qwerty')[0][0].code == 0x1D


def test_other_layouts_via_xkb():
    from keyboardlight import xkb_layout
    if not xkb_layout.available():
        return
    de = xkb_layout.char_table('de')
    assert de['z'] == (0x1C, 0) and de['ä'][0] == 0x34 and de['@'] == (0x14, 0x40)
    assert xkb_layout.char_table('cz')['!'][1] == 0x02          # Shift preferred over AltGr
