"""Build the installable app.

    python installer/build.py                 build, test and package
    python installer/build.py --no-package    build and test only

Windows: installer/output/LIBRA-Setup-<version>.exe   (PyInstaller + Inno Setup 6)
macOS:   installer/output/LIBRA-<version>-macOS-<arch>.dmg   (PyInstaller + hdiutil)

Needs the app's packages and PyInstaller in the Python that runs this script:
    pip install -r requirements.txt "pyinstaller>=6.11"
Windows also needs Inno Setup 6 (winget install JRSoftware.InnoSetup).

macOS signing (optional, but without it Gatekeeper asks users to confirm the first start):
    export MACOS_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
    then notarize the .dmg with: xcrun notarytool submit <dmg> --keychain-profile <profile> --wait
                                  xcrun stapler staple <dmg>
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

INST = Path(__file__).resolve().parent
SRC = INST.parent
BUILD = INST / "build"
DIST = BUILD / "dist"
WORK = BUILD / "work"
OUT = INST / "output"
MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"


def step(msg):
    print(f"\n== {msg}", flush=True)


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def remove_tree(path: Path):
    """Delete a folder; virus scanners briefly lock new files, so retry, then move aside."""
    for _ in range(5):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(2)
    aside = path.with_name(f"{path.name}_old_{int(time.time())}")
    path.rename(aside)
    shutil.rmtree(aside, ignore_errors=True)


def app_version() -> str:
    text = (SRC / "randomizer" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def find_iscc() -> Path:
    for base in [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramFiles", "")]:
        p = Path(base) / ("Programs/Inno Setup 6" if "Local" in base else "Inno Setup 6") / "ISCC.exe"
        if p.exists():
            return p
    found = shutil.which("iscc")
    if found:
        return Path(found)
    sys.exit("Inno Setup 6 not found. Install it with:  winget install JRSoftware.InnoSetup")


def check_requirements():
    missing = []
    for mod in ("PySide6", "highspy", "numpy", "pandas", "matplotlib", "openpyxl", "PyInstaller"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.exit(f"Missing packages: {', '.join(missing)}.\n"
                 f'Install with:  pip install -r requirements.txt "pyinstaller>=6.11"')


def app_folder() -> Path:
    return DIST / ("LIBRA.app" if MAC else "LIBRA")


def program(name: str) -> Path:
    if MAC:
        return app_folder() / "Contents" / "MacOS" / name
    return app_folder() / (name + (".exe" if WIN else ""))


def smoke_test():
    """Use the built programs the way a user would."""
    cli, gui = program("libra-cli"), program("LIBRA")
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "smoke.libra"
        run([cli, "new", proj, "--example", "rat-crossover"])
        run([cli, "run", proj, "--time-limit", "8", "--seed", "11"])     # solver in a child process
        run([cli, "export", proj, "--format", "xlsx", "--png", "--out", tmp])
        made = sorted(p.name for p in Path(tmp).iterdir())
        print("  files:", ", ".join(made))
        assert any(n.endswith(".xlsx") for n in made) and any(n.endswith(".png") for n in made)
        report = Path(tmp) / "gui_selftest.txt"
        run([gui, "--self-test", report], timeout=180)
        print("  " + report.read_text(encoding="utf-8").strip().replace("\n", "\n  "))
        assert report.read_text(encoding="utf-8").startswith("OK")


def package_windows(version: str) -> Path:
    iscc = find_iscc()
    run([iscc, f"/DAppVersion={version}", f"/DSourceDir={app_folder()}", "/Q", INST / "LIBRA.iss"])
    return OUT / f"LIBRA-Setup-{version}.exe"


def package_mac(version: str) -> Path:
    app = app_folder()
    identity = os.environ.get("MACOS_SIGN_IDENTITY")
    if identity:
        step("Signing the app")
        run(["codesign", "--deep", "--force", "--options", "runtime", "--timestamp", "--sign", identity, app])
        run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])
    else:
        print("  (not signed: set MACOS_SIGN_IDENTITY to sign; see the top of this file)")
    arch = platform.machine()
    dmg = OUT / f"LIBRA-{version}-macOS-{arch}.dmg"
    stage = BUILD / "dmg"
    remove_tree(stage)
    stage.mkdir(parents=True)
    run(["ditto", app, stage / app.name])
    (stage / "Applications").symlink_to("/Applications")
    if dmg.exists():
        dmg.unlink()
    for attempt in range(3):            # hdiutil sometimes fails with "Resource busy"; retry
        try:
            run(["hdiutil", "create", "-volname", f"LIBRA {version}", "-srcfolder", stage,
                 "-ov", "-format", "UDZO", dmg])
            break
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            time.sleep(10)
    if identity:
        run(["codesign", "--force", "--timestamp", "--sign", identity, dmg])
    return dmg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-package", action="store_true", help="build and test, but make no installer")
    ap.add_argument("--no-test", action="store_true")
    args = ap.parse_args()
    if not (WIN or MAC):
        print("Note: only Windows and macOS installers are made; Linux builds the folder only.")
    check_requirements()
    version = app_version()
    OUT.mkdir(exist_ok=True)

    step(f"Building LIBRA {version} with PyInstaller")
    remove_tree(DIST)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST,
         "--workpath", WORK, INST / "libra.spec"], cwd=SRC)
    size = sum(f.stat().st_size for f in app_folder().rglob("*") if f.is_file()) / 1e6
    print(f"  {app_folder()}  ({size:.0f} MB)")

    if not args.no_test:
        step("Smoke test of the built programs")
        smoke_test()

    if args.no_package or not (WIN or MAC):
        print(f"\nDone (no installer): {app_folder()}")
        return
    step("Packaging")
    out = package_windows(version) if WIN else package_mac(version)
    print(f"\nDone: {out}  ({out.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
