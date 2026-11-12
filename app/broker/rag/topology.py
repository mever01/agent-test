
from dataclasses import dataclass

from aio_pika import ExchangeType
from aio_pika.abc import AbstractExchange, AbstractQueue

from core.broker.topology import RabbitTopology

from .constants import Exchange, Queue, RoutingKey


@dataclass(frozen=True)
class RAGExchanges:
    events: AbstractExchange
    dlx: AbstractExchange


@dataclass(frozen=True)
class RAGQueues:
    threads: AbstractQueue
    documents: AbstractQueue
    dlq: AbstractQueue


@dataclass(frozen=True)
class RAGTopologyResources:
    exchanges: RAGExchanges
    queues: RAGQueues


class RAGTopology(RabbitTopology[RAGTopologyResources]):
    async def setup(self) -> RAGTopologyResources:
        # Dead Letter Exchange and Queue
        dlx = await self.declare_exchange(
            name=Exchange.RAG_EVENTS_DLX,
            exchange_type=ExchangeType.DIRECT,
        )

        dlq = await self.declare_queue(
            name=Queue.DLQ,
        )

        await self.bind(
            queue=dlq,
            exchange=dlx,
            routing_key=RoutingKey.DEAD_LETTER,
        )

        # Main Topic Exchange
        events = await self.declare_exchange(
            name=Exchange.RAG_EVENTS,
            exchange_type=ExchangeType.TOPIC,
        )

        # Working Queues
        dlq_arguments = {
            "x-dead-letter-exchange": dlx.name,
            "x-dead-letter-routing-key": RoutingKey.DEAD_LETTER,
        }

        threads = await self.declare_queue(
            name=Queue.THREADS,
            arguments=dlq_arguments,
        )

        documents = await self.declare_queue(
            name=Queue.DOCUMENTS,
            arguments=dlq_arguments,
        )

        # Bindings
        await self.bind(
            queue=threads,
            exchange=events,
            routing_key=RoutingKey.THREAD_BINDING_PATTERN,
        )

        await self.bind(
            queue=documents,
            exchange=events,
            routing_key=RoutingKey.DOC_BINDING_PATTERN,
        )

        return RAGTopologyResources(
            exchanges=RAGExchanges(
                events=events,
                dlx=dlx,
            ),
            queues=RAGQueues(
                threads=threads,
                documents=documents,
                dlq=dlq,
            ),
        )
