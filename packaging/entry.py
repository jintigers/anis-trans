"""PyInstaller 진입점: anis-trans(.exe) 하나로 CLI와 GUI(--gui)를 모두 실행한다."""
import multiprocessing
import sys

from anis_trans.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
