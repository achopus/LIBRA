"""Entry point of the packaged command-line tool `libra-cli` (PyInstaller)."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from randomizer.cli import main
    main()
