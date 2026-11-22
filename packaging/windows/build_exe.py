"""Build dist/GambiPad/GambiPad.exe with PyInstaller (one folder, no console window).

    .venv\\Scripts\\python.exe -m pip install pyinstaller
    .venv\\Scripts\\python.exe packaging\\windows\\build_exe.py

The executable is not code-signed, so Windows SmartScreen shows a warning the
first time it runs. packaging\\windows\\gambipad.iss turns the folder into an
installer (Inno Setup).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build" / "exe"

# Qt modules GambiPad never touches; leaving them out saves well over 100 MB.
UNUSED_QT = (
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtWebSockets",
    "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DExtras", "Qt3DAnimation", "Qt3DLogic",
    "QtQuick", "QtQuick3D", "QtQuickWidgets", "QtQuickControls2", "QtQml", "QtCharts", "QtGraphs",
    "QtDataVisualization", "QtPdf", "QtPdfWidgets", "QtSql", "QtTest", "QtMultimedia",
    "QtMultimediaWidgets", "QtBluetooth", "QtNfc", "QtPositioning", "QtLocation", "QtSensors",
    "QtSerialPort", "QtSerialBus", "QtDesigner", "QtHelp", "QtUiTools", "QtOpenGL",
    "QtOpenGLWidgets", "QtNetworkAuth", "QtRemoteObjects", "QtScxml", "QtStateMachine",
    "QtTextToSpeech", "QtSpatialAudio", "QtHttpServer", "QtConcurrent", "QtXml", "QtDBus",
)


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "src"))
    from gambipad.cli import main as cli

    icon = BUILD / "gambipad.ico"
    if cli(["icon", str(icon), "--size", "256"]) != 0:
        raise SystemExit("could not write the icon")
    entry = BUILD / "gambipad_entry.py"
    entry.write_text("import sys\nfrom gambipad.cli import main\nsys.exit(main())\n", encoding="utf-8")
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "GambiPad", "--icon", str(icon),
        "--distpath", str(ROOT / "dist"), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
        "--paths", str(ROOT / "src"),
        "--collect-submodules", "gambipad",
        "--collect-all", "vgamepad",  # carries ViGEmClient.dll
        *[arg for module in UNUSED_QT for arg in ("--exclude-module", f"PySide6.{module}")],
        str(entry),
    ]
    shutil.rmtree(ROOT / "dist" / "GambiPad", ignore_errors=True)
    subprocess.check_call(cmd, cwd=ROOT)
    shutil.copy2(icon, ROOT / "dist" / "GambiPad" / "gambipad.ico")
    print(f"built {ROOT / 'dist' / 'GambiPad' / 'GambiPad.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
