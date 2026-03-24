"""Cron service — mirrors OpenClaw's cron/service.ts.

Timer-based scheduler with exponential error backoff.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Callable, Awaitable, Optional

from predator.cron.types import (
    CronJob, CronJobState, CronSchedule, CronPayload, ScheduleKind,
)
from predator.cron.schedule import compute_next_run, is_due

logger = logging.getLogger(__name__)

MAX_TIMER_DELAY_MS = 60_000
DEFAULT_JOB_TIMEOUT_MS = 10 * 60_000
MIN_REFIRE_GAP_MS = 2_000
ERROR_BACKOFF_MS = [30_000, 60_000, 300_000, 900_000, 3_600_000]


class CronService:
    """Cron scheduler with persistent job storage."""

    def __init__(
        self,
        state_dir: str = "",
        job_handler: Optional[Callable[[CronJob], Awaitable[str]]] = None,
    ):
        self._state_dir = state_dir or os.path.expanduser("~/.predator")
        self._store_path = os.path.join(self._state_dir, "cron-jobs.json")
        self._jobs: dict[str, CronJob] = {}
        self._job_handler = job_handler
        self._timer_task: Optional[asyncio.Task] = None
        self._running = False

    def _load(self) -> None:
        if os.path.isfile(self._store_path):
            try:
                with open(self._store_path) as f:
                    data = json.load(f)
                for item in data.get("jobs", []):
                    job = CronJob(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        enabled=item.get("enabled", True),
                        delete_after_run=item.get("delete_after_run", False),
                        payload=CronPayload(
                            kind=item.get("payload", {}).get("kind", "agent_turn"),
                            message=item.get("payload", {}).get("message", ""),
                            model=item.get("payload", {}).get("model", ""),
                            timeout_seconds=item.get("payload", {}).get("timeout_seconds", 600),
                        ),
                        state=CronJobState(
                            next_run_at_ms=item.get("state", {}).get("next_run_at_ms", 0),
                            last_run_at_ms=item.get("state", {}).get("last_run_at_ms", 0),
                            last_status=item.get("state", {}).get("last_status", ""),
                            consecutive_errors=item.get("state", {}).get("consecutive_errors", 0),
                        ),
                    )
                    sched = item.get("schedule", {})
                    job.schedule = CronSchedule(
                        kind=ScheduleKind(sched.get("kind", "every")),
                        at=sched.get("at", ""),
                        every_ms=sched.get("every_ms", 0),
                        expr=sched.get("expr", ""),
                        tz=sched.get("tz", ""),
                    )
                    self._jobs[job.id] = job
            except Exception as e:
                logger.error(f"Failed to load cron store: {e}")

    def _save(self) -> None:
        os.makedirs(self._state_dir, exist_ok=True)
        jobs_data = []
        for job in self._jobs.values():
            jobs_data.append({
                "id": job.id,
                "name": job.name,
                "enabled": job.enabled,
                "delete_after_run": job.delete_after_run,
                "schedule": {
                    "kind": job.schedule.kind.value,
                    "at": job.schedule.at,
                    "every_ms": job.schedule.every_ms,
                    "expr": job.schedule.expr,
                    "tz": job.schedule.tz,
                },
                "payload": {
                    "kind": job.payload.kind,
                    "message": job.payload.message,
                    "model": job.payload.model,
                    "timeout_seconds": job.payload.timeout_seconds,
                },
                "state": {
                    "next_run_at_ms": job.state.next_run_at_ms,
                    "last_run_at_ms": job.state.last_run_at_ms,
                    "last_status": job.state.last_status,
                    "consecutive_errors": job.state.consecutive_errors,
                },
            })
        with open(self._store_path, "w") as f:
            json.dump({"version": 1, "jobs": jobs_data}, f, indent=2)

    def add_job(self, job: CronJob) -> CronJob:
        if not job.id:
            job.id = uuid.uuid4().hex[:12]
        now_ms = time.time() * 1000
        job.state.next_run_at_ms = compute_next_run(job.schedule, now_ms)
        self._jobs[job.id] = job
        self._save()
        logger.info(f"Cron job added: {job.name} ({job.id})")
        return job

    def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            return True
        return False

    def enable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = True
            self._save()
            return True
        return False

    def disable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = False
            self._save()
            return True
        return False

    def list_jobs(self) -> list[CronJob]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    async def start(self) -> None:
        self._load()
        self._running = True
        self._run_missed_jobs()
        self._arm_timer()
        logger.info(f"Cron service started with {len(self._jobs)} jobs")

    async def stop(self) -> None:
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
        self._save()
        logger.info("Cron service stopped")

    def _run_missed_jobs(self) -> None:
        now_ms = time.time() * 1000
        for job in self._jobs.values():
            if not job.enabled:
                continue
            if job.schedule.kind == ScheduleKind.AT and job.state.last_run_at_ms > 0:
                continue  # Already ran
            if job.state.next_run_at_ms and job.state.next_run_at_ms < now_ms:
                job.state.next_run_at_ms = now_ms  # Will fire on next tick

    def _arm_timer(self) -> None:
        if not self._running:
            return
        now_ms = time.time() * 1000
        next_wake = now_ms + MAX_TIMER_DELAY_MS
        for job in self._jobs.values():
            if job.enabled and job.state.next_run_at_ms:
                next_wake = min(next_wake, job.state.next_run_at_ms)
        delay_ms = max(100, next_wake - now_ms)
        delay_s = min(delay_ms / 1000, MAX_TIMER_DELAY_MS / 1000)

        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._timer_tick(delay_s))

    async def _timer_tick(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if not self._running:
            return
        await self._on_timer()
        self._arm_timer()

    async def _on_timer(self) -> None:
        now_ms = time.time() * 1000
        due_jobs = [
            job for job in self._jobs.values()
            if job.enabled and is_due(job.state.next_run_at_ms, now_ms)
            and (now_ms - job.state.last_run_at_ms) > MIN_REFIRE_GAP_MS
        ]
        tasks = [self._run_job(job) for job in due_jobs]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_job(self, job: CronJob) -> None:
        now_ms = time.time() * 1000
        job.state.running_at_ms = now_ms
        logger.info(f"Cron executing: {job.name} ({job.id})")

        try:
            if self._job_handler:
                result = await asyncio.wait_for(
                    self._job_handler(job),
                    timeout=job.payload.timeout_seconds,
                )
            else:
                result = "no handler"

            job.state.last_status = "ok"
            job.state.last_error = ""
            job.state.consecutive_errors = 0
            job.state.last_duration_ms = time.time() * 1000 - now_ms
            logger.info(f"Cron completed: {job.name}")

        except Exception as e:
            job.state.last_status = "error"
            job.state.last_error = str(e)
            job.state.consecutive_errors += 1
            job.state.last_duration_ms = time.time() * 1000 - now_ms
            logger.error(f"Cron failed: {job.name}: {e}")

        job.state.last_run_at_ms = time.time() * 1000
        job.state.running_at_ms = 0

        if job.delete_after_run:
            self._jobs.pop(job.id, None)
        else:
            # Apply error backoff
            backoff = 0
            if job.state.consecutive_errors > 0:
                idx = min(job.state.consecutive_errors - 1, len(ERROR_BACKOFF_MS) - 1)
                backoff = ERROR_BACKOFF_MS[idx]

            next_ms = compute_next_run(job.schedule, time.time() * 1000)
            job.state.next_run_at_ms = max(next_ms, time.time() * 1000 + backoff)

        self._save()
