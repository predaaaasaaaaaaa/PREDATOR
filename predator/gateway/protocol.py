"""Gateway protocol — mirrors OpenClaw's gateway/protocol/ module.

Defines frame types, message validation, and the WebSocket protocol.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FrameType(str, Enum):
    """WebSocket frame types."""

    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"


@dataclass
class Frame:
    """A WebSocket protocol frame."""

    type: FrameType
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    is_final: bool = True

    def to_json(self) -> str:
        data: dict[str, Any] = {
            "type": self.type.value,
            "id": self.id,
        }
        if self.method:
            data["method"] = self.method
        if self.params:
            data["params"] = self.params
        if self.result is not None:
            data["result"] = self.result
        if self.error:
            data["error"] = self.error
        data["is_final"] = self.is_final
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, data: str) -> "Frame":
        parsed = json.loads(data)
        return cls(
            type=FrameType(parsed.get("type", "request")),
            id=parsed.get("id", str(uuid.uuid4())),
            method=parsed.get("method", ""),
            params=parsed.get("params", {}),
            result=parsed.get("result"),
            error=parsed.get("error"),
            is_final=parsed.get("is_final", True),
        )


def create_request(method: str, params: Optional[dict] = None) -> Frame:
    return Frame(type=FrameType.REQUEST, method=method, params=params or {})


def create_response(request_id: str, result: Any = None, error: str = None) -> Frame:
    return Frame(
        type=FrameType.RESPONSE,
        id=request_id,
        result=result,
        error=error,
    )


def create_event(method: str, data: Any = None) -> Frame:
    return Frame(type=FrameType.EVENT, method=method, result=data)


# Protocol version
PROTOCOL_VERSION = 1
PROTOCOL_MIN_VERSION = 1
