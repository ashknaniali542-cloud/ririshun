"""Portable method demo. All fixtures are generated at runtime, with no business input."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '05_原始Skill/rrs-operations-learning/scripts'))
from synthetic_demo import main

if __name__ == '__main__':
    raise SystemExit(main())
