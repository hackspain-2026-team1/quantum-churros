from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from .models import OutboxEvent


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)


hub = EventHub()


async def run_outbox_worker(engine: Any, poll_seconds: float) -> None:
    while True:
        events: list[dict[str, Any]] = []
        with Session(engine) as session:
            rows = session.exec(select(OutboxEvent).where(OutboxEvent.status == "pending").order_by(OutboxEvent.created_at).limit(100)).all()
            for row in rows:
                row.attempts += 1
                row.status = "delivered"
                row.delivered_at = datetime.now(UTC)
                session.add(row)
                events.append({"id": row.id, "type": row.event_type, "aggregate_id": row.aggregate_id, "created_at": row.created_at.isoformat(), "payload": row.payload_json})
            session.commit()
        for event in events:
            await hub.publish(event)
        await asyncio.sleep(poll_seconds)
