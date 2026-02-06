"""Exceptions for Belgian e-Procurement connector."""


class EProcurementCredentialsError(Exception):
    """Raised when OAuth credentials are missing or invalid."""

    pass


class EProcurementEndpointNotConfiguredError(NotImplementedError):
    """Raised when credentials are valid but endpoint mapping is not yet confirmed."""

    pass
