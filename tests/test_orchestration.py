"""End-to-end tests for the PREDATOR multi-agent orchestration system.

Tests:
1. SubagentRegistry — register, lookup, state transitions, lifecycle
2. SubagentDepthTracker — depth limits, parent-child tracking
3. SubagentSpawner — spawn, kill, wait, can_spawn limits
4. SubagentAnnouncer — auto-announce on completion
5. Lanes — command lane routing
6. Tools — spawn_subagent, list_subagents, wait_subagent, kill_subagent, steer_subagent
7. Gateway integration — RPC methods
8. System prompt — orchestration instructions present
"""

import asyncio
import sys
import time
import io

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def test_lanes():
    """Test command lane definitions."""
    from predator.agents.lanes import CommandLane, get_lane_label

    assert CommandLane.MAIN.value == "main"
    assert CommandLane.SUBAGENT.value == "subagent"
    assert CommandLane.NESTED.value == "nested"
    assert CommandLane.CRON.value == "cron"
    assert get_lane_label(CommandLane.SUBAGENT) == "Subagent"
    print("[+] Lanes: OK")


def test_registry_basics():
    """Test SubagentRegistry register/get/state transitions."""
    from predator.agents.subagent import (
        SubagentRegistry,
        SubagentRunRecord,
        SubagentState,
    )

    registry = SubagentRegistry()

    # Register
    record = SubagentRunRecord(
        run_id="test-001",
        session_key="agent:default:subagent:test-001",
        parent_session_key="agent:default:main",
        agent_id="default",
        label="test-recon",
        task="Scan target.com",
        state=SubagentState.PENDING,
        created_at=time.time(),
    )
    registry.register(record)

    # Get
    r = registry.get("test-001")
    assert r is not None
    assert r.label == "test-recon"
    assert r.state == SubagentState.PENDING

    # Children
    children = registry.get_children("agent:default:main")
    assert len(children) == 1

    # State transition
    registry.update_state("test-001", SubagentState.RUNNING, started_at=time.time())
    r = registry.get("test-001")
    assert r.state == SubagentState.RUNNING

    registry.update_state(
        "test-001", SubagentState.COMPLETED,
        result_text="Found 5 open ports",
        total_tokens=1500,
        turns=3,
        completed_at=time.time(),
    )
    r = registry.get("test-001")
    assert r.state == SubagentState.COMPLETED
    assert r.result_text == "Found 5 open ports"
    assert r.is_done is True
    assert r.total_tokens == 1500

    # Active children (should be 0 now)
    active = registry.get_active_children("agent:default:main")
    assert len(active) == 0

    # to_dict
    d = r.to_dict()
    assert d["run_id"] == "test-001"
    assert d["state"] == "completed"
    assert d["turns"] == 3

    print("[+] Registry basics: OK")


def test_depth_tracker():
    """Test SubagentDepthTracker depth enforcement."""
    from predator.agents.subagent import SubagentDepthTracker

    tracker = SubagentDepthTracker(max_depth=2)

    # Parent at depth 0
    assert tracker.get_depth("parent-session") == 0
    ok, reason = tracker.can_spawn("parent-session")
    assert ok is True

    # Register child at depth 1
    child_depth = tracker.register_child("parent-session", "child-session")
    assert child_depth == 1
    ok, reason = tracker.can_spawn("child-session")
    assert ok is True  # depth 1 < max 2

    # Register grandchild at depth 2
    grandchild_depth = tracker.register_child("child-session", "grandchild-session")
    assert grandchild_depth == 2
    ok, reason = tracker.can_spawn("grandchild-session")
    assert ok is False  # depth 2 >= max 2
    assert "Max spawn depth" in reason

    # Cleanup
    tracker.remove("grandchild-session")
    assert tracker.get_depth("grandchild-session") == 0

    print("[+] Depth tracker: OK")


