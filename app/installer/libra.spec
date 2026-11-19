# PyInstaller recipe for Windows and macOS. Run through installer/build.py, or directly:
#     python -m PyInstaller --noconfirm installer/libra.spec
#
# Produces one folder with two programs that share the same libraries:
#     LIBRA(.exe)   the desktop app (no console window)
#     libra-cli(.exe)  the command line for project files (not just "libra": Windows and macOS
#                      file names ignore case, so it would clash with LIBRA)
# On macOS the folder is wrapped as "LIBRA.app".
import sys
from pathlib import Path

SRC = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(SRC))
from randomizer import __version__  # noqa: E402

MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"
ICON = str(SRC / "installer" / ("icon.ico" if WIN else "icon.png"))

# Not needed at run time; keeps the download small.
EXCLUDES = ["tkinter", "streamlit", "IPython", "jupyter", "notebook", "pytest", "scipy", "sympy",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtDesigner", "gurobipy",
            "PyQt5", "PyQt6", "PySide2",                        # other Qt bindings in the build Python
            # optional extras of pandas/matplotlib that the app never uses
            "numba", "llvmlite", "pyarrow", "cryptography", "lxml", "zmq", "sqlalchemy", "bs4",
            "html5lib", "fsspec", "tables", "pythoncom", "pywintypes", "win32com", "win32api", "Pythonwin"]

gui = Analysis([str(SRC / "installer" / "entry_gui.py")], pathex=[str(SRC)],
               datas=[(str(SRC / "randomizer_gui" / "assets"), "randomizer_gui/assets"),
                      (str(SRC / "LICENSE"), "."), (str(SRC / "THIRD_PARTY_LICENSES.md"), ".")],
               hiddenimports=["PySide6.QtSvg", "PySide6.QtPrintSupport", "matplotlib.backends.backend_agg"],
               excludes=EXCLUDES, noarchive=False)
cli = Analysis([str(SRC / "installer" / "entry_cli.py")], pathex=[str(SRC)],
               hiddenimports=["matplotlib.backends.backend_agg"],
               excludes=EXCLUDES + ["PySide6", "randomizer_gui"], noarchive=False)

# Qt's software OpenGL fallback (20 MB): the app draws no OpenGL
gui.binaries = [b for b in gui.binaries if "opengl32sw" not in b[0].lower()]

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="LIBRA",
              console=False, icon=ICON, upx=False, argv_emulation=False)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="libra-cli",
              console=True, icon=ICON, upx=False)

coll = COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,
               name="LIBRA", upx=False)

if MAC:
    app = BUNDLE(
        coll, name="LIBRA.app", icon=ICON, bundle_identifier="cz.nudz.libra",
        version=__version__,
        info_plist={
            "CFBundleName": "LIBRA",
            "CFBundleDisplayName": "LIBRA",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,          # follow light / dark mode
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "LIBRA project",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["cz.nudz.libra.project"],
            }],
            "UTExportedTypeDeclarations": [{
                "UTTypeIdentifier": "cz.nudz.libra.project",
                "UTTypeDescription": "LIBRA project",
                "UTTypeConformsTo": ["public.json", "public.data"],
                "UTTypeTagSpecification": {"public.filename-extension": ["libra"]},
            }],
        })
