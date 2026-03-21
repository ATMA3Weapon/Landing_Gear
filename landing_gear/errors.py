from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ServiceError(Exception):
    message: str
    status: int = 500
    code: str = 'service_error'
    details: object | None = None

    def __str__(self) -> str:
        return self.message


class BadRequestError(ServiceError):
    def __init__(self, message: str, *, code: str = 'bad_request', details: object | None = None) -> None:
        super().__init__(message=message, status=400, code=code, details=details)


class UnauthorizedError(ServiceError):
    def __init__(self, message: str = 'unauthorized', *, code: str = 'unauthorized') -> None:
        super().__init__(message=message, status=401, code=code)


class ForbiddenError(ServiceError):
    def __init__(self, message: str = 'forbidden', *, code: str = 'forbidden') -> None:
        super().__init__(message=message, status=403, code=code)


class NotFoundError(ServiceError):
    def __init__(self, message: str = 'not found', *, code: str = 'not_found') -> None:
        super().__init__(message=message, status=404, code=code)


class ConflictError(ServiceError):
    def __init__(self, message: str, *, code: str = 'conflict', details: object | None = None) -> None:
        super().__init__(message=message, status=409, code=code, details=details)
