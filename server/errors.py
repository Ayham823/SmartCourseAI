"""Public sanitized application errors; internal exception text stays private."""


class AppError(Exception):
    def __init__(self, message, code="service_unavailable", status=503):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
