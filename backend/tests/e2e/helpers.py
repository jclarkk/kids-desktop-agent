from __future__ import annotations

import json
from typing import Any

from websockets.asyncio.client import ClientConnection


class WsClient:
    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.initial_state: dict[str, Any] | None = None

    async def recv(self) -> dict[str, Any]:
        raw = await self.ws.recv()
        return json.loads(str(raw))

    async def recv_until(self, msg_type: str, *, limit: int = 40) -> dict[str, Any]:
        last: dict[str, Any] = {}
        for _ in range(limit):
            last = await self.recv()
            if last.get("type") == msg_type:
                return last
        raise AssertionError(f"Did not receive type={msg_type!r}; last={last!r}")

    async def send(self, payload: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(payload))

    async def request(self, payload: dict[str, Any], expect: str) -> dict[str, Any]:
        await self.send(payload)
        return await self.recv_until(expect)

    async def drain(self, *, max_msgs: int = 20) -> None:
        """Read and discard pending messages without blocking long."""
        import asyncio

        for _ in range(max_msgs):
            try:
                await asyncio.wait_for(self.ws.recv(), timeout=0.05)
            except (TimeoutError, asyncio.TimeoutError):
                return
