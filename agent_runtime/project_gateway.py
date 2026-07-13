from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ProjectJobPreset,
    ProjectJobPresetCreate,
    ProjectRepeatMode,
    ProjectScheduleMode,
    RuntimeEvent,
    utc_now,
)
from .scheduler import (
    ScheduledTaskRunner,
    cron_field_matches,
    cron_field_values,
    cron_weekday_matches,
    next_cron_time,
    next_followup_time,
    next_weekday_occurrence,
    normalize_datetime,
    normalize_weekdays,
    resolve_schedule,
)
from .storage import RuntimeStore


EventSink = Callable[[RuntimeEvent], Awaitable[None]]


class ProjectJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[str] = Field(default=None, max_length=80)
    approved: bool = False
    schedule_mode: ProjectScheduleMode = ProjectScheduleMode.IMMEDIATE
    scheduled_for: Optional[datetime] = None
    cron_expression: str = Field(default="", max_length=120)
    repeat_mode: ProjectRepeatMode = ProjectRepeatMode.ONCE
    weekdays: list[int] = Field(default_factory=list)


class ProjectJob(BaseModel):
    id: str = Field(default_factory=lambda: f"job-{uuid4().hex[:12]}")
    project_id: str
    action: str
    parameters: dict[str, Any]
    agent_id: Optional[str] = None
    state: str = "queued"
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    schedule_mode: ProjectScheduleMode = ProjectScheduleMode.IMMEDIATE
    scheduled_for: Optional[datetime] = None
    cron_expression: str = ""
    repeat_mode: ProjectRepeatMode = ProjectRepeatMode.ONCE
    weekdays: list[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProjectGateway:
    def __init__(self, root: Path, emit: EventSink, store: Optional[RuntimeStore] = None):
        self.root = root.resolve()
        self.emit = emit
        self.registry = self._read_json(self.root / "config" / "projects.json")
        local_path = self.root / "config" / "projects.local.json"
        self.local = self._read_json(local_path) if local_path.exists() else {"projects": {}}
        self.jobs: dict[str, ProjectJob] = {}
        self.semaphores: dict[str, asyncio.Semaphore] = {}
        self.logger = logging.getLogger("agent_lab.gateway")
        self.scheduler = ScheduledTaskRunner(self.logger)
        self.running = self.scheduler.running
        self.store = store

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def list_projects(self) -> list[dict[str, Any]]:
        projects = []
        for entry in self.registry.get("projects", []):
            manifest = self._manifest(entry)
            projects.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "enabled": bool(entry.get("enabled", True)),
                    "available": self._project_root(entry).is_dir(),
                    "actions": [
                        {
                            "id": action_id,
                            "label": action.get("label", action_id),
                            "description": action.get("description", ""),
                            "risk": action.get("risk", "read"),
                            "requiresApproval": bool(action.get("requiresApproval", False)),
                            "parameters": action.get("parameters", []),
                        }
                        for action_id, action in manifest.get("actions", {}).items()
                    ],
                }
            )
        return projects

    def list_jobs(self) -> list[ProjectJob]:
        return sorted(self.jobs.values(), key=lambda job: job.created_at, reverse=True)

    def list_presets(self, project_id: Optional[str] = None) -> list[ProjectJobPreset]:
        return self.store.load_project_job_presets(project_id) if self.store else []

    def create_preset(self, request: ProjectJobPresetCreate) -> ProjectJobPreset:
        self._validate_action_parameters(request.project_id, request.action, request.parameters)
        if not self.store:
            raise RuntimeError("Preset storage is not available")
        preset = ProjectJobPreset(**request.model_dump())
        self.store.save_project_job_preset(preset)
        self.logger.info(
            "preset_created id=%s project=%s action=%s parameters=%s",
            preset.id,
            preset.project_id,
            preset.action,
            sorted(preset.parameters),
        )
        return preset

    def delete_preset(self, preset_id: str) -> bool:
        deleted = self.store.delete_project_job_preset(preset_id) if self.store else False
        if deleted:
            self.logger.info("preset_deleted id=%s", preset_id)
        return deleted

    async def create_job(self, request: ProjectJobCreate) -> ProjectJob:
        entry = self._project_entry(request.project_id)
        if not entry.get("enabled", True):
            raise ValueError(f"Project is disabled: {request.project_id}")
        manifest = self._manifest(entry)
        action = manifest.get("actions", {}).get(request.action)
        if action is None:
            raise ValueError(f"Action is not registered: {request.action}")
        if action.get("requiresApproval") and not request.approved:
            raise PermissionError(f"Action requires explicit approval: {request.action}")
        self._validate_parameters(action, request.parameters)
        scheduled_for = self._resolve_schedule(request)
        weekdays = self._normalize_weekdays(request.weekdays)

        job = ProjectJob(
            **request.model_dump(
                exclude={"approved", "scheduled_for", "cron_expression", "schedule_mode", "repeat_mode", "weekdays"}
            ),
            schedule_mode=request.schedule_mode,
            scheduled_for=scheduled_for,
            cron_expression=request.cron_expression.strip(),
            repeat_mode=request.repeat_mode,
            weekdays=weekdays,
        )
        self.jobs[job.id] = job
        if scheduled_for and scheduled_for > utc_now():
            job.state = "scheduled"
            self.logger.info(
                "job_scheduled id=%s project=%s action=%s agent=%s run_at=%s parameters=%s",
                job.id,
                job.project_id,
                job.action,
                job.agent_id or "-",
                scheduled_for.isoformat(),
                sorted(job.parameters),
            )
            await self._publish(job, "scheduled")
            self.scheduler.schedule_at(job.id, scheduled_for, lambda: self._queue_and_run(job, entry, manifest, action))
        else:
            self.logger.info(
                "job_queued id=%s project=%s action=%s agent=%s parameters=%s",
                job.id,
                job.project_id,
                job.action,
                job.agent_id or "-",
                sorted(job.parameters),
            )
            await self._publish(job, "queued")
            self.scheduler.start(self._run(job, entry, manifest, action), name=job.id)
        return job

    def _resolve_schedule(self, request: ProjectJobCreate) -> Optional[datetime]:
        return resolve_schedule(request.schedule_mode, request.scheduled_for, request.cron_expression, utc_now())

    @staticmethod
    def _normalize_weekdays(weekdays: list[int]) -> list[int]:
        return normalize_weekdays(weekdays)

    @staticmethod
    def _normalize_datetime(value: datetime) -> datetime:
        return normalize_datetime(value)

    async def _queue_and_run(
        self,
        job: ProjectJob,
        entry: dict[str, Any],
        manifest: dict[str, Any],
        action: dict[str, Any],
    ) -> None:
        job.state = "queued"
        job.updated_at = utc_now()
        await self._publish(job, "queued")
        await self._run(job, entry, manifest, action)

    def _validate_action_parameters(
        self, project_id: str, action_id: str, parameters: dict[str, Any]
    ) -> None:
        entry = self._project_entry(project_id)
        action = self._manifest(entry).get("actions", {}).get(action_id)
        if action is None:
            raise ValueError(f"Action is not registered: {action_id}")
        self._validate_parameters(action, parameters)

    @staticmethod
    def _validate_parameters(action: dict[str, Any], parameters: dict[str, Any]) -> None:
        allowed = set(action.get("parameters", []))
        unknown = sorted(set(parameters) - allowed)
        if unknown:
            raise ValueError(f"Unsupported parameters: {', '.join(unknown)}")

    async def _run(
        self,
        job: ProjectJob,
        entry: dict[str, Any],
        manifest: dict[str, Any],
        action: dict[str, Any],
    ) -> None:
        limit = max(1, int(entry.get("maxConcurrentJobs", 1)))
        semaphore = self.semaphores.setdefault(job.project_id, asyncio.Semaphore(limit))
        async with semaphore:
            try:
                project_root = self._project_root(entry)
                executable = self._python_executable(entry, manifest, project_root)
                entrypoint = (project_root / manifest["runtime"]["entrypoint"]).resolve()
                if not entrypoint.is_relative_to(project_root):
                    raise ValueError("Project entrypoint escapes its project root")
                if not executable.is_file() or not entrypoint.is_file():
                    raise FileNotFoundError("Python executable or project entrypoint is missing")

                arguments = [str(executable), str(entrypoint), *action.get("arguments", [])]
                arguments.extend(self._parameter_arguments(job.parameters))
                job.state = "running"
                job.updated_at = utc_now()
                await self._publish(job, "started")
                self.logger.info(
                    "job_started id=%s executable=%s cwd=%s flags=%s",
                    job.id,
                    executable,
                    project_root,
                    [value for value in arguments[2:] if str(value).startswith("--")],
                )

                detached = action.get("mode") == "detached"
                process = await asyncio.create_subprocess_exec(
                    *arguments,
                    cwd=str(project_root),
                    stdout=asyncio.subprocess.DEVNULL if detached else asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL if detached else asyncio.subprocess.PIPE,
                )
                if detached:
                    job.result = {
                        "ok": True,
                        "command": job.action,
                        "pid": process.pid,
                        "message": "Programma avviato.",
                    }
                    job.state = "completed"
                    job.updated_at = utc_now()
                    self.logger.info("job_detached id=%s pid=%s", job.id, process.pid)
                    await self._publish(job, "completed")
                    await self._schedule_followup(job, entry, manifest, action)
                    return
                timeout = max(10, int(entry.get("defaultTimeoutSeconds", 900)))
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                stdout_text = stdout.decode("utf-8", errors="replace").strip()
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                if process.returncode != 0:
                    raise RuntimeError(stderr_text or stdout_text or f"Process exited with {process.returncode}")
                job.result = self._parse_json_output(stdout_text)
                job.state = "completed"
                job.updated_at = utc_now()
                self.logger.info("job_completed id=%s command=%s", job.id, job.result.get("command"))
                await self._publish(job, "completed")
                await self._schedule_followup(job, entry, manifest, action)
            except Exception as error:
                job.state = "failed"
                job.error = str(error)[:4000]
                job.updated_at = utc_now()
                self.logger.exception("job_failed id=%s error=%s", job.id, error)
                await self._publish(job, "failed")

    async def _schedule_followup(
        self,
        job: ProjectJob,
        entry: dict[str, Any],
        manifest: dict[str, Any],
        action: dict[str, Any],
    ) -> None:
        next_run = self._next_followup_time(job)
        if next_run is None:
            return
        followup = ProjectJob(
            project_id=job.project_id,
            action=job.action,
            parameters=dict(job.parameters),
            agent_id=job.agent_id,
            schedule_mode=ProjectScheduleMode.AT if job.schedule_mode == ProjectScheduleMode.AT else ProjectScheduleMode.CRON,
            scheduled_for=next_run,
            cron_expression=job.cron_expression,
            repeat_mode=job.repeat_mode,
            weekdays=list(job.weekdays),
        )
        self.jobs[followup.id] = followup
        if followup.schedule_mode == ProjectScheduleMode.AT:
            followup.state = "scheduled"
            self.logger.info(
                "job_repeated id=%s source=%s mode=%s run_at=%s",
                followup.id,
                job.id,
                followup.repeat_mode.value,
                next_run.isoformat(),
            )
            await self._publish(followup, "scheduled")
            self.scheduler.schedule_at(
                followup.id,
                next_run,
                lambda: self._queue_and_run(followup, entry, manifest, action),
            )
        else:
            followup.state = "scheduled"
            self.logger.info(
                "job_repeated id=%s source=%s mode=cron run_at=%s",
                followup.id,
                job.id,
                next_run.isoformat(),
            )
            await self._publish(followup, "scheduled")
            self.scheduler.schedule_at(
                followup.id,
                next_run,
                lambda: self._queue_and_run(followup, entry, manifest, action),
            )

    def _next_followup_time(self, job: ProjectJob) -> Optional[datetime]:
        return next_followup_time(
            schedule_mode=job.schedule_mode,
            scheduled_for=job.scheduled_for,
            cron_expression=job.cron_expression,
            repeat_mode=job.repeat_mode,
            weekdays=job.weekdays,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _next_weekday_occurrence(base: datetime, weekdays: list[int]) -> Optional[datetime]:
        return next_weekday_occurrence(base, weekdays)

    @staticmethod
    def _next_cron_time(expression: str, start: datetime) -> datetime:
        return next_cron_time(expression, start)

    @staticmethod
    def _cron_weekday_matches(moment: datetime, field: str) -> bool:
        return cron_weekday_matches(moment, field)

    @staticmethod
    def _cron_field_matches(value: int, field: str, minimum: int, maximum: int) -> bool:
        return cron_field_matches(value, field, minimum, maximum)

    @staticmethod
    def _cron_field_values(field: str, minimum: int, maximum: int) -> set[int]:
        return cron_field_values(field, minimum, maximum)

    @staticmethod
    def _parameter_arguments(parameters: dict[str, Any]) -> list[str]:
        arguments: list[str] = []
        for name, value in parameters.items():
            flag = f"--{name}"
            if isinstance(value, bool):
                if value:
                    arguments.append(flag)
            elif value is not None and str(value).strip() != "":
                arguments.extend((flag, str(value)))
        return arguments

    @staticmethod
    def _parse_json_output(output: str) -> dict[str, Any]:
        for line in reversed(output.splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise ValueError("Project did not return a JSON object on stdout")

    def _project_entry(self, project_id: str) -> dict[str, Any]:
        for entry in self.registry.get("projects", []):
            if entry.get("id") == project_id:
                return entry
        raise KeyError(project_id)

    def _project_root(self, entry: dict[str, Any]) -> Path:
        path = (self.root / entry["root"]).resolve()
        if not path.is_relative_to(self.root / "projects"):
            raise ValueError("Project root must remain inside projects/")
        return path

    def _manifest(self, entry: dict[str, Any]) -> dict[str, Any]:
        path = (self.root / entry["integration"]).resolve()
        if not path.is_relative_to(self.root / "integrations"):
            raise ValueError("Integration manifest must remain inside integrations/")
        return self._read_json(path)

    def _python_executable(
        self, entry: dict[str, Any], manifest: dict[str, Any], project_root: Path
    ) -> Path:
        local = self.local.get("projects", {}).get(entry["id"], {})
        configured = local.get("pythonExecutable")
        if configured:
            return Path(configured).expanduser()
        for candidate in manifest["runtime"].get("venvCandidates", []):
            path = project_root / candidate
            if path.is_file():
                return path
        raise FileNotFoundError(f"No Python environment configured for {entry['id']}")

    async def _publish(self, job: ProjectJob, phase: str) -> None:
        await self.emit(
            RuntimeEvent(
                type=f"project.job.{phase}",
                entity_id=job.id,
                agent_id=job.agent_id,
                summary=f"{job.action}: {phase}",
                data={"job": job.model_dump(mode="json")},
            )
        )

    async def shutdown(self) -> None:
        await self.scheduler.shutdown()
