"""Agent runtime — mirrors OpenClaw's pi-embedded-runner/run/attempt.ts.

The core agent loop:
1. Send message + context to LLM
2. STREAM response (text deltas + tool calls)
3. Execute tool calls
4. Feed results back to LLM
5. Check for compaction needs
6. Repeat until agent finishes or limit reached

This is the brain of PREDATOR — the autonomous execution engine.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from predator.agents.lanes import CommandLane
from predator.agents.loop_detection import LoopDetector
from predator.agents.prompts.system import build_system_prompt
from predator.agents.tool_executor import ToolExecutor
from predator.config.schema import PredatorConfig
from predator.hooks.runner import HookRunner
from predator.providers.base import (
    BaseProvider,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    StreamEvent,
    ToolCall,
)
from predator.providers.router import ProviderRouter
from predator.sessions.compaction import (
    CompactionResult,
    compact_conversation,
    estimate_tokens,
    get_compaction_warning,
    get_context_limit,
    needs_compaction,
)
from predator.sessions.transcript import SessionTranscript
from predator.tools.registry import ToolRegistry
from predator.utils.logger import get_logger
from predator.utils.platform import detect_platform

log = get_logger("agents.runtime")


@dataclass
class AgentTurn:
    """A single turn in the agent loop."""

    turn_number: int
    user_message: str = ""
    assistant_text: str = ""
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    elapsed: float = 0.0


@dataclass
class AgentResult:
    """Result of a full agent run."""

    final_text: str
    turns: list[AgentTurn] = field(default_factory=list)
    total_tokens: int = 0
    total_elapsed: float = 0.0
    stopped_reason: str = ""  # completed, max_turns, error, aborted, compacted
    compaction: Optional[CompactionResult] = None


class AgentRuntime:
    """The PREDATOR agent runtime — autonomous execution engine.

    Mirrors OpenClaw's agent loop architecture:
    - Message construction with system prompt + history
    - STREAMING LLM interaction (real-time text deltas)
    - Multi-turn tool execution
    - Automatic session compaction when approaching context limits
    - Loop detection and recovery
    - Session transcript persistence
    """

    def __init__(
        self,
        provider: BaseProvider,
        registry: ToolRegistry,
        config: PredatorConfig,
        hook_runner: Optional[HookRunner] = None,
        transcript: Optional[SessionTranscript] = None,
        router: Optional[ProviderRouter] = None,
        on_text: Optional[Callable[[str], None]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_tool_start: Optional[Callable[[str, str, dict], None]] = None,
        on_tool_end: Optional[Callable[[str, str, bool], None]] = None,
        on_compaction: Optional[Callable[[str], None]] = None,
        lane: CommandLane = CommandLane.MAIN,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._config = config
        self._hook_runner = hook_runner or HookRunner()
        self._transcript = transcript
        self._router: Optional[ProviderRouter] = router
        self._on_text = on_text
        self._on_thinking = on_thinking
        self._on_tool_start = on_tool_start
        self._on_tool_end = on_tool_end
        self._on_compaction = on_compaction
        self._lane = lane

        self._tool_executor = ToolExecutor(
            registry=registry,
            hook_runner=self._hook_runner,
            on_tool_update=self._handle_tool_update,
        )

        self._max_turns = 50  # Max tool-use turns per run
        self._aborted = False
        self._use_streaming = True  # Enable streaming by default
        self._session_key: str = ""  # Set during run()

        # Orchestration improvements (from agent-orchestra patterns)
        self._loop_detector = LoopDetector()
        self._max_stuck_retries = 3  # Kill after N stuck iterations
        self._stuck_count = 0
        self._token_budget = config.agent.max_tokens * 20 if config else 160_000  # Per-run budget
        self._last_error: str = ""

    def _build_system_prompt(self, session_type: str = "main") -> str:
        """Build the system prompt with platform context, tool info, and workspace files."""
        platform_info = None
        try:
            platform_info = detect_platform()
        except Exception:
            pass

        tool_names = self._registry.tool_names
        tools_summary = f"You have {len(tool_names)} tools available: {', '.join(tool_names)}"

        # Load memory context if available
        memory_context = ""
        try:
            from predator.memory.manager import MemoryManager
            mm = MemoryManager()
            memory_context = mm.get_context_for_agent()
        except Exception:
            pass

        return build_system_prompt(
            platform_info=platform_info,
            identity_name=self._config.identity.name,
            identity_description=self._config.identity.description,
            extra_prompt=self._config.identity.system_prompt_extra or "",
            available_tools_summary=tools_summary,
            session_type=session_type,
            memory_context=memory_context,
        )

    def _build_messages(
        self,
        user_message: str,
        history: list[ModelMessage],
    ) -> list[ModelMessage]:
        """Build the message array for the LLM request."""
        messages: list[ModelMessage] = []
        messages.extend(history)
        messages.append(ModelMessage(role="user", content=user_message))
        return messages

    def _handle_tool_update(self, tool_call_id: str, text: str) -> None:
        """Handle streaming tool output updates."""
        if self._on_text:
            self._on_text(f"[tool output] {text}")

    def abort(self) -> None:
        """Abort the current agent run."""
        self._aborted = True

    def switch_provider(self, provider: BaseProvider) -> None:
        """Switch the active LLM provider at runtime."""
        old_type = getattr(self._provider, "provider_type", "unknown")
        new_type = getattr(provider, "provider_type", "unknown")
        log.info(f"Runtime provider switched: {old_type} -> {new_type}")

        self._provider = provider

        if self._transcript:
            self._transcript.add_event("provider_switched", {
                "from": str(old_type),
                "to": str(new_type),
                "model": getattr(provider, "default_model", None),
            })

    async def _stream_response(self, request: ModelRequest) -> ModelResponse:
        """Stream a response from the LLM, emitting text deltas in real-time.

        Falls back to non-streaming complete() if streaming fails.
        """
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        usage: dict[str, int] = {}
        model = ""

        try:
            async for event in self._provider.stream(request):
                if event.type == "text_delta":
                    content_parts.append(event.text)
                    if self._on_text:
                        self._on_text(event.text)

                elif event.type == "thinking":
                    thinking_parts.append(event.thinking)
                    if self._on_thinking:
                        self._on_thinking(event.thinking)

                elif event.type == "tool_call_start" and event.tool_call:
                    tool_calls.append(event.tool_call)

                elif event.type == "done":
                    if event.usage:
                        usage = event.usage

                elif event.type == "error":
                    log.error(f"Stream error: {event.text}")
                    break

            return ModelResponse(
                content="".join(content_parts),
                thinking="".join(thinking_parts),
                tool_calls=tool_calls,
                usage=usage,
                model=model or request.model,
            )

        except (NotImplementedError, AttributeError):
            # Provider doesn't support streaming — fall back
            log.debug("Streaming not supported, falling back to complete()")
            self._use_streaming = False
            response = await self._provider.complete(request)
            if response.content and self._on_text:
                self._on_text(response.content)
            if response.thinking and self._on_thinking:
                self._on_thinking(response.thinking)
            return response

        except Exception as e:
            # Streaming failed — fall back to non-streaming
            log.warning(f"Streaming failed ({e}), falling back to complete()")
            response = await self._provider.complete(request)
            if response.content and self._on_text:
                self._on_text(response.content)
            return response

    async def run(
        self,
        message: str,
        history: Optional[list[ModelMessage]] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Run the agent loop for a single user message.

        This is the main execution loop — mirrors OpenClaw's attempt.ts:
        1. Build system prompt + message history
        2. Stream response from LLM (real-time text deltas)
        3. If LLM returns tool calls -> execute them -> feed results -> loop
        4. If LLM returns text only -> done
        5. Check for compaction needs between turns
        6. Repeat up to max_turns
        """
        self._aborted = False
        self._session_key = session_id or "agent:default:main"
        start_time = time.time()
        turns: list[AgentTurn] = []
        conversation: list[ModelMessage] = list(history or [])
        total_tokens = 0
        compaction_result: Optional[CompactionResult] = None

        agent_config = self._config.agent
        session_type = "subagent" if self._lane == CommandLane.SUBAGENT else "main"
        system_prompt = self._build_system_prompt(session_type=session_type)
        tool_schemas = self._registry.get_llm_schemas()

        # Run agent start hook
        await self._hook_runner.run("agent_start", {"message": message, "session_id": session_id})

        # Record user message
        if self._transcript:
            self._transcript.add_event("user_message", {"content": message})

        # Add user message to conversation
        conversation.append(ModelMessage(role="user", content=message))

        turn_number = 0
        final_text = ""

        while turn_number < self._max_turns and not self._aborted:
            turn_number += 1
            turn = AgentTurn(turn_number=turn_number)
            turn_start = time.time()

            # --- Compaction check ---
            warning = get_compaction_warning(conversation, agent_config.model)
            if warning and self._on_compaction:
                self._on_compaction(warning)

            if needs_compaction(conversation, agent_config.model):
                log.info("Compacting conversation...")
                if self._on_compaction:
                    self._on_compaction("[Compacting session to preserve context...]")

                try:
                    memory_manager = None
                    try:
                        from predator.memory.manager import MemoryManager
                        memory_manager = MemoryManager()
                    except Exception:
                        pass

                    cr = await compact_conversation(
                        messages=conversation,
                        provider=self._provider,
                        model=agent_config.model,
                        memory_manager=memory_manager,
                    )
                    compaction_result = cr
                    # Replace conversation with compacted version
                    conversation = [
                        ModelMessage(
                            role="user",
                            content=(
                                "[Session compacted — previous conversation summarized below]\n\n"
                                f"{cr.summary}\n\n"
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
                    # Re-add the last user message
                    conversation.append(ModelMessage(role="user", content=message))

                    if self._on_compaction:
                        self._on_compaction(
                            f"[Compacted: {cr.original_messages} -> {cr.compacted_messages} messages, "
                            f"~{cr.tokens_before} -> ~{cr.tokens_after_estimate} tokens]"
                        )
                    if self._transcript:
                        self._transcript.add_event("compaction", {
                            "original_messages": cr.original_messages,
                            "compacted_messages": cr.compacted_messages,
                            "tokens_before": cr.tokens_before,
                            "tokens_after": cr.tokens_after_estimate,
                        })
                except Exception as e:
                    log.error(f"Compaction failed: {e}")

            # Build LLM request
            request = ModelRequest(
                messages=conversation,
                model=agent_config.model,
                tools=tool_schemas,
                temperature=agent_config.temperature,
                max_tokens=agent_config.max_tokens,
                thinking_budget=agent_config.thinking_budget,
                system_prompt=system_prompt,
            )

            # Call LLM — streaming or non-streaming
            try:
                if self._use_streaming:
                    response = await self._stream_response(request)
                else:
                    response = await self._provider.complete(request)
                    if response.content and self._on_text:
                        self._on_text(response.content)
                    if response.thinking and self._on_thinking:
                        self._on_thinking(response.thinking)
            except Exception as e:
                log.error(f"LLM error: {e}")
                final_text = f"Error communicating with LLM: {e}"
                turns.append(turn)
                break

            # Track usage
            total_tokens += response.usage.get("input_tokens", 0)
            total_tokens += response.usage.get("output_tokens", 0)
            turn.usage = response.usage

            # Process response text
            if response.content:
                turn.assistant_text = response.content
                final_text = response.content

            if response.thinking:
                turn.thinking = response.thinking

            # Record assistant message in conversation
            assistant_msg = ModelMessage(
                role="assistant",
                content=response.content,
            )
            if response.tool_calls:
                assistant_msg.tool_calls = [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ]
            conversation.append(assistant_msg)

            # If no tool calls, we're done
            if not response.tool_calls:
                turn.elapsed = time.time() - turn_start
                turns.append(turn)

                if self._transcript:
                    self._transcript.add_event("assistant_message", {
                        "content": response.content,
                        "thinking": response.thinking,
                    })
                break

            # Execute tool calls
            for tc in response.tool_calls:
                if self._aborted:
                    break

                turn.tool_calls.append({
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                })

                if self._on_tool_start:
                    self._on_tool_start(tc.id, tc.name, tc.arguments)

                if self._transcript:
                    self._transcript.add_event("tool_call", {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    })

                # Inject parent session key for subagent tools
                exec_args = dict(tc.arguments)
                if tc.name in (
                    "spawn_subagent", "list_subagents", "wait_subagent",
                    "kill_subagent", "steer_subagent",
                ):
                    exec_args["_parent_session_key"] = self._session_key

                # Execute
                result = await self._tool_executor.execute(tc.id, tc.name, exec_args)

                turn.tool_results.append({
                    "id": tc.id,
                    "name": tc.name,
                    "output": result.output[:5000],  # Truncate for history
                    "is_error": result.is_error,
                })

                if self._on_tool_end:
                    self._on_tool_end(tc.id, tc.name, result.is_error)

                if self._transcript:
                    self._transcript.add_event("tool_result", {
                        "id": tc.id,
                        "name": tc.name,
                        "output": result.output[:2000],
                        "is_error": result.is_error,
                    })

                # Add tool result to conversation
                conversation.append(ModelMessage(
                    role="tool",
                    content=result.output,
                    tool_call_id=tc.id,
                ))

                # Record call for loop detection
                self._loop_detector.record_call(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=result.output[:500] if result.output else "",
                )

            # --- Loop detection check ---
            loop_msg = self._loop_detector.check_loop()
            if loop_msg:
                self._stuck_count += 1
                log.warning(f"Loop detected (stuck count: {self._stuck_count}): {loop_msg}")

                if self._stuck_count >= self._max_stuck_retries:
                    # Kill — too many stuck iterations
                    log.error(f"Agent stuck after {self._stuck_count} retries, terminating")
                    final_text = (
                        f"[Agent terminated: stuck in a loop after {self._stuck_count} retries]\n"
                        f"Loop: {loop_msg}\n"
                        f"Last output: {final_text[:500] if final_text else '(none)'}"
                    )
                    turn.elapsed = time.time() - turn_start
                    turns.append(turn)
                    break

                # Forced reflection — inject a reflection prompt to break the loop
                reflection_prompt = (
                    f"[SYSTEM] Loop detected: {loop_msg}\n"
                    f"You have been repeating the same action. Stop and reflect:\n"
                    f"1. What failed?\n"
                    f"2. What specific change would fix it?\n"
                    f"3. Are you repeating the same approach?\n"
                    f"Try a DIFFERENT approach or report that you cannot complete the task."
                )
                conversation.append(ModelMessage(role="user", content=reflection_prompt))
                self._loop_detector.reset()

            # --- Token budget check ---
            if total_tokens >= self._token_budget:
                log.warning(f"Token budget exhausted: {total_tokens}/{self._token_budget}")
                final_text += "\n\n[Token budget exhausted — stopping to prevent runaway costs]"
                turn.elapsed = time.time() - turn_start
                turns.append(turn)
                break

            turn.elapsed = time.time() - turn_start
            turns.append(turn)

        # Determine stop reason
        if self._aborted:
            stopped_reason = "aborted"
        elif self._stuck_count >= self._max_stuck_retries:
            stopped_reason = "stuck_loop"
        elif total_tokens >= self._token_budget:
            stopped_reason = "token_budget"
        elif turn_number >= self._max_turns:
            stopped_reason = "max_turns"
            final_text += "\n\n[Reached maximum number of tool-use turns]"
        else:
            stopped_reason = "completed"

        total_elapsed = time.time() - start_time

        # ── Append auto-install report if any tools were installed ──
        install_report = self._tool_executor.get_auto_install_report()
        if install_report:
            final_text += f"\n\n{install_report}"

        # Run agent end hook
        await self._hook_runner.run("agent_end", {
            "turns": turn_number,
            "total_tokens": total_tokens,
            "elapsed": total_elapsed,
            "stopped_reason": stopped_reason,
        })

        # Save transcript
        if self._transcript:
            self._transcript.add_event("agent_end", {
                "stopped_reason": stopped_reason,
                "turns": turn_number,
                "total_tokens": total_tokens,
            })
            self._transcript.save()

        return AgentResult(
            final_text=final_text,
            turns=turns,
            total_tokens=total_tokens,
            total_elapsed=total_elapsed,
            stopped_reason=stopped_reason,
            compaction=compaction_result,
        )