def test_spawner_limits():
    """Test SubagentSpawner max_children and depth limits."""
    from predator.agents.subagent import SubagentSpawner

    spawner = SubagentSpawner(max_children=2, max_depth=1)

    # Can spawn initially
    ok, reason = spawner.can_spawn("parent")
    assert ok is True

    # Spawn 2 agents (simulate by registering records directly)
    from predator.agents.subagent import SubagentRunRecord, SubagentState

    for i in range(2):
        record = SubagentRunRecord(
            run_id=f"sim-{i}",
            session_key=f"agent:default:subagent:sim-{i}",
            parent_session_key="parent",
            state=SubagentState.RUNNING,
            created_at=time.time(),
        )
        spawner.registry.register(record)

    # Now at max children
    ok, reason = spawner.can_spawn("parent")
    assert ok is False
    assert "Max concurrent children" in reason

    # Complete one
    spawner.registry.update_state("sim-0", SubagentState.COMPLETED, completed_at=time.time())
    ok, reason = spawner.can_spawn("parent")
    assert ok is True  # One slot freed

    print("[+] Spawner limits: OK")


def test_spawner_spawn_and_lifecycle():
    """Test actual subagent spawning (with mock runtime)."""
    from predator.agents.subagent import (
        SubagentSpawner, SpawnParams, SubagentState,
    )

    results = {"called": False, "task": ""}

    class MockRuntime:
        async def run(self, message, session_id=None):
            results["called"] = True
            results["task"] = message

            class MockResult:
                final_text = "Scan complete: 3 ports open"
                turns = [1, 2]
                total_tokens = 500
                total_elapsed = 2.5
                stopped_reason = "completed"
            return MockResult()

    def mock_factory(record):
        return MockRuntime()

    async def _test():
        spawner = SubagentSpawner(max_children=5, max_depth=2)

        params = SpawnParams(
            task="Scan target.com ports 1-1000",
            label="port-scan",
            timeout_seconds=30,
        )

        record = await spawner.spawn(
            params, "agent:default:main",
            runtime_factory=mock_factory,
        )

        assert record.state in (SubagentState.PENDING, SubagentState.RUNNING)
        assert record.label == "port-scan"
        assert record.run_id != ""

        # Wait for completion
        completed = await spawner.wait(record.run_id, timeout=10)
        assert completed is not None
        assert completed.state == SubagentState.COMPLETED
        assert "3 ports open" in completed.result_text
        assert completed.turns == 2
        assert completed.total_tokens == 500
        assert results["called"] is True

        print("[+] Spawner spawn + lifecycle: OK")

    asyncio.run(_test())


def test_spawner_kill():
    """Test killing a running subagent."""
    from predator.agents.subagent import SubagentSpawner, SpawnParams

    async def _test():
        spawner = SubagentSpawner(max_children=5, max_depth=2)

        # Spawn a slow agent
        class SlowRuntime:
            async def run(self, message, session_id=None):
                await asyncio.sleep(999)  # Will be killed

        def slow_factory(record):
            return SlowRuntime()

        params = SpawnParams(task="Slow task", label="slow", timeout_seconds=999)
        record = await spawner.spawn(
            params, "parent", runtime_factory=slow_factory,
        )

        await asyncio.sleep(0.2)  # Let it start

        # Kill
        killed = await spawner.kill(record.run_id)
        assert killed is True

        await asyncio.sleep(0.3)  # Let cancel propagate

        r = spawner.registry.get(record.run_id)
        assert r.state.value == "cancelled"
        print("[+] Spawner kill: OK")

    asyncio.run(_test())


def test_spawner_steering():
    """Test steering messages."""
    from predator.agents.subagent import SubagentSpawner

    async def _test():
        spawner = SubagentSpawner()

        # Simulate a running subagent
        from predator.agents.subagent import SubagentRunRecord, SubagentState
        record = SubagentRunRecord(
            run_id="steer-test",
            session_key="agent:default:subagent:steer-test",
            parent_session_key="parent",
            state=SubagentState.RUNNING,
            created_at=time.time(),
        )
        spawner.registry.register(record)

        # Send steering message
        ok = await spawner.steer("steer-test", "Focus on port 443 specifically")
        assert ok is True

        msgs = spawner.get_steering_messages("steer-test")
        assert len(msgs) == 1
        assert "port 443" in msgs[0]

        # Second call should return empty (messages consumed)
        msgs2 = spawner.get_steering_messages("steer-test")
        assert len(msgs2) == 0

        print("[+] Steering: OK")

    asyncio.run(_test())


