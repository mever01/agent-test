from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.dto.db_mail import (
    MailCursor,
    MailFilters,
)


class MailListQuery(MailFilters):
    account_id: UUID | None = None
    before_date: AwareDatetime | None = None
    before_id: UUID | None = None
    limit: int = Field(25, ge=1, le=100)

    @model_validator(mode="after")
    def validate_cursor(self) -> Self:
        if (self.before_date is None) != (self.before_id is None):
            raise ValueError("Для следующей страницы укажите дату и ID письма.")
        return self

    def cursor(self) -> MailCursor | None:
        if self.before_date is None or self.before_id is None:
            return None
        return MailCursor(date=self.before_date, email_id=self.before_id)
