"""Run Meinya Mind Map straight from a checkout, without installing it.

    python -I run_mindmap.py check /path/to/repo

`python -m mindmap` puts the current folder first on the import path, so
running it from inside a repo you do not trust would let that repo's files
shadow Python modules. This launcher adds only its own folder, and `-I`
keeps the current folder and PYTHON* variables out.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mindmap.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
