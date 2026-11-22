#!/bin/sh
# KeyBoardLight installer for CachyOS / Arch Linux.
#   Download from https://github.com/brbla/keyboardlight/releases/latest and run:  sh install.sh
# It refreshes the package database, installs the dependencies, downloads the latest KeyBoardLight package
# and installs it. On any failure it prints what to do (Czech + English).
set -u

REPO="brbla/keyboardlight"
DEPS="python python-pyqt6 libxkbcommon"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() {
  printf '\n\033[1;31m!! %s\033[0m\n' "$1"
  [ -n "${2:-}" ] && printf '%b\n' "$2"
  exit 1
}

command -v pacman >/dev/null 2>&1 || fail "Tento instalátor je pro CachyOS / Arch (pacman). / This installer is for CachyOS / Arch (pacman)."
command -v curl   >/dev/null 2>&1 || fail "Chybí curl. / curl is missing." "  sudo pacman -S curl"

say "Kontrola připojení k internetu / Checking internet connection"
curl -fsS --max-time 15 -o /dev/null https://github.com || fail \
  "Nejde se připojit k internetu (github.com). / Cannot reach github.com." \
  "  Zkontrolujte připojení a zkuste to znovu. / Check the network and try again."

say "Aktualizace systému a instalace závislostí / Updating the system and installing dependencies"
echo "    sudo pacman -Syu --needed $DEPS"
if ! sudo pacman -Syu --needed $DEPS; then
  fail "Stažení balíčků selhalo. / Downloading packages failed." \
"  Nejčastěji jsou zastaralá zrcadla nebo seznam balíčků. Zkuste: / Usually outdated mirrors or package database. Try:
    sudo cachyos-rate-mirrors        # CachyOS: vybere funkční zrcadla / picks working mirrors
    sudo pacman -Syyu                # vynutí nové stažení seznamu / forces a fresh database
  a pak spusťte instalátor znovu. / then run this installer again."
fi

say "Stahování KeyBoardLight / Downloading KeyBoardLight"
URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
      | grep -o '"browser_download_url": *"[^"]*\.pkg\.tar\.zst"' | head -n1 | sed 's/.*"\(http[^"]*\)"/\1/')
[ -n "$URL" ] || fail "Nepodařilo se najít balíček na GitHubu. / Could not find the package on GitHub." \
  "  Stáhněte ho ručně: / Download it manually: https://github.com/$REPO/releases/latest"
TMP=$(mktemp -d) || fail "mktemp selhal / mktemp failed"
PKG="$TMP/$(basename "$URL")"
curl -fL --retry 3 -o "$PKG" "$URL" || fail "Stažení balíčku selhalo. / Package download failed." "  $URL"

say "Instalace / Installing $(basename "$PKG")"
sudo pacman -U --noconfirm "$PKG" || fail "Instalace selhala. / Installation failed." \
  "  Zkuste: / Try:  sudo pacman -U $PKG"
rm -rf "$TMP"

say "Hotovo! / Done!"
echo "  1. Odpojte a znovu připojte klávesnici (kabel = přepínač TYP-C, přijímač = 2.4G)."
echo "     Unplug and re-plug the keyboard (cable = switch TYP-C, receiver = 2.4G)."
echo "  2. Spusťte KeyBoardLight z nabídky aplikací. / Start KeyBoardLight from the application menu."
