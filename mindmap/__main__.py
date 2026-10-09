import os
import sys

# `python -m` puts the current folder first on the import path. Mind Map only
# reads the folder it checks, so that folder must not be able to shadow the
# modules imported from here on (a `json.py` in it would otherwise run).
# Python has already imported a few modules of its own by now: for a folder
# you do not trust, use the `mindmap` command or `python -I run_mindmap.py`.
if sys.path and sys.path[0] in ("", os.getcwd()):
    del sys.path[0]

from .cli import main  # noqa: E402

sys.exit(main())
