from enum import StrEnum


class Exchange(StrEnum):
    RAG_EVENTS = "rag.events"
    RAG_EVENTS_DLX = "rag.events.dlx"


class Queue(StrEnum):
    THREADS = "rag.threads.queue"
    DOCUMENTS = "rag.documents.queue"
    DLQ = "rag.dead.queue"


class RoutingKey(StrEnum):
    THREAD_CLOSED = "rag.thread.closed"
    DOC_UPLOADED = "rag.doc.uploaded"
    DEAD_LETTER = "rag.dead"

    THREAD_BINDING_PATTERN = "rag.thread.*"
    DOC_BINDING_PATTERN = "rag.doc.*"
