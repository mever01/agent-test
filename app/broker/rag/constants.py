from enum import StrEnum


class Exchange(StrEnum):
    RAG_EVENTS = "rag.events"
    RAG_EVENTS_DLX = "rag.events.dlx"


class Queue(StrEnum):
    DOCUMENTS = "rag.documents.queue"
    DLQ = "rag.dead.queue"


class RoutingKey(StrEnum):
    DOC_UPLOADED = "rag.doc.uploaded"
    DEAD_LETTER = "rag.dead"

    DOC_BINDING_PATTERN = "rag.doc.*"
