from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Session:
    user_id: UUID
    expires_at: float
