<p align="center"><img src="docs/icon.svg" width="96" alt="KeyBoardLight icon"></p>

# KeyBoardLight

**Linux configurator for the Yenkee YKB 30 Odyssey and AULA WIN68 HE keyboards** – lighting effects, per-key colours,
key remapping, macros and profiles. No Windows, no Wine, everything is stored in the keyboard itself.

**Linuxová aplikace pro nastavení klávesnice Yenkee YKB 30 Odyssey** – efekty podsvícení, barvy jednotlivých
kláves, přemapování kláves, makra a profily. Bez Windows a bez Wine, vše se ukládá přímo do klávesnice.
[Česky níže ↓](#česky)

![screenshot](docs/screenshot.png)

## Features

| | |
|---|---|
| **Lighting** | all 20 hardware effects, brightness, speed, direction, colour, rainbow – only the controls that apply to the chosen effect are shown |
| **Per-key colours** | click/drag to paint keys, any RGB colour, per-key brightness 0–100 % (selected keys or the whole keyboard) |
| **Keys** | remap any key to another key (with Ctrl/Shift/Alt/Win), a multimedia function, a macro, or disable it |
| **Macros** | record from the keyboard, type text (aware of your system keyboard layout via libxkbcommon), mouse clicks, delays; play once / while held / toggle / N times |
| **Profiles** | save named presets (e.g. *Day*, *Night*) and switch with one click or `keyboardlight --profile Night` (bind it to a hotkey or a timer) |
| **Knob** | the knob always changes volume (fixed in firmware); one click under *More* makes **Ctrl + knob** change the screen brightness (KDE Plasma) |
| **AULA WIN68 HE** | lighting effects, per-key colours, per-key actuation point and rapid trigger (sensitivity), SOCD pairs, automatic backup of the original settings and one-click restore |
| **Battery** | battery level shown in the app while the keyboard is connected over Bluetooth (BLE Battery Service) |
| **Auto-detect** | detects which keyboard is connected (cable, 2.4 GHz receiver, Bluetooth) at start and while running, and switches to the right settings |
| **Languages** | English and Czech (follows the system language, switchable under *More*) |
| **Safety** | every write is verified by reading it back; each area is backed up before the first write (`~/.local/share/keyboardlight/backups/`) |

Connect the keyboard **by USB cable** (switch on the bottom on **TYP-C**) **or through its 2.4 GHz USB receiver**
(switch on **2.4G**). Over **Bluetooth** the keyboard cannot be configured – but everything you set is stored in the
keyboard, so it keeps working over Bluetooth too.

## Install

### CachyOS / Arch Linux – installer (recommended)
Download **`install.sh`** from **[Releases](https://github.com/brbla/keyboardlight/releases/latest)** and run it:
```sh
sh install.sh
```
It updates the system, installs the dependencies (PyQt6), downloads the latest package and installs it. If anything
fails (e.g. *failed to download* because of outdated mirrors) it tells you exactly what to do.

### CachyOS / Arch Linux – ready-made package
Download the latest `keyboardlight-*-any.pkg.tar.zst` from
**[Releases](https://github.com/brbla/keyboardlight/releases/latest)** and install it:
```sh
sudo pacman -Syu                                   # update first – avoids "failed to download" of dependencies
sudo pacman -U keyboardlight-*-any.pkg.tar.zst
```

### CachyOS / Arch Linux – build from source
```sh
git clone https://github.com/brbla/keyboardlight.git
cd keyboardlight/packaging/arch
makepkg -si
```
Then unplug and re-plug the keyboard and start **KeyBoardLight** from the application menu.
The package installs a udev rule (`/usr/lib/udev/rules.d/70-keyboardlight.rules`) that gives the logged-in user
access to the keyboard – no root needed afterwards.

### Run from source (any distribution)
Requirements: Python ≥ 3.10, PyQt6, libxkbcommon.
```sh
sudo cp udev/70-keyboardlight.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger   # then re-plug the keyboard
./keyboardlight.sh
```

### Command line
```sh
keyboardlight --list-profiles
keyboardlight --profile Night        # apply a saved profile without opening the window
```

## Supported hardware

| Keyboard | USB ID | Status |
|---|---|---|
| Yenkee YKB 30 Odyssey (Telink, 75 %, 82 keys) – USB cable | `320f:5055` | ✅ supported |
| Yenkee YKB 30 Odyssey – 2.4 GHz USB receiver | `320f:5088` | ✅ supported |
| Yenkee YKB 30 Odyssey – Bluetooth | – | ❌ no configuration channel (settings stored in the keyboard still apply) |
| Evision Kreo Hive and other boards with `320f:5055` | `320f:5055` | likely works (same OEM board), untested |
| AULA WIN68 HE (Hall-effect, Standard edition) | `2e3c:c365` | ✅ lighting effects, per-key colours, per-key actuation point + rapid trigger, SOCD, automatic backup + restore of the original settings |

## Troubleshooting

- **Keyboard stays dark** although the app shows a lighting setting (Fn + Del does nothing): the firmware sometimes
  keeps the backlight asleep after switching from battery to cable. Unplug the cable, move the switch to 2.4G and
  back to TYP-C, plug the cable in again.
- **Keyboard not found:** use the cable (switch TYP-C) or the 2.4 GHz receiver (switch 2.4G) – Bluetooth cannot be
  used for configuration. After installing from source, re-plug the keyboard so the udev rule applies.

## How it works

The protocol was reverse-engineered on Linux (usbmon captures, a webcam watching the LEDs, and static
analysis of the vendor Windows app). It is documented in **[docs/odyssey-protocol.md](docs/odyssey-protocol.md)**:
64-byte HID reports (report ID 4) on interface 1 – lighting block, per-key colours, default/active key map,
macro block and key-assignment encoding. Helper scripts used during the research are in `tools/`.

Not affiliated with Yenkee / FAST ČR. Use at your own risk – although every write is verified and backed up,
this is unofficial software talking to the keyboard firmware.

## Development
```sh
python -m pytest tests          # unit tests (no keyboard needed)
KEYBOARDLIGHT_LANG=en ./keyboardlight.sh
```
Roadmap: [docs/PLAN.md](docs/PLAN.md).

---

## Česky

**Co umí**
- **Podsvícení:** všech 20 efektů klávesnice, jas, rychlost, směr, barva, duha. Zobrazují se jen volby, které má u daného efektu smysl měnit.
- **Barvy jednotlivých kláves:** klikáním nebo tažením obarvíte klávesy libovolnou barvou, jas 0–100 % pro vybrané klávesy nebo celou klávesnici.
- **Klávesy:** přemapování na jinou klávesu (i s Ctrl/Shift/Alt/Win), multimediální funkci, makro, nebo vypnutí klávesy.
- **Makra:** nahrávání z klávesnice, vložení textu (podle rozložení klávesnice v systému, např. česká QWERTZ), kliknutí myší, prodlevy; přehrát jednou / při držení / přepínač / N-krát.
- **Profily:** uložené předvolby (např. *Den*, *Noc*) a přepínání jedním kliknutím nebo příkazem `keyboardlight --profile Noc`.

- **Baterie:** když je klávesnice připojená přes Bluetooth, aplikace ukazuje stav baterie.
- **Knoflík:** otáčení mění vždy hlasitost (dáno firmwarem); jedním tlačítkem na stránce *Další* nastavíte, že **Ctrl + knoflík** mění jas obrazovky (KDE Plasma).

**Instalace na CachyOS / Arch – instalátor (doporučeno)**
Stáhněte **`install.sh`** z **[Releases](https://github.com/brbla/keyboardlight/releases/latest)** a spusťte:
```sh
sh install.sh
```
Aktualizuje systém, doinstaluje závislosti (PyQt6), stáhne nejnovější balíček a nainstaluje ho. Když něco selže
(např. *failed to download* kvůli zastaralým zrcadlům), napíše přesně, co udělat.

**Hotový balíček ručně:** stáhněte `keyboardlight-*-any.pkg.tar.zst` z Releases a spusťte
`sudo pacman -Syu` (aktualizace – předejde chybě „failed to download“) a pak `sudo pacman -U keyboardlight-*-any.pkg.tar.zst`.
Nebo ze zdrojů: `git clone https://github.com/brbla/keyboardlight.git && cd keyboardlight/packaging/arch && makepkg -si`
Pak klávesnici odpojte a znovu připojte a spusťte **KeyBoardLight** z nabídky aplikací.
Klávesnici připojte **kabelem** (přepínač vespod na **TYP-C**) **nebo přes USB přijímač 2,4 GHz** (přepínač na **2.4G**).
Přes **Bluetooth** nastavovat nejde, ale vše, co nastavíte, je uložené v klávesnici a funguje i přes Bluetooth.

**Klávesnice nesvítí**, i když je vše nastavené a nepomáhá ani Fn + Del? Odpojte kabel, přepněte přepínač na 2.4G
a zpět na TYP-C a kabel znovu zapojte (firmware se po přepnutí z baterie na kabel občas zasekne).

Aplikace není oficiálním produktem firmy Yenkee / FAST ČR.
