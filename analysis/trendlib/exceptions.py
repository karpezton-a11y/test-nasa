"""Named data-quality exceptions (decision SCI-02). The backend maps exactly these to INSUFFICIENT_DATA."""


class InsufficientDataError(ValueError):
    """Too few valid observations or too short a record for a reliable trend test."""


class DataQualityError(ValueError):
    """Input violates a data rule (duplicate dates, non-finite values, wrong frequency)."""
