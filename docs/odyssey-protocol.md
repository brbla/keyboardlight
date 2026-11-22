# Yenkee YKB 30 Odyssey – USB protocol notes

Device: `320f:5055` "Telink ODYSSEY" (same OEM board as Evision Kreo Hive) over the USB cable (switch on TYP-C).

**2.4 GHz receiver** `320f:5088` "Telink Wireless Gaming Keyboard" exposes the same two interfaces and the same
config channel (report 4, page 0xFF1C), but relays only **32-byte packets**: 8 B header + **24 B (0x18) data**.
All commands work when every frame carries at most 0x18 data bytes (longer frames are truncated → zeros on read,
corrupted writes). Verified: info, config read/write, per-key colours, key map read/write.

**Bluetooth** exposes only feature report 5 (vendor page 0xFF01, 4 B); GET_FEATURE returns `05 00 00 00 00`,
all other report IDs fail. The vendor app never uses feature reports (no HidD_SetFeature import), so there is no
known configuration protocol over Bluetooth – settings stored in the keyboard still apply.
Bluetooth is **LE** (HID over GATT) with the standard **Battery Service** (0x180F) → BlueZ `org.bluez.Battery1.Percentage`
(used by the app). A Telink vendor GATT service `00010203-0405-0607-0809-0a0b0c0d1912` (Telink OTA) is present –
deliberately not touched.

## Interfaces (USB)

| Intf | hidraw descriptor | Purpose |
|---|---|---|
| 0 | boot keyboard + 64 B feature report (no report ID) | typing; feature report unused so far |
| 1 | IDs 1 NKRO, 2 system, 3 consumer, **4 vendor (page 0xFF1C, usage 0x92, 63 B in/out)**, 5 vendor 32 B in/out, 6 mouse | **config channel = report 4** |

## Frame (report 4, 64 bytes incl. report ID)

```
[0]    0x04  report ID
[1..2] checksum, LE = sum(bytes[3..63]) & 0xFFFF
[3]    command
[4]    data length
[5..6] offset, LE
[7]    0
[8..]  data (max 0x38 bytes)
```
The device answers with the same header (echo) and data at `[8..]`. Same family as OpenRGB's EVision controllers.

| Cmd | Meaning |
|---|---|
| 0x01 | begin configure |
| 0x02 | end configure |
| 0x05 | read config (`length`, `offset`) |
| 0x06 | write config (`length`, `offset`, data) |

### Flash semantics (important)
Config is stored in flash. A write **only clears bits** (AND), except a write **starting at offset 0**,
which erases the block (at least 0x00–0x3F) first. Always read-modify-write the whole block 0x00–0x3F:
write 0x38 B at offset 0, then the remaining 8 B at offset 0x38. See `tools/poke_odyssey.py`.

## Lighting config (offset 0x00…)

| Offset | Meaning | Values / Fn shortcut |
|---|---|---|
| 0x00 | ? (profile?) | 00 |
| 0x01 | effect | 06 = static, 01 = wave; Fn+Home cycles |
| 0x02 | brightness | 0 (off) – 4 (max); Fn+↑ / Fn+↓ |
| 0x03 | speed | 0 (fastest) – 4 (slowest); no Fn shortcut found |
| 0x04 | direction | 00 = left→right, ff = right→left; Fn+← |
| 0x05 | rainbow / multicolour | 00 = single colour, ff = rainbow; Fn+Space |
| 0x06–0x08 | colour R G B | e.g. ff 00 00 red, ff 60 00 orange, 00 ff ff cyan; Fn+→ cycles presets |
| 0x09 | preset colour index | 0 red, 1 orange, … 4 cyan |
| 0x10–0x1F | unknown, possibly second zone (spacebar strip?) | `00 00 01 00 ff 00 00 00 00 00 00 06 03 01 00 00` |
| 0x40–0x1BF | mostly ff (erased), 0xA8–0xAF = 00 | unknown (keymap / per-key colours / macros?) |

