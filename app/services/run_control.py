from __future__ import annotations

import asyncio
import subprocess
import threading
from dataclasses import dataclass, field
from time import time


class WorkflowCancelled(Exception):
    pass


@dataclass(eq=False)
class RunState:
    task: asyncio.Task | None = None
    run_id: str = ""
    status: str = "running"
    stages: dict[str, dict] = field(default_factory=dict)
    result: dict | None = None
    error: str = ""
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    processes: set[subprocess.Popen] = field(default_factory=set)
    comfy_url: str = ""
    comfy_prompt_id: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise WorkflowCancelled("Workflow cancelled")

    def set_run_id(self, run_id: str) -> None:
        with self._lock:
            self.run_id = run_id
            self.updated_at = time()

    def set_comfy_prompt(self, comfy_url: str, prompt_id: str) -> None:
        with self._lock:
            self.comfy_url = comfy_url
            self.comfy_prompt_id = prompt_id
            self.updated_at = time()

    def record_stage(self, event: dict) -> None:
        stage = str(event.get("stage") or "")
        if not stage:
            return
        with self._lock:
            item = {
                "status": str(event.get("status") or "idle"),
                "duration": event.get("duration"),
            }
            self.stages[stage] = item
            if stage == "total" and item["status"] == "done":
                self.status = "done"
            self.updated_at = time()

    def record_result(self, data: dict) -> None:
        with self._lock:
            self.result = data
            self.status = "done"
            self.updated_at = time()

    def record_error(self, message: str) -> None:
        with self._lock:
            self.error = message
            self.status = "failed"
            self._mark_running_locked("failed")
            self.updated_at = time()

    def record_cancelled(self, message: str = "Workflow cancelled") -> None:
        with self._lock:
            self.error = message
            self.status = "cancelled"
            self._mark_running_locked("cancelled")
            self.updated_at = time()

    def snapshot(self, active: bool) -> dict:
        with self._lock:
            return {
                "exists": True,
                "active": active,
                "run_id": self.run_id,
                "status": self.status,
                "stages": {k: dict(v) for k, v in self.stages.items()},
                "result": dict(self.result) if self.result else None,
                "error": self.error,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }

    def add_process(self, process: subprocess.Popen) -> None:
        with self._lock:
            self.processes.add(process)

    def remove_process(self, process: subprocess.Popen) -> None:
        with self._lock:
            self.processes.discard(process)

    def cancel(self) -> None:
        self.cancel_event.set()
        self.record_cancelled()
        with self._lock:
            processes = list(self.processes)
        for process in processes:
            self._terminate_process(process)

    def _mark_running_locked(self, status: str) -> None:
        for item in self.stages.values():
            if item.get("status") == "running":
                item["status"] = status

    def _terminate_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            if process.poll() is None:
                process.kill()


class RunController:
    def __init__(self) -> None:
        self._active: RunState | None = None
        self._latest: RunState | None = None
        self._lock = threading.Lock()

    def start(self, task: asyncio.Task | None) -> RunState:
        state = RunState(task=task)
        with self._lock:
            if self._active is not None:
                self._active.cancel()
            self._active = state
            self._latest = state
        return state

    def finish(self, state: RunState) -> None:
        with self._lock:
            if self._active is state:
                self._active = None

    def cancel_active(self) -> RunState | None:
        with self._lock:
            state = self._active
        if state is None:
            return None
        state.cancel()
        if state.task is not None and not state.task.done():
            state.task.cancel()
        return state

    def latest_status(self) -> dict:
        with self._lock:
            latest = self._latest
            active = self._active
        if latest is None:
            return {"exists": False, "active": False}
        return latest.snapshot(active=latest is active)


run_controller = RunController()
