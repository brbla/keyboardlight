# KeyBoardLight – plán práce

Stav k 2026-11-22.

## Hotovo
- [x] Yenkee Odyssey: protokol podsvícení (efekty, jas, rychlost, směr, duha, barva) – `docs/odyssey-protocol.md`
- [x] Odyssey: barvy jednotlivých kláves (efekt 19), čtení i zápis
- [x] Odyssey: mapa kláves – čtení výchozí (0x07) i aktivní (0x08), zápis (0x09), ověřeno (CapsLock → X)
- [x] Pomocné nástroje v `tools/` (snapshoty, kamera, odposlech usbmon, dekódování pcap, ovládání X11 oken)
- [x] Aplikace v0.1 (PyQt6): podsvícení, barvy kláves, přemapování kláves – `./keyboardlight.sh`
- [x] Makra Odyssey: formát zjištěn z `YENKEE ODYSSEY.exe` a ověřen; stránka Makra (nahrávání, text, kliky myši, prodlevy), přiřazení makra klávese s režimy

- [x] Profily (Den/Noc…): uložení podsvícení, volitelně barev kláves a mapy kláves s makry; přepínání v okně i `keyboardlight.sh --profile NÁZEV`

- [x] Překlad CZ/EN, převod textu maker pro libovolné rozložení klávesnice (libxkbcommon)
- [x] Zobrazují se jen volby platné pro zvolený efekt; jeden posuvník jasu (celá klávesnice / vybrané klávesy, 0–100 %)
- [x] Veřejný repozitář https://github.com/brbla/keyboardlight + PKGBUILD pro CachyOS/Arch

## Rozpracováno / další kroky
1. [ ] Makra: ověřit režimy 1–3 a 0x71 (N×) na klávesnici; typy událostí 3/4/5 (kolečko, pohyb myši).
2. [ ] Knoflík: otáčení je ve firmwaru napevno (hlasitost) – nabídnout přemapování v systému (udev hwdb:
       `evdev:input:b0003v320Fp5055*` → KEYBOARD_KEY_c00e9/c00ea = brightnessup/down).
3. [ ] Odyssey: zámek Win klávesy, frekvence hlášení USB (pravděpodobně bajty v konfiguračním bloku 0x10–0x3F).
4. [ ] **Aula 60HE** – připojit, zjistit VID:PID, rozebrat webový ovladač (hero.aulastar.com, magnet.aulastar.com),
       přidat ovladač do aplikace (citlivost/aktuace, rapid trigger, podsvícení, mapa kláves).
5. [ ] Publikovat balíček do AUR.
6. [ ] **Reaktivní efekty nad vlastními barvami** (nápad uživatele): firmware umí reakci/vlnky jen s jednou barvou
       nebo duhou, kombinaci s efektem 19 ne. Varianta: efekt počítá aplikace a posílá barvy živě. Příkaz 0x0b
       zapisuje do flash → nevhodné pro animaci. Najít „živý“ kanál, kterým výrobce streamuje režimy
       Stín/Hudba (29/30): kandidáti HidD_SetOutputReport ve fn 0x487500, report ID 5 (32 B), příkazy 0x1c/0xaa.
       Pak démon v pozadí čte stisky (hidraw) a kreslí vlnu.
7. [ ] Aplikace: ikona, přepínání mezi více klávesnicemi, export/import profilu (JSON).
