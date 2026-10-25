"""DocProof: a friendly manuscript proofreader that never rewrites your originals.

Docs get read, flagged, and reported. Suggestions (if you ask for them) land in
an annotated patch file only. Your source file is never modified.

Copyright (c) 2026 Asdale Dynamics, LLC
"""

from .rules import RULES, Finding, check_text, load_extra_typos

__version__ = "0.1.0"

__all__ = [
    "RULES",
    "Finding",
    "__version__",
    "check_text",
    "load_extra_typos",
]
