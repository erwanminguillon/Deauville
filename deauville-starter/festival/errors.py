class FestivalError(Exception):
    """Base class for errors that can be shown to a festival organiser."""


class InvalidValue(FestivalError):
    """A value does not satisfy a festival rule."""


class NotFound(FestivalError):
    """A referenced festival object does not exist."""


class Conflict(FestivalError):
    """A change conflicts with the existing festival schedule."""


class StorageError(FestivalError):
    """Festival data could not be read or written."""
