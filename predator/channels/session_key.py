"""Session key management — mirrors OpenClaw's session routing."""
from __future__ import annotations
from typing import Literal
import uuid

DmScope = Literal["main", "per-peer", "per-channel-peer", "per-account-channel-peer"]

def build_main_session_key(agent_id: str, main_key: str = "main") -> str:
    return f"agent:{agent_id}:{main_key}"

def build_peer_session_key(
    agent_id: str,
    channel: str,
    peer_id: str = "",
    chat_type: str = "direct",
    account_id: str = "",
    dm_scope: DmScope = "main",
) -> str:
    if chat_type == "group":
        return f"agent:{agent_id}:channel:{channel}:{peer_id}"
    if dm_scope == "main":
        return build_main_session_key(agent_id)
    if dm_scope == "per-peer":
        return f"agent:{agent_id}:direct:user:{peer_id}"
    if dm_scope == "per-channel-peer":
        return f"agent:{agent_id}:per-channel-peer:{channel}:{peer_id}"
    if dm_scope == "per-account-channel-peer":
        return f"agent:{agent_id}:per-account-channel-peer:{account_id}:{channel}:{peer_id}"
    return build_main_session_key(agent_id)

def build_subagent_session_key(agent_id: str) -> str:
    return f"agent:{agent_id}:subagent:{uuid.uuid4().hex[:12]}"

def parse_session_key(key: str) -> dict:
    parts = key.split(":")
    if len(parts) < 3 or parts[0] != "agent":
        return {"shape": "malformed", "raw": key}
    return {
        "shape": "agent",
        "agent_id": parts[1],
        "rest": ":".join(parts[2:]),
        "raw": key,
    }
