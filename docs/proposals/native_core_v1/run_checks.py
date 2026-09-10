"""Run this proposal's tests against the existing PIX source without installing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PROPOSAL_ROOT = Path(__file__).resolve().parent
PIX_ROOT = PROPOSAL_ROOT.parents[2]
sys.path[:0] = [str(PROPOSAL_ROOT), str(PIX_ROOT / "src")]

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(PROPOSAL_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
