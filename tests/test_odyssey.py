import os

from keyboardlight.devices.odyssey import Lighting, frame
from keyboardlight.devices.odyssey_layout import (DISABLED_ENTRY, EFFECTS, EVDEV_TO_HID, KEY_BY_SLOT, KEYS,
                                                  consumer_entry, describe, keyboard_entry)

HERE = os.path.dirname(__file__)


def test_frame_checksum_matches_captured_packet():
    # captured: begin configure / read config 0x38 @0
    assert frame(0x01)[:8] == bytes.fromhex('0401000100000000')
    assert frame(0x05, 0x38, 0)[:8] == bytes.fromhex('043d000538000000')


def test_layout_has_82_keys_plus_knob_and_unique_slots():
    slots = [k.slot for k in KEYS]
    assert len(slots) == len(set(slots)) == 83          # 82 keys + knob
    assert all(0 <= s < 90 for s in slots)


def test_layout_matches_factory_keymap_dump():
    km = open(os.path.join(HERE, 'data', 'odyssey_factory_keymap.bin'), 'rb').read()
    entry = lambda s: km[s * 3:s * 3 + 3]
    assert describe(entry(KEY_BY_SLOT[32].slot)) == 'W'
    assert describe(entry(45)) == 'CapsLock'
    assert describe(entry(85)) == 'Fn'
    assert describe(entry(81)) == 'Mezerník'
    assert describe(entry(14)) == 'Přehrát/Pauza'
    # every physical key except knob/Fn maps to a keyboard usage or modifier
    for k in KEYS:
        if k.slot not in (14, 85):
            assert entry(k.slot)[0] == 0x20, k


def test_entry_encoding():
    assert keyboard_entry(0x29) == bytes.fromhex('200029')
    assert keyboard_entry(0x06, 0x01) == bytes.fromhex('200106')
    assert describe(keyboard_entry(0x06, 0x01)) == 'L Ctrl + C'
    assert consumer_entry(0x00E2) == bytes.fromhex('30e200')
    assert describe(DISABLED_ENTRY) == 'vypnuto'


def test_lighting_roundtrip():
    block = bytearray(bytes.fromhex('00130402ff00ff0000040000000000000000010' '0ff000000000000060301') + bytes(0x40 - 30))
    light = Lighting.from_block(block)
    assert (light.effect, light.brightness, light.speed, light.direction, light.rainbow) == (19, 4, 2, 1, False)
    assert light.color == (0xff, 0, 0)
    out = bytearray(block)
    light.apply_to(out)
    assert out == block


def test_effect_values_unique_and_evdev_letters():
    vals = [v for v, _, _ in EFFECTS]
    assert len(vals) == len(set(vals))
    assert EVDEV_TO_HID[30] == 0x04 and EVDEV_TO_HID[44] == 0x1D   # A, Z (evdev KEY_A=30, KEY_Z=44)