Other observations:
- Fn+Del toggles backlight on/off, not stored in this config area.
- Green strip at the spacebar = **charging indicator** (manual): green while charging in wired mode,
  returns to normal when full; red when battery < 10 %. Not a lighting zone.
- Fn+Enter, Fn+PgUp, Fn+PgDn, Fn+End: no visible effect.

## Effects (byte 0x01)

Names from the vendor software (`DefaultData/default_light.json` list 0 + `Skin/lan_en.xml` / `lan_cz.xml`
in `45021093-sw.zip`), behaviour verified with the webcam (`tools/cam_watch.py`).
Fn+Home cycle order: 6 → 1 → 4 → 5 → 2 → 3 → 8 → 7 → 9 → 11 → 10 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 20 → 6.

| Value | EN (software) | CZ (software) | Webcam observation |
|---|---|---|---|
| 0 | (hidden) | – | dark |
| 1 | Corrugated | Vlnění | moving wave |
| 2 | Cloud | Mrak | whole board breathing, colour |
| 3 | Serpentine | Serpentýna | moving |
| 4 | Spectrum | Spektrum | whole board one colour, cycling |
| 5 | Breath | Dýchání | breathing bands |
| 6 | Normal (static) | Statické | static |
| 7 | Reaction | Reakce na stisk | dark until keys pressed |
| 8 | Ripples | Vlnky | ripple from pressed key |
| 9 | Traverse | Přechod | mostly dark (reactive) |
| 10 | Stars | Hvězdy | random sparkles |
| 11 | Flowers | Květiny | moving spots |
| 12 | Roll | Řádky | horizontal colour rows |
| 13 | Wave | Mávání | moving left→right |
| 14 | Cartoon | Kulatá animace | mostly dark (reactive) |
| 15 | Rain | Déšť | vertical bands |
| 16 | Scan | Skenovat | top row / edge lit |
| 17 | Surmount | Přechodová reakce | bright centre |
| 18 | Speed | Přechod ze středu | moving |
| 19 | Custom (per-key) | Herní podsvícení | per-key colours (currently black) – **not in Fn+Home cycle** |
| 20 | Off | Vypnuto | (in Fn+Home cycle) |
| 29 | Audio wave | Reakce na hudbu | host-driven (software streams audio levels) |
| 30 | Shadow | Stín | host-driven (screen colour capture) |

## Per-key colours (effect 19 = Custom)

Found in OpenRGB issue #5190 captures (`tools/pcap_frames.py`), verified on the device + webcam.

| Cmd | Meaning |
|---|---|
| 0x0a | read per-key colours (`len` ≤ 0x38, `offset`) |
| 0x0b | write per-key colours, chunks of 0x38 from offset 0, total 0x180 B |
| 0x10 / 0x11 | **not supported** (reply has byte[7] = 0xFF = error flag) |

- 0x180 B = 128 slots × R G B. LED index = **row × 15 + col** (6 rows × 15 cols, first 90 slots used).
- Factory default: W(32) A(46) S(47) D(48) ↑(73) ←(87) ↓(88) →(89) = `ff ff ff`, everything else black.
  Backup: `tools/snapshots/keycolors/custom_colors_backup.bin`.
- Effect 19 ignores the main colour bytes 0x06–0x08; overall brightness byte 0x02 still applies.
- Vendor software sequence: 0x0b × 7 chunks, then begin / write config with effect 0x13 / end.
- Tool: `tools/keycolors_odyssey.py set 101010 32,46,47,48=ff0000 73,87,88,89=0000ff`.

## Device info, key map

