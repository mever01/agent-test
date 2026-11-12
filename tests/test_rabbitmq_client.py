import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.broker.rag.producer import RAGProducer
from core.broker.client import RabbitMQClient


@pytest.fixture
def transport(monkeypatch):
    channel = MagicMock(is_closed=False)
    channel.close = AsyncMock()
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    channel.get_exchange = AsyncMock(return_value=exchange)
    connection = MagicMock(is_closed=False)
    connection.channel = AsyncMock(return_value=channel)
    connection.close = AsyncMock()
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr("core.broker.client.aio_pika.connect_robust", connect)
    return RabbitMQClient("amqp://localhost"), connection, channel, exchange, connect


async def test_publish_reuses_connection_and_serializes_json(transport):
    client, connection, channel, exchange, connect = transport
    await client.publish("events", "index", {"text": "Привет"})
    await client.publish("events", "index", {"id": 2})
    connect.assert_awaited_once()
    connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    message = exchange.publish.await_args_list[0].args[0]
    assert json.loads(message.body) == {"text": "Привет"}
    assert exchange.publish.await_args.kwargs == {"routing_key": "index", "mandatory": True}
    channel.declare_exchange.assert_not_called()


async def test_recovers_after_channel_creation_failure(transport):
    client, connection, channel, _, connect = transport
    connection.channel.side_effect = [ConnectionError(), channel]
    with pytest.raises(ConnectionError):
        await client.connect()
    await client.connect()
    connect.assert_awaited_once()
    assert connection.channel.await_count == 2


async def test_recreates_closed_channel(transport):
    client, connection, channel, _, _ = transport
    await client.connect()
    channel.is_closed = True
    replacement = MagicMock(is_closed=False)
    connection.channel.return_value = replacement
    await client.connect()
    assert connection.channel.await_count == 2


async def test_close_connection_even_if_channel_close_fails(transport):
    client, connection, channel, _, _ = transport
    await client.connect()
    channel.close.side_effect = RuntimeError("close failed")
    with pytest.raises(RuntimeError):
        await client.close()
    connection.close.assert_awaited_once()
    await client.close()
    connection.close.assert_awaited_once()


async def test_publish_failure_is_not_retried(transport):
    client, _, _, exchange, _ = transport
    exchange.publish.side_effect = ConnectionError()
    with pytest.raises(ConnectionError):
        await RAGProducer(client, "events").publish_thread_closed(UUID(int=1))
    exchange.publish.assert_awaited_once()


async def test_close_waits_for_publication(transport):
    client, connection, _, exchange, _ = transport
    started, release = asyncio.Event(), asyncio.Event()

    async def publish(*args, **kwargs):
        started.set()
        await release.wait()

    exchange.publish.side_effect = publish
    producer = RAGProducer(client, "events")
    sending = asyncio.create_task(producer.publish_thread_closed(UUID(int=1)))
    await started.wait()
    closing = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    connection.close.assert_not_awaited()
    release.set()
    await asyncio.gather(sending, closing)
    connection.close.assert_awaited_once()
