
from abc import ABC, abstractmethod

from aio_pika.abc import AbstractIncomingMessage, AbstractQueue
from pydantic import BaseModel, ValidationError

from core.utils.mixins.logger import LoggerMixin


class RabbitConsumer[MessageT: BaseModel](LoggerMixin, ABC):
    message_type: type[MessageT]

    def __init__(self, queue: AbstractQueue) -> None:
        self._queue = queue

    async def start(self) -> None:
        self.logger.info(
            "Consumer started: queue=%s",
            self._queue.name,
        )

        try:
            # можно добавить async с помощью Semaphore и prefetch rabbit
            # сейчас handle выполняются один за другим
            async with self._queue.iterator() as messages:
                async for message in messages:
                    await self._on_message(message)
        finally:
            self.logger.info(
                "Consumer stopped: queue=%s",
                self._queue.name,
            )

    async def _on_message(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        try:
            payload = self.message_type.model_validate_json(
                message.body,
            )

            await self.handle(payload)

        except ValidationError:
            self.logger.error(
                "Message validation failed: queue=%s, message_id=%s",
                self._queue.name,
                message.message_id,
            )
            await message.reject(requeue=False)

        except Exception:
            self.logger.exception(
                "Message processing failed: queue=%s, message_id=%s",
                self._queue.name,
                message.message_id,
            )

            # TODO: Extend error handling with retry policies,
            # error classification and dead-letter routing.
            await message.reject(requeue=False)

        else:
            await message.ack()

    @abstractmethod
    async def handle(self, message: MessageT) -> None:
        """Process a validated domain message."""
        pass
