import importlib.util
import os
import subprocess
import sys

from PIL import Image

QUI = os.path.dirname(os.path.abspath(__file__))
LAVORO = os.path.join(QUI, "_build")
RILASCIO = os.path.join(QUI, "rilascio")


def icona():
    spec = importlib.util.spec_from_file_location("crea_icone", os.path.join(QUI, "streamdeck", "crea_icone.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    base.alpha_composite(modulo.cassa(232), (12, 12))
    percorso = os.path.join(LAVORO, "contacasse.ico")
    base.save(percorso, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return percorso


def main():
    os.makedirs(LAVORO, exist_ok=True)
    os.makedirs(RILASCIO, exist_ok=True)
    ico = icona()
    comando = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "ContaCasse", "--icon", ico,
        "--add-data", f"{os.path.join(QUI, 'web')}{os.pathsep}web",
        "--add-data", f"{os.path.join(QUI, 'base')}{os.pathsep}base",
        "--distpath", RILASCIO, "--workpath", os.path.join(LAVORO, "work"), "--specpath", LAVORO,
        "--exclude-module", "tkinter", "--exclude-module", "matplotlib", "--exclude-module", "pyaudiowpatch",
        "--exclude-module", "impronte", "--exclude-module", "PIL", "--exclude-module", "IPython",
        os.path.join(QUI, "contacasse.py"),
    ]
    print(" ".join(comando))
    subprocess.check_call(comando, cwd=QUI)
    exe = os.path.join(RILASCIO, "ContaCasse.exe")
    print(f"\nFatto: {exe} ({os.path.getsize(exe) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
