import enum


class UserRole(str, enum.Enum):
    """Роли пользователей в системе для контроля доступа (RBAC)."""
    MANAGER = "manager"
    ADMIN = "admin"


class ThreadStatus(str, enum.Enum):
    """Статусы цепочки писем (активна / закрыта)."""
    ACTIVE = "active"
    CLOSED = "closed"
