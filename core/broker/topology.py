
from abc import ABC, abstractmethod
from typing import Any

from aio_pika import ExchangeType
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractQueue,
)

from core.utils.mixins.logger import LoggerMixin


class RabbitTopology[ResourcesT](LoggerMixin, ABC):
    def __init__(self, channel: AbstractChannel) -> None:
        self._channel = channel

    async def declare_exchange(
        self,
        name: str,
        exchange_type: ExchangeType = ExchangeType.DIRECT,
        durable: bool = True,
    ) -> AbstractExchange:
        exchange = await self._channel.declare_exchange(
            name=name,
            type=exchange_type,
            durable=durable,
        )

        self.logger.info(
            "Exchange declared: name=%s, type=%s",
            name,
            exchange_type,
        )

        return exchange

    async def declare_queue(
        self,
        name: str,
        durable: bool = True,
        arguments: dict[str, Any] | None = None,
    ) -> AbstractQueue:
        queue = await self._channel.declare_queue(
            name=name,
            durable=durable,
            arguments=arguments,
        )

        self.logger.info(
            "Queue declared: name=%s",
            name,
        )

        return queue

    async def bind(
        self,
        queue: AbstractQueue,
        exchange: AbstractExchange,
        routing_key: str,
    ) -> None:
        await queue.bind(
            exchange,
            routing_key=routing_key,
        )

        self.logger.info(
            "Queue bound: queue=%s, exchange=%s, routing_key=%s",
            queue.name,
            exchange.name,
            routing_key,
        )

    @abstractmethod
    async def setup(self) -> ResourcesT:
        """Declare domain topology and return typed resources."""
        pass