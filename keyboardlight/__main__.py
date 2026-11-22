import argparse
import sys
from keyboardlight.i18n import _


def _missing_dependency(module: str, package: str) -> None:
    """Tell the user (terminal + desktop dialog) how to finish an incomplete installation."""
    import shutil
    import subprocess
    msg = _('KeyBoardLight nejde spustit – chybí knihovna {module}.\n\n'
            'Instalace se nejspíš nedokončila (např. selhalo stažení závislostí).\n'
            'Dokončete ji v terminálu příkazem:\n\n'
            '    sudo pacman -Syu {package}\n\n'
            'Když stahování selže, obnovte zrcadla: sudo cachyos-rate-mirrors (CachyOS)\n'
            'nebo sudo pacman -Syyu, a pak příkaz zopakujte.').format(module=module, package=package)
    print(msg, file=sys.stderr)
    for cmd in (['kdialog', '--title', 'KeyBoardLight', '--error', msg],
                ['zenity', '--error', '--title=KeyBoardLight', '--text', msg],
                ['notify-send', '-u', 'critical', 'KeyBoardLight', msg]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, timeout=600)
            except (OSError, subprocess.SubprocessError):
                continue
            break


def main() -> int:
    ap = argparse.ArgumentParser(prog='keyboardlight', description=_('Nastavení klávesnice Yenkee Odyssey'))
    ap.add_argument('--profile', metavar=_('NÁZEV'), help=_('načte uložený profil do klávesnice a skončí (bez okna)'))
    ap.add_argument('--list-profiles', action='store_true', help=_('vypíše uložené profily'))
    args = ap.parse_args()

    if args.list_profiles or args.profile:
        from keyboardlight import profiles
        from keyboardlight.devices.odyssey import Odyssey, OdysseyError
        allp = profiles.load_all()
        if args.list_profiles:
            for p in allp:
                print(f'{p.name}\t({p.summary()})')
            return 0
        match = [p for p in allp if p.name.lower() == args.profile.lower()]
        if not match:
            print(_('Profil „{name}“ neexistuje. Uložené: {saved}').format(name=args.profile, saved=', '.join(p.name for p in allp) or _('žádné')),
                  file=sys.stderr)
            return 2
        try:
            dev = Odyssey()
            written = profiles.apply(dev, match[0])
            dev.close()
        except OdysseyError as e:
            print(f'Chyba: {e}', file=sys.stderr)
            return 1
        print(_('Profil „{name}“ načten').format(name=match[0].name) + (_(' – zapsáno: {what}').format(what=', '.join(written)) if written else _(' – beze změny')))
        return 0

    import os
    try:
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        _missing_dependency('PyQt6', 'python-pyqt6')
        return 1
    from keyboardlight.gui.main_window import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName('KeyBoardLight')
    app.setDesktopFileName('keyboardlight')
    app.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'resources', 'keyboardlight.svg')))
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
