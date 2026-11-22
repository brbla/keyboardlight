from keyboardlight import profiles
from keyboardlight.devices import odyssey_macros
from keyboardlight.devices.odyssey import Lighting
from keyboardlight.devices.odyssey_macros import Macro, MacroEvent


class FakeDev:
    def __init__(self):
        self.light = Lighting(6, 4, 2, 0, False, (255, 0, 0))
        self.colors = [(0, 0, 0)] * 128
        self.km = [bytes([0x20, 0, 4])] * 128
        self.writes = []

    def read_lighting(self): return Lighting(**vars(self.light))
    def write_lighting(self, l): self.light = l; self.writes.append('light')
    def read_key_colors(self): return list(self.colors)
    def write_key_colors(self, c): self.colors = list(c); self.writes.append('colors')
    def read_keymaps(self): return list(self.km), list(self.km)
    def write_keymap(self, k): self.km = list(k); self.writes.append('keymap')
    def write_macros(self, b): odyssey_macros.mark_written(b); self.writes.append('macros')


def test_capture_apply_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, 'STORE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(odyssey_macros, 'STORE', str(tmp_path / 'm.json'))
    monkeypatch.setattr(odyssey_macros, 'WRITTEN', str(tmp_path / 'm.written'))
    night = profiles.capture('Noc', Lighting(19, 1, 2, 0, False, (0, 0, 255)),
                             [(10, 0, 0)] * 128, [bytes([0x20, 0, 5])] * 128,
                             [Macro('x', [MacroEvent(0x0A, 4, True)])])
    profiles.save_all([night])
    p = profiles.load_all()[0]
    assert p.name == 'Noc' and 'klávesy' in p.summary()
    dev = FakeDev()
    assert profiles.apply(dev, p) == ['podsvícení', 'barvy kláves', 'makra', 'mapa kláves']
    assert dev.light.brightness == 1 and dev.colors[0] == (10, 0, 0)
    dev.writes.clear()
    assert profiles.apply(dev, p) == []          # second apply: nothing differs -> no flash writes
    assert dev.writes == []


def test_lighting_only_profile_does_not_touch_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(odyssey_macros, 'WRITTEN', str(tmp_path / 'm.written'))
    p = profiles.capture('Den', Lighting(6, 4, 2, 0, True, (255, 255, 255)))
    dev = FakeDev()
    assert profiles.apply(dev, p) == ['podsvícení']
    assert dev.writes == ['light']
