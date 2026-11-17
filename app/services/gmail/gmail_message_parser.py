import logging
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses
from html.parser import HTMLParser

from app.dto.gmail import ImportedGmailMessage
from app.external_api_clients.gmail.schemas import (
    GmailMessage,
    GmailPart,
    GmailPartBody,
)

logger = logging.getLogger(__name__)

MAX_TEXT_PART_BYTES = 512 * 1024
MAX_ENCODED_PART_LENGTH = ((MAX_TEXT_PART_BYTES + 2) // 3) * 4
_EXCLUDED_LABELS = {"DRAFT", "SPAM", "TRASH"}
_TEXT_TYPES = {"text/plain", "text/html"}
_ATTACHMENT_TYPES = {"message/rfc822"}
_BLOCK_TAGS = {"br", "div", "li", "p", "tr"}
_HIDDEN_TAGS = {"head", "script", "style"}

type TextPartLoader = Callable[[str, str], Awaitable[GmailPartBody]]


def is_importable(message: GmailMessage) -> bool:
    return _EXCLUDED_LABELS.isdisjoint(message.label_ids)


def message_date(message: GmailMessage) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
        milliseconds=message.internal_date_ms,
    )


async def parse_message(
    message: GmailMessage, mailbox: str, load_text_part: TextPartLoader,
) -> ImportedGmailMessage:
    headers = {
        header.name.lower(): header.value
        for header in message.payload.headers
    } if message.payload else {}
    try:
        subject = str(make_header(decode_header(headers.get("subject", ""))))
    except (UnicodeError, LookupError, ValueError):
        subject = headers.get("subject", "")
    sender = _first_address(headers.get("from", ""))
    if not sender and "SENT" in message.label_ids:
        sender = mailbox
    recipient = _first_address(headers.get("to", "")) or mailbox
    body = await _part_text(message.payload, message.id, load_text_part)
    if body is None and message.payload is not None:
        logger.debug("Gmail message has no supported text part")
    return ImportedGmailMessage(
        message.id, sender, recipient, message_date(message),
        _clean_text(subject), _clean_text(body or "")[:MAX_TEXT_PART_BYTES],
    )


def _first_address(value: str) -> str:
    return next(
        (
            address.lower()
            for _, address in getaddresses([value])
            if "@" in address and len(address) <= 255 and "\x00" not in address
        ),
        "",
    )


def _clean_text(text: str) -> str:
    return text.replace("\x00", "").strip()


async def _part_text(
    part: GmailPart | None, message_id: str, load_text_part: TextPartLoader,
) -> str | None:
    if part is None or part.filename or part.mime_type in _ATTACHMENT_TYPES:
        return None
    headers = Message()
    for header in part.headers:
        headers[header.name] = header.value
    if headers.get_content_disposition() == "attachment":
        return None
    if part.mime_type == "multipart/alternative":
        candidates = sorted(
            part.parts, key=lambda item: item.mime_type != "text/plain",
        )
        for child in candidates:
            content = await _part_text(child, message_id, load_text_part)
            if content:
                return content
        return None
    if part.parts and part.mime_type.startswith("multipart/"):
        content = [
            await _part_text(child, message_id, load_text_part) for child in part.parts
        ]
        return "\n\n".join(item for item in content if item) or None
    body = part.body
    if part.mime_type not in _TEXT_TYPES or not body or body.size > MAX_TEXT_PART_BYTES:
        return None
    if body.attachment_id and body.data is None:
        body = await load_text_part(message_id, body.attachment_id)
    data = body.data
    if (
        not data or body.size > MAX_TEXT_PART_BYTES
        or len(data) > MAX_ENCODED_PART_LENGTH
    ):
        return None
    try:
        padded = data + "=" * (-len(data) % 4)
        decoded = b64decode(padded, altchars=b"-_", validate=True)
    except (Base64Error, ValueError):
        logger.warning("Gmail text part has invalid base64")
        return None
    if len(decoded) > MAX_TEXT_PART_BYTES:
        return None

    charset = headers.get_content_charset() or "utf-8"
    try:
        text = decoded.decode(charset, errors="replace")
    except LookupError:
        text = decoded.decode("utf-8", errors="replace")
    if part.mime_type == "text/html":
        parser = _PlainHTML()
        try:
            parser.feed(text)
            parser.close()
        except (ValueError, AssertionError):
            logger.warning("Gmail HTML part could not be parsed")
            return None
        return "".join(parser.chunks).strip()
    return text.strip()


class _PlainHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._hidden = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in _HIDDEN_TAGS:
            self._hidden += 1
        elif tag in _BLOCK_TAGS and not self._hidden:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_TAGS and self._hidden:
            self._hidden -= 1
        elif tag in _BLOCK_TAGS and not self._hidden:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self.chunks.append(data)
