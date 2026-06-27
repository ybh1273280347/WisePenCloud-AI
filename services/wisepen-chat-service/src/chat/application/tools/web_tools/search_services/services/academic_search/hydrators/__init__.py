from __future__ import annotations

from .models import (
    HydratedPaper,
    HydratedPaperAuthor,
    HydratedPaperOpenAccess,
    OpenAlexFailureReason,
)
from .paper import PaperHydrator

__all__ = [
    "HydratedPaper",
    "HydratedPaperAuthor",
    "HydratedPaperOpenAccess",
    "OpenAlexFailureReason",
    "PaperHydrator",
]