def test_announcer():
    """Test SubagentAnnouncer auto-announce."""
    from predator.agents.subagent import (
        SubagentRegistry, SubagentRunRecord, SubagentState, SubagentAnnouncer,
    )

    announced = {"called": False, "message": ""}

    async def mock_announce(parent_session_key, message, run_id):
        announced["called"] = True
        announced["message"] = message

    async def _test():
        registry = SubagentRegistry()
        announcer = SubagentAnnouncer(
            registry=registry, announce_callback=mock_announce,
        )

        record = SubagentRunRecord(
            run_id="ann-001",
            session_key="agent:default:subagent:ann-001",
            parent_session_key="parent",
            label="test-announce",
            task="Test task",
            state=SubagentState.RUNNING,
            created_at=time.time(),
            started_at=time.time(),
        )
        registry.register(record)

        # Complete the subagent (triggers lifecycle event -> announce)
        registry.update_state(
            "ann-001", SubagentState.COMPLETED,
            result_text="Found: admin panel at /admin",
            total_tokens=200,
            turns=2,
            completed_at=time.time(),
        )

        # Give the async announce task time to run
        await asyncio.sleep(0.5)

        assert announced["called"] is True
        assert "COMPLETED" in announced["message"]
        assert "admin panel" in announced["message"]
        assert record.announced is True

        print("[+] Announcer: OK")

    asyncio.run(_test())


def test_tools_spawn():
    """Test SubagentSpawnTool execute."""
    from predator.agents.tools.subagent_tool import SubagentSpawnTool
    from predator.agents.subagent import set_spawner, SubagentSpawner

    async def _test():
        spawner = SubagentSpawner(max_children=5, max_depth=2)
        set_spawner(spawner)

        tool = SubagentSpawnTool()
        assert tool.name == "spawn_subagent"

        result = await tool.execute(
            tool_call_id="tc-001",
            arguments={
                "task": "Scan example.com for open ports",
                "label": "port-scan",
                "_parent_session_key": "agent:default:main",
            },
        )

        assert not result.is_error
        assert "spawned successfully" in result.output
        assert "port-scan" in result.output

        print("[+] SpawnTool: OK")

    asyncio.run(_test())


def test_tools_list():
    """Test SubagentListTool execute."""
    from predator.agents.tools.subagent_tool import SubagentListTool
    from predator.agents.subagent import (
        set_spawner, SubagentSpawner, SubagentRunRecord, SubagentState,
    )

    async def _test():
        spawner = SubagentSpawner()
        set_spawner(spawner)

        # Register some test records
        for i, state in enumerate([SubagentState.RUNNING, SubagentState.COMPLETED]):
            record = SubagentRunRecord(
                run_id=f"list-{i}",
                session_key=f"agent:default:subagent:list-{i}",
                parent_session_key="agent:default:main",
                label=f"task-{i}",
                task=f"Task number {i}",
                state=state,
                created_at=time.time(),
                total_tokens=100 * (i + 1),
                turns=i + 1,
            )
            spawner.registry.register(record)

        tool = SubagentListTool()
        result = await tool.execute(
            tool_call_id="tc-002",
            arguments={"_parent_session_key": "agent:default:main"},
        )

        assert not result.is_error
        assert "task-0" in result.output
        assert "task-1" in result.output
        assert "RUNNING" in result.output
        assert "COMPLETED" in result.output

        print("[+] ListTool: OK")

    asyncio.run(_test())


