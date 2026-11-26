class ScraperError(Exception):
    """An expected scraping failure: the book may well exist, we just could not read the store."""


class BlockedError(ScraperError):
    """The store refused us (HTTP 401/403/429, CAPTCHA, IP restriction)."""


class NetworkError(ScraperError):
    """The store could not be reached or kept failing (timeouts, connection errors, HTTP 5xx)."""