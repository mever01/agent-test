from uuid import uuid4

from aio_pika import DeliveryMode, Message
from core.broker.client import RabbitMQClient
from pydantic import BaseModel

from core.utils.mixins.logger import LoggerMixin


class RabbitProducer(LoggerMixin):
    def __init__(
        self,
        client: RabbitMQClient,
        exchange_name: str
    ) -> None:
        self._client = client
        self._exchange_name = exchange_name

    async def publish(
        self,
        routing_key: str,
        payload: BaseModel,
    ) -> None:
        message_id = str(uuid4())

        message = Message(
            body=payload.model_dump_json().encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id,
        )

        await self._client.publish_message(self._exchange_name, routing_key, message)

        self.logger.debug(
            "Message published: exchange=%s, routing_key=%s, message_id=%s",
            self._exchange_name,
            routing_key,
            message_id,
        )
