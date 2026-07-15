class Form7Error(Exception):
    """Base exception for expected parser and annotation failures."""


class PdfReadError(Form7Error):
    """Raised when an input PDF cannot be read safely."""


class PdfLimitError(Form7Error):
    """Raised when a configured PDF resource limit is exceeded."""


class OverlayError(Form7Error):
    """Raised when annotation overlays are invalid."""
