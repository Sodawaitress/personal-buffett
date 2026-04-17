"""Shared path bootstrap for directly executed legacy scripts."""

from __future__ import annotations

import os
import sys


def bootstrap_paths():
    script_dir = os.path.dirname(__file__)
    root_dir = os.path.dirname(script_dir)

    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    return root_dir, script_dir