| Cmd | Meaning | Status |
|---|---|---|
| 0x03 | read device info, 0x22 B (`aa 55 00 00 06 80 18 00 02 …`) | read OK |
| 0x07 | read **default (factory) key map**, 0x180 B = 128 slots × 3 B, **slot index == LED index** | read OK |
| 0x08 | read **active key map** (same format) | read OK |
| 0x09 | write **active key map** (chunks of 0x38 from offset 0) | write OK, verified by 0x08 read-back |
| 0x1b | read 0x80 B: identity table 0x00–0x59 + 16 bytes `18 39 10 23 22 48 3c 24 33 12 0c 09 49 3d 06 31` | meaning unknown |

Key map entry: `20 mm uu` = keyboard (mm = modifier mask, uu = HID usage), `30 lo hi` = consumer usage,
`a0 xx 00` = special (Fn = `a0 01`, knob rotate = `a0 30` / `a0 31`).
Layout (ISO, 6 × 15): row 0 Esc F1–F12 Delete Knob-press · row 1 ` 1–0 - = Backspace Home ·
row 2 Tab Q–P [ ] \ End · row 3 Caps A–L ; ' #(ISO) Enter PgUp · row 4 LShift \(ISO) Z–/ RShift Up PgDn ·
row 5 LCtrl LWin LAlt (78–80 hidden) Space (82–83 hidden) RAlt Fn RCtrl Left Down Right.
Row 6 (90–104) = numpad slots not present on this board; 118/119 = knob rotation.
Factory dump: `tools/snapshots/keymap/factory_*.bin`.

**Incident 2026-11-22:** the vendor app under Wine wrote heap garbage (contained the string `MacroInfo`) via 0x09
when saving a remap, and the keyboard stopped typing. Recovered by writing the 0x07 default map into 0x09.
→ Never let the vendor app write to the keyboard under Wine; always dump an area before writing to it.
Wine needs `winebus\Devices\320f/5055` `Hidraw=1` (see `~/.local/share/keyboardlight/winebus-enable-hidraw.reg`)
to see the device at all.

Vendor software features (from `Skin/lan_en.xml`): macros (record, delays, up to 256 actions per key,
repeat modes: once / while held / toggle / N times), key remap (keyboard, multimedia, mouse, system, macro),
Windows-key lock, USB report rate. "Repeat rate / delay" in the software is the **Windows OS setting**, not a device
setting. No actuation / debounce settings (mechanical Gateron G Pro 2.0 Yellow switches, fixed 2.0 mm).

## Macros

Reverse-engineered from `YENKEE ODYSSEY.exe` (objdump; frame builders at 0x479910…, macro writer 0x4a4b20,
event packer 0x4472b0, key-assignment builder 0x4105d0) and verified on the device.

Commands used by the vendor app: 01 02 03 05 06 07 09 0b **15** 17 1a 1b 1c aa.
`0x15` = write macro block (0x38-byte chunks from offset 0). The app never reads macros back
(macros live in the app profile); a read command is unknown (0x14 untested on purpose).
`0x17` = write "ShootData" (mouse fire key), `0x1a`/`0x1b` = write/read a 0x80 B table (0x1b reads an identity
table 0x00–0x59 + 16 bytes; meaning unknown).
`0xaa` = status ping sent by the vendor app before writes; reply data[0] = `ff` over the 2.4 GHz receiver, `00` over the USB cable (link-type flag, no battery info).

**Battery:** not reported over the cable or the 2.4 GHz receiver – no byte in info (0x03), config (0x05), table 0x1b
or the 0xaa reply matches the BLE battery level, the receiver sends no unsolicited status reports, and the vendor app
has no battery feature. Only Bluetooth LE reports it (Battery Service).

Macro block:
```
0x00 u16 0x55AA | 0x02 u16 total length | 0x04 u16 macro count | 0x06..0x0F zero
0x10 u16 offset[count]   absolute offset of each macro inside the block
macro: u16 event count, u16 0, events × 4 B:
  [0..1] delay ms (u16 LE, vendor max 65535)  [2] type | 0x80 when pressed  [3] code
