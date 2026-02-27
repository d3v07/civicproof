from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).parent

# Allow bare imports used in tests: `from agents...`, `from parsers...`
_worker_src = _root / "services" / "worker" / "src"
if str(_worker_src) not in sys.path:
    sys.path.insert(0, str(_worker_src))