def test_tools_kill():
    """Test SubagentKillTool."""
    from predator.agents.tools.subagent_tool import SubagentKillTool
    from predator.agents.subagent import (
        set_spawner, SubagentSpawner, SubagentRunRecord, SubagentState,
    )

    async def _test():
        spawner = SubagentSpawner()
        set_spawner(spawner)

        # Can't kill a non-existent agent
        tool = SubagentKillTool()
        result = await tool.execute(
            tool_call_id="tc-kill",
            arguments={"run_id": "nonexistent"},
        )
        assert result.is_error
        assert "not found" in result.output

        print("[+] KillTool: OK")

    asyncio.run(_test())


def test_tools_steer():
    """Test SubagentSteerTool."""
    from predator.agents.tools.subagent_tool import SubagentSteerTool
    from predator.agents.subagent import (
        set_spawner, SubagentSpawner, SubagentRunRecord, SubagentState,
    )

    async def _test():
        spawner = SubagentSpawner()
        set_spawner(spawner)

        record = SubagentRunRecord(
            run_id="steer-tool-test",
            session_key="agent:default:subagent:steer-tool-test",
            parent_session_key="agent:default:main",
            label="steer-me",
            task="Scan stuff",
            state=SubagentState.RUNNING,
            created_at=time.time(),
        )
        spawner.registry.register(record)

        tool = SubagentSteerTool()
        result = await tool.execute(
            tool_call_id="tc-steer",
            arguments={
                "run_id": "steer-tool-test",
                "message": "Focus only on HTTPS services",
            },
        )

        assert not result.is_error
        assert "Steering message sent" in result.output

        print("[+] SteerTool: OK")

    asyncio.run(_test())


def test_system_prompt_includes_orchestration():
    """Verify the system prompt includes subagent orchestration instructions."""
    from predator.agents.prompts.system import build_system_prompt

    prompt = build_system_prompt()

    assert "spawn_subagent" in prompt
    assert "Multi-Agent Orchestration" in prompt
    assert "list_subagents" in prompt
    assert "wait_subagent" in prompt
    assert "kill_subagent" in prompt
    assert "steer_subagent" in prompt
    assert "Max 5 concurrent subagents" in prompt
    assert "EXAMPLE ORCHESTRATION FLOW" in prompt
    assert "Parallel scanning" in prompt

    print("[+] System prompt orchestration: OK")


def test_registry_tool_count():
    """Verify orchestration tools are registered."""
    from predator.tools.registry import create_default_registry

    registry = create_default_registry()

    assert registry.get("spawn_subagent") is not None
    assert registry.get("list_subagents") is not None
    assert registry.get("wait_subagent") is not None
    assert registry.get("kill_subagent") is not None
    assert registry.get("steer_subagent") is not None

    print(f"[+] Registry: {registry.count} tools, all 5 orchestration tools present")


def test_concurrent_spawn():
    """Test spawning multiple subagents concurrently."""
    from predator.agents.subagent import SubagentSpawner, SpawnParams, SubagentState

    class FastRuntime:
        def __init__(self, delay=0.1):
            self._delay = delay

        async def run(self, message, session_id=None):
            await asyncio.sleep(self._delay)
            class R:
                final_text = f"Done: {message[:50]}"
                turns = [1]
                total_tokens = 100
            return R()

    def factory(record):
        return FastRuntime(delay=0.2)

    async def _test():
        spawner = SubagentSpawner(max_children=5, max_depth=2)

        # Spawn 3 in parallel
        records = []
        for i in range(3):
            params = SpawnParams(
                task=f"Task {i}: scan port {i * 100}",
                label=f"parallel-{i}",
                timeout_seconds=30,
            )
            r = await spawner.spawn(params, "parent", runtime_factory=factory)
            records.append(r)

        assert len(records) == 3
        for r in records:
            assert r.state in (SubagentState.PENDING, SubagentState.RUNNING)

        # Wait for all
        for r in records:
            completed = await spawner.wait(r.run_id, timeout=10)
            assert completed.state == SubagentState.COMPLETED

        children = spawner.get_children("parent")
        completed_count = sum(1 for c in children if c.state == SubagentState.COMPLETED)
        assert completed_count == 3

        print("[+] Concurrent spawn (3 parallel): OK")

    asyncio.run(_test())


