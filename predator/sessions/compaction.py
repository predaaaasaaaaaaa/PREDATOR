"""Session compaction — mirrors OpenClaw's compaction system.

When a session approaches the context limit, compaction:
1. Summarizes the conversation history
2. Writes key findings to MEMORY.md
3. Replaces the full history with the summary
4. Warns the user before it happens

The .md files (SOUL.md, IDENTITY.md, USER.md, MEMORY.md) persist across
sessions — they ARE the long-term brain. Sessions are short-term working memory.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from predator.providers.base import ModelMessage, ModelRequest, ModelResponse, BaseProvider

logger = logging.getLogger(__name__)

# Model context limits (tokens) — conservative estimates
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "llama3.1": 128_000,
    "llama3": 8_000,
    "mistral": 32_000,
}
DEFAULT_CONTEXT_LIMIT = 128_000

# Trigger compaction at this fraction of context limit
COMPACTION_THRESHOLD = 0.75

# Rough chars-to-tokens ratio (conservative)
CHARS_PER_TOKEN = 3.5

COMPACTION_PROMPT = """Summarize this conversation history into a concise but complete summary.
Preserve ALL of the following:
- Target information (IPs, domains, hostnames, credentials found)
- Tool results and findings (open ports, vulnerabilities, paths discovered)
- Decisions made and reasoning
- Current task/objective and progress
- Any errors encountered and workarounds

Format as a structured briefing the agent can use to continue seamlessly.
Do NOT include pleasantries or meta-commentary. Just the facts."""


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    summary: str
    original_messages: int
    compacted_messages: int
    tokens_before: int
    tokens_after_estimate: int
    memory_entries: list[str]  # Keys written to memory


def estimate_tokens(messages: list[ModelMessage]) -> int:
    """Rough token estimate from messages."""
    total_chars = 0
    for msg in messages:
        if isinstance(msg.content, str):
            total_chars += len(msg.content)
        elif isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, dict):
                    total_chars += len(str(block.get("text", "")))
        if msg.tool_calls:
            total_chars += len(str(msg.tool_calls))
    return int(total_chars / CHARS_PER_TOKEN)


def get_context_limit(model: str) -> int:
    """Get the context limit for a model."""
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if key in model:
            return limit
    return DEFAULT_CONTEXT_LIMIT


def needs_compaction(
    messages: list[ModelMessage],
    model: str,
    threshold: float = COMPACTION_THRESHOLD,
) -> bool:
    """Check if the conversation needs compaction."""
    current_tokens = estimate_tokens(messages)
    limit = get_context_limit(model)
    return current_tokens >= int(limit * threshold)


def get_compaction_warning(
    messages: list[ModelMessage],
    model: str,
) -> str | None:
    """Get a user-facing warning if approaching context limit.

    Returns warning text or None if not close.
    """
    current_tokens = estimate_tokens(messages)
    limit = get_context_limit(model)
    ratio = current_tokens / limit

    if ratio >= 0.9:
        return (
            f"[!] Session at {int(ratio*100)}% context capacity "
            f"({current_tokens:,}/{limit:,} tokens). "
            "Compacting now to preserve context. "
            "Use /new to start a fresh session — the agent will remember everything via MEMORY.md."
        )
    elif ratio >= COMPACTION_THRESHOLD:
        return (
            f"[*] Session at {int(ratio*100)}% context capacity. "
            "Automatic compaction will trigger soon. "
            "Consider /new for a clean session."
        )
    return None


async def compact_conversation(
    messages: list[ModelMessage],
    provider: BaseProvider,
    model: str,
    memory_manager: Any = None,
) -> CompactionResult:
    """Compact a conversation by summarizing it.

    Returns a CompactionResult with the summary and new message list.
    The caller should replace the conversation history with the compacted version.
    """
    original_count = len(messages)
    tokens_before = estimate_tokens(messages)

    # Build the conversation text for summarization
    conv_text_parts = []
    for msg in messages:
        role = msg.role.upper()
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if msg.tool_calls:
            tool_info = ", ".join(tc.get("name", "?") for tc in msg.tool_calls)
            conv_text_parts.append(f"[{role}] {content}\n  -> Tools: {tool_info}")
        elif msg.role == "tool":
            # Truncate tool output for summary
            truncated = content[:2000] + ("..." if len(content) > 2000 else "")
            conv_text_parts.append(f"[TOOL RESULT] {truncated}")
        else:
            conv_text_parts.append(f"[{role}] {content}")

    conversation_dump = "\n\n".join(conv_text_parts)

    # Ask the LLM to summarize
    summary_request = ModelRequest(
        messages=[
            ModelMessage(role="user", content=f"{COMPACTION_PROMPT}\n\n---\n{conversation_dump}\n---"),
        ],
        model=model,
        max_tokens=4096,
        temperature=0.3,
        system_prompt="You are a precise intelligence analyst creating operational briefings.",
    )

    try:
        response: ModelResponse = await provider.complete(summary_request)
        summary = response.content
    except Exception as e:
        logger.error(f"Compaction summarization failed: {e}")
        # Fallback: just keep the last N messages
        keep = messages[-10:]
        return CompactionResult(
            summary="[Compaction failed — keeping recent messages]",
            original_messages=original_count,
            compacted_messages=len(keep),
            tokens_before=tokens_before,
            tokens_after_estimate=estimate_tokens(keep),
            memory_entries=[],
        )

    # Write summary to memory if available
    memory_entries = []
    if memory_manager:
        try:
            key = f"session_summary_{int(time.time())}"
            memory_manager.store.store(key, summary, category="session_summary")
            memory_entries.append(key)
        except Exception:
            pass

    # Build compacted conversation: system context + summary + last 2 messages
    compacted: list[ModelMessage] = [
        ModelMessage(
            role="user",
            content=(
                "[Session compacted — previous conversation summarized below]\n\n"
                f"{summary}\n\n"
                "[End of summary — continue from here]"
            ),
        ),
        ModelMessage(
            role="assistant",
            content=(
                "Understood. I have the full context from our previous conversation. "
                "Ready to continue."
            ),
        ),
    ]

    # Append the last few actual messages for continuity
    recent = [m for m in messages[-4:] if m.role in ("user", "assistant")]
    compacted.extend(recent)

    tokens_after = estimate_tokens(compacted)

    logger.info(
        f"Compaction: {original_count} messages -> {len(compacted)} "
        f"({tokens_before} -> {tokens_after} est. tokens)"
    )

    return CompactionResult(
        summary=summary,
        original_messages=original_count,
        compacted_messages=len(compacted),
        tokens_before=tokens_before,
        tokens_after_estimate=tokens_after,
        memory_entries=memory_entries,
    )
