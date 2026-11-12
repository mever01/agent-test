import asyncio
import json
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection, AbstractMessage


class RabbitMQClient:
    """AMQP-транспорт. Топология объявляется отдельно от клиента.

    Экземпляр используется в одном event loop. Публикации и закрытие
    сериализуются, чтобы канал не закрывался во время отправки.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._lock = asyncio.Lock()

    async def _ensure_channel(self) -> AbstractChannel:
        """Вызывается под lock; восстанавливает отсутствующий канал."""
        connection = self._connection
        if connection is None or connection.is_closed:
            connection = await aio_pika.connect_robust(self._url)
            self._connection = connection
            self._channel = None

        channel = self._channel
        if channel is None or channel.is_closed:
            channel = await connection.channel(
                publisher_confirms=True,
                on_return_raises=True,
            )
            self._channel = channel
        return channel

    async def get_channel(self) -> AbstractChannel:
        """Возвращает активный AMQP-канал, создавая его при необходимости."""
        async with self._lock:
            return await self._ensure_channel()

    async def connect(self) -> None:
        """Открывает соединение и канал; повторный вызов безопасен."""
        async with self._lock:
            await self._ensure_channel()

    async def publish(
        self,
        exchange_name: str,
        routing_key: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Публикует JSON с подтверждением и ошибкой при отсутствии маршрута.

        Exchange должен существовать. Исключения транспорта передаются вызывающему
        коду; автоматического повтора публикации с неопределённым исходом нет.
        """
        message = aio_pika.Message(
            body=json.dumps(dict(payload), ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self.publish_message(exchange_name, routing_key, message)

    async def publish_message(
        self, exchange_name: str, routing_key: str, message: AbstractMessage,
    ) -> None:
        async with self._lock:
            channel = await self._ensure_channel()
            exchange = await channel.get_exchange(exchange_name, ensure=False)
            await exchange.publish(message, routing_key=routing_key, mandatory=True)

    async def close(self) -> None:
        """Освобождает ресурсы, в том числе после частичной инициализации."""
        async with self._lock:
            channel, connection = self._channel, self._connection
            self._channel = None
            self._connection = None
            try:
                if channel is not None and not channel.is_closed:
                    await channel.close()
            finally:
                if connection is not None and not connection.is_closed:
                    await connection.close()

    async def __aenter__(self) -> "RabbitMQClient":
        try:
            await self.connect()
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
