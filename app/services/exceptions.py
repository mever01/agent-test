class ServiceError(Exception):
    """Базовое исключение прикладных сервисов."""


class ThreadNotFoundError(ServiceError):
    """Почтовый тред не найден."""


class EmailNotFoundError(ServiceError):
    """Письмо отсутствует или недоступно владельцу."""


class DocumentNotFoundError(ServiceError):
    """Документ не найден."""


class DocumentAccessDeniedError(ServiceError):
    """Доступ к файлу вне разрешенной директории запрещен."""


class LLMTimeoutError(ServiceError):
    """Таймаут обращения к LLM."""


class SecurityViolationError(ServiceError):
    """Блокировка сценария контуром безопасности."""


class GmailAccountNotFound(ServiceError):
    """Gmail-аккаунт отсутствует или недоступен владельцу."""


class GmailConnectionConflict(ServiceError):
    """Настройки подключения изменились или требуют уточнения."""


class GmailLeaseLost(ServiceError):
    """Проход синхронизации больше не владеет подключением."""
