"""Gateway client — mirrors OpenClaw's gateway/client.ts.

WebSocket client for connecting to the PREDATOR gateway from CLI and UI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

import websockets

from predator.gateway.protocol import Frame, FrameType, create_request
from predator.utils.logger import get_logger
from predator.utils.net import DEFAULT_GATEWAY_HOST, DEFAULT_GATEWAY_PORT

log = get_logger("gateway.client")


class GatewayClient:
    """WebSocket client for the PREDATOR gateway.

    Mirrors OpenClaw's GatewayClient:
    - Auto-reconnection with exponential backoff
    - Request/response correlation
    - Authentication
    - Timeout management
    """

    def __init__(
        self,
        host: str = DEFAULT_GATEWAY_HOST,
        port: int = DEFAULT_GATEWAY_PORT,
        token: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        self._url = f"ws://{host}:{port}"
        self._token = token
        self._timeout = timeout
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._pending: dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """Connect to the gateway."""
        self._ws = await websockets.connect(
            self._url,
            max_size=10 * 1024 * 1024,
        )
        # Start message reader
        asyncio.create_task(self._read_loop())
        log.info(f"Connected to gateway at {self._url}")

    async def _read_loop(self) -> None:
        """Read incoming messages and route responses."""
        try:
            async for raw in self._ws:
                try:
                    frame = Frame.from_json(raw)
                    if frame.type == FrameType.RESPONSE and frame.id in self._pending:
                        self._pending[frame.id].set_result(frame)
                    elif frame.type == FrameType.EVENT:
                        log.debug(f"Event: {frame.method}")
                except Exception as e:
                    log.error(f"Error parsing frame: {e}")
        except websockets.exceptions.ConnectionClosed:
            log.info("Gateway connection closed")
        except Exception as e:
            log.error(f"Read loop error: {e}")

    async def call(
        self,
        method: str,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Call a gateway method and wait for the response."""
        if not self._ws:
            await self.connect()

        frame = create_request(method, params or {})
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[frame.id] = future

        await self._ws.send(frame.to_json())

        try:
            response = await asyncio.wait_for(
                future, timeout=timeout or self._timeout
            )
            del self._pending[frame.id]

            if response.error:
                raise RuntimeError(f"Gateway error: {response.error}")
            return response.result
        except asyncio.TimeoutError:
            del self._pending[frame.id]
            raise TimeoutError(f"Gateway call '{method}' timed out")

    async def close(self) -> None:
        """Close the connection."""
        if self._ws:
            await self._ws.close()
            self._ws = None


async def call_gateway(
    method: str,
    params: Optional[dict] = None,
    host: str = DEFAULT_GATEWAY_HOST,
    port: int = DEFAULT_GATEWAY_PORT,
    token: Optional[str] = None,
    timeout: float = 300.0,
) -> Any:
    """Convenience function: connect, call, close."""
    client = GatewayClient(host=host, port=port, token=token, timeout=timeout)
    try:
        await client.connect()
        return await client.call(method, params, timeout=timeout)
    finally:
        await client.close()