def test_full_orchestration_flow():
    """Simulate a full orchestration flow like a real pentest."""
    from predator.agents.subagent import SubagentSpawner, SpawnParams, SubagentState

    class ReconRuntime:
        def __init__(self, task_text):
            self._task = task_text

        async def run(self, message, session_id=None):
            await asyncio.sleep(0.1)
            msg = message.lower()
            if msg.startswith("port"):
                text = "Port scan results:\n22/tcp open ssh\n80/tcp open http\n443/tcp open https"
            elif "osint" in msg:
                text = "OSINT results:\nDomain: target.com\nIP: 1.2.3.4\nEmails: admin@target.com"
            elif "vuln" in msg:
                text = "Vulnerability scan:\nCVE-2024-1234 (CRITICAL) - Apache RCE\nCVE-2023-5678 (HIGH)"
            else:
                text = f"Completed: {message[:50]}"

            class R:
                final_text = text
                turns = [1, 2]
                total_tokens = 300
            return R()

    def factory(record):
        return ReconRuntime(record.task)

    async def _test():
        # Use a fresh spawner for this test
        spawner = SubagentSpawner(max_children=5, max_depth=2)

        # Phase 1: Spawn recon subagents
        port_scan = await spawner.spawn(
            SpawnParams(task="Port scan target.com", label="port-scan"),
            "orchestrator", runtime_factory=factory,
        )
        osint = await spawner.spawn(
            SpawnParams(task="OSINT recon on target.com", label="osint-recon"),
            "orchestrator", runtime_factory=factory,
        )

        # Wait for phase 1
        r1 = await spawner.wait(port_scan.run_id, timeout=10)
        r2 = await spawner.wait(osint.run_id, timeout=10)
        assert r1.state == SubagentState.COMPLETED, f"Expected COMPLETED, got {r1.state}"
        assert r2.state == SubagentState.COMPLETED, f"Expected COMPLETED, got {r2.state}"
        assert "22/tcp" in r1.result_text, f"Missing port data: {r1.result_text[:100]}"
        assert "admin@target.com" in r2.result_text, f"Missing OSINT data: {r2.result_text[:100]}"

        # Phase 2: Spawn vuln scan based on phase 1 results
        vuln_scan = await spawner.spawn(
            SpawnParams(task="Vulnerability scan on ports 22,80,443", label="vuln-scan"),
            "orchestrator", runtime_factory=factory,
        )
        r3 = await spawner.wait(vuln_scan.run_id, timeout=10)
        assert r3.state == SubagentState.COMPLETED, f"Expected COMPLETED, got {r3.state}"
        assert "CVE-2024-1234" in r3.result_text, f"Missing CVE data: {r3.result_text[:100]}"

        # Check all children
        all_children = spawner.get_children("orchestrator")
        assert len(all_children) == 3
        assert all(c.state == SubagentState.COMPLETED for c in all_children)

        total_tokens = sum(c.total_tokens for c in all_children)
        assert total_tokens == 900  # 300 * 3

        print("[+] Full orchestration flow (3-phase pentest): OK")

    asyncio.run(_test())


if __name__ == "__main__":
    print("=" * 60)
    print("PREDATOR Orchestration System — End-to-End Tests")
    print("=" * 60)
    print()

    test_lanes()
    test_registry_basics()
    test_depth_tracker()
    test_spawner_limits()
    test_spawner_spawn_and_lifecycle()
    test_spawner_kill()
    test_spawner_steering()
    test_announcer()
    test_tools_spawn()
    test_tools_list()
    test_tools_kill()
    test_tools_steer()
    test_system_prompt_includes_orchestration()
    test_registry_tool_count()
    test_concurrent_spawn()
    test_full_orchestration_flow()

    print()
    print("=" * 60)
    print("ALL 16 TESTS PASSED!")
    print("=" * 60)
