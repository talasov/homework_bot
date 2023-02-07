class ServerError(Exception):
    """Исключение, если битая ссылка."""

    pass


class MissingVariable(Exception):
    pass


class UnknownStatus(Exception):
    pass


class KeyNotFound(Exception):
    pass


class ConnectionError(Exception):
    pass


class Timeout(Exception):
    pass


class RequestException(Exception):
    pass
