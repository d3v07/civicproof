"""Source-specific parsers for transforming raw artifacts into structured data."""

from .doj import parse_doj_press_release
from .oversight import parse_ig_report
from .sec_edgar import parse_sec_filing
from .usaspending import parse_usaspending_award

__all__ = [
    "parse_usaspending_award",
    "parse_doj_press_release",
    "parse_sec_filing",
    "parse_ig_report",
]
