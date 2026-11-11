import os
import sys

# a windowed build (Windows / macOS app) has no console: give print() somewhere to go
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))

from hostrix.__main__ import main  # noqa: E402

sys.exit(main())
