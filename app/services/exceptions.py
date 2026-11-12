class ServiceError(Exception):
    """Базовое исключение прикладных сервисов."""


class ThreadNotFoundError(ServiceError):
    """Почтовый тред не найден."""


class DocumentNotFoundError(ServiceError):
    """Документ не найден."""


class DocumentAccessDeniedError(ServiceError):
    """Доступ к файлу вне разрешенной директории запрещен."""


class LLMTimeoutError(ServiceError):
    """Таймаут обращения к LLM."""


class SecurityViolationError(ServiceError):
    """Блокировка сценария контуром безопасности."""
