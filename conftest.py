"""Permit source-tree tests before editable installation."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path[:0] = [str(ROOT / "model/src"), str(ROOT / "algorithm/src")]
