import enum


class UserRole(str, enum.Enum):
    """Роли пользователей в системе для контроля доступа (RBAC)."""
    MANAGER = "manager"
    ADMIN = "admin"


class GmailConnectionStatus(enum.StrEnum):
    PENDING = "pending"
    SYNCING = "syncing"
    CONNECTED = "connected"
    SYNC_ERROR = "sync_error"
    REAUTH_REQUIRED = "reauth_required"
    DISCONNECTED = "disconnected"


class AccountSource(enum.StrEnum):
    GMAIL = "gmail"
