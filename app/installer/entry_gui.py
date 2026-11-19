"""Entry point of the packaged desktop app (PyInstaller)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()          # solver child processes start through this executable
    from randomizer_gui.app import main
    sys.exit(main())