```
Event types (verified with hidraw capture): **0x0A key** (HID usage), **0x09 modifiers** (bit mask,
same as key-map modifier byte), 0x01 mouse buttons (bit mask 01 L, 02 R, 04 M, 08/10 back/fwd),
0x02 horizontal wheel; 3/4/5 other mouse actions (unverified).

Key-map entry that triggers macro *i* (written with 0x09 like any remap):
| Entry | Vendor label | Meaning (interpretation) |
|---|---|---|
| `70 ii 00` | Běžný / Regular | play once |
| `70 ii 01` | Ukončení relace / Release Stop | repeat while held |
| `70 ii 02` | Zmáčkněte dolů / Press Down | toggle: press starts repeating, next press stops |
| `70 ii 03` | Ihned uvolnit / Release Immediately | repeat while held, stop at once on release |
| `71 ii NN` | Zastavit po určeném počtu | play NN times |

Tool: `tools/macro_odyssey.py text <string>`.

## Keyboard shortcuts

Source: manual `docs/vendor/ykb30-odyssey-manual.pdf` (YKB 30/31, rev. 03/2023,
https://data.fast.eu/manual/45/45021093/45021093-im.pdf) + own tests (✔ = verified, config byte in brackets).

| Shortcut | Function | Source |
|---|---|---|
| Fn + ← | effect direction (0x04) | manual ✔ |
| Fn + → | next preset colour (0x06–0x09) | manual ✔ |
| Fn + ↓ / Fn + ↑ | brightness down / up (0x02, 0–4) | manual ✔ |
| Fn + Del | backlight on / off | manual ✔ |
| Fn + Home | next effect (0x01) | manual ✔ |
| Fn + Space | rainbow on / off (0x05) | **undocumented** ✔ |
| Fn + 1 / 2 / 3 | switch Bluetooth device; hold 3 s = pairing (LED flashes fast) | manual |
| Fn + G (hold 3 s) | pair 2.4 GHz receiver | manual (CZ) |
| Fn + Enter, PgUp, PgDn, End | nothing visible | tested |

Hardware: 75 % layout, 82 keys, rotary knob, switch on the bottom: 2.4G (left) / BT (middle) / TYP-C wired (right).
Backlight turns off after 3 min idle on battery; sleep after 10 min.
Windows software: https://data.fast.eu/software/45/45021093/45021093-sw.zip ("ODYSSEY software suite").

## Colour / rainbow support per effect (webcam test 2026-11-22, red vs rainbow, with typing)
- Honour colour **and** rainbow: 6 static, 1 wave, 5 breath, 2 cloud, 3 serpentine, 10 stars, 13 waving, 14 circles,
  15 rain, 16 scan; reactive (only light on key press): 7 reaction, 8 ripples, 9 traverse (row runs from the key).
- Own fixed colours, colour + rainbow ignored: 4 spectrum (whole board cycles hues), 11 flowers, 12 rows,
  18 centre transition (multicolour), 17 transition reaction (white).
- 14 circles is an autonomous animation, not reactive.

## Speed / direction per effect (webcam test 2026-11-22; speed byte 0 fastest … 4 slowest)
- Direction works: 1 wave and 2 cloud (00 = moves left→right, ff = right→left), 12 rows (00 = top→bottom,
  ff = bottom→top). No effect elsewhere (3 serpentine only looked reversed at full speed – camera aliasing).
- Speed works: 1, 2, 3, 4, 5, 11, 12, 15; weaker/irregular: 10 stars, 13 waving.
- Speed has no visible effect: 16 scan (bar sweeps back and forth at any speed), 17, 18.
- 14 circles: expanding rings at random places, honours colour/rainbow, speed has a small effect. During a long
  test session it got **stuck dark** (any speed, typing, re-writing the effect did not help); unplugging and
  replugging the keyboard fixed it, and later config writes did not break it again. Full re-test after the replug:
  all other results unchanged. The app shows a "disconnect and reconnect" hint on the lighting page.
