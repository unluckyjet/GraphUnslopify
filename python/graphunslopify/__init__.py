"""Render-time checks for figures produced by GraphUnslopify.

The MCP server checks a spec. This checks the picture. Import it in a generated
script and it reports what a reviewer would complain about, before you submit.

    from graphunslopify import inspect_figure

    report = inspect_figure(fig, target_width_in=3.4)
    print(report)
"""

from .build import Figure, Kind, SpecError
from .colour import ciede2000, distance, simulate, worst_case_distance
from .describe import profile
from .inspect import Finding, Report, inspect_figure
from .lockfile import appearance
from .provenance import ProvenanceError, read_provenance

__all__ = [
    "Figure",
    "Finding",
    "Kind",
    "ProvenanceError",
    "Report",
    "SpecError",
    "appearance",
    "ciede2000",
    "distance",
    "inspect_figure",
    "profile",
    "read_provenance",
    "simulate",
    "worst_case_distance",
]

__version__ = "0.7.0"
