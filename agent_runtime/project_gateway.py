from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    AgentChatMessage,
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
        self.job_alert_states: dict[str, tuple[str, str, bool, bool]] = {}
        self.semaphores: dict[str, asyncio.Semaphore] = {}
        self.processes: dict[str, asyncio.subprocess.Process] = {}
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
            ui_settings = self._project_ui_settings(entry)
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
                            "parameters": self._resolved_parameter_definitions(
                                action.get("parameters", []),
                                ui_settings,
                            ),
                        }
                        for action_id, action in manifest.get("actions", {}).items()
                    ],
                }
            )
        return projects

    def list_jobs(self) -> list[ProjectJob]:
        return sorted(self.jobs.values(), key=lambda job: job.created_at, reverse=True)

    async def cancel_job(self, job_id: str) -> ProjectJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        process = self.processes.pop(job_id, None)
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await asyncio.gather(process.wait(), return_exceptions=True)
        else:
            pid = int((job.result or {}).get("pid") or 0) if isinstance(job.result, dict) else 0
            if pid > 0:
                try:
                    os.kill(pid, 15)
                except OSError:
                    pass
        job.state = "failed"
        job.error = "Stopped by user."
        job.updated_at = utc_now()
        self._store_agent_job_message(job)
        await self._publish(job, "failed")
        return job

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
        allowed = {definition["id"] for definition in ProjectGateway._parameter_definitions(action.get("parameters", []))}
        unknown = sorted(set(parameters) - allowed)
        if unknown:
            raise ValueError(f"Unsupported parameters: {', '.join(unknown)}")

    @staticmethod
    def _parameter_definitions(definitions: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for definition in definitions:
            if isinstance(definition, str):
                normalized.append({"id": definition})
            elif isinstance(definition, dict):
                parameter_id = str(definition.get("id") or "").strip()
                if parameter_id:
                    normalized.append({**definition, "id": parameter_id})
        return normalized

    @classmethod
    def _resolved_parameter_definitions(
        cls,
        definitions: list[Any],
        ui_settings: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for definition in cls._parameter_definitions(definitions):
            item = dict(definition)
            ui_setting_key = item.get("defaultFromUiSetting")
            if isinstance(ui_setting_key, str) and ui_settings and ui_setting_key in ui_settings:
                item["default"] = ui_settings.get(ui_setting_key)
            resolved.append(item)
        return resolved

    def _project_ui_settings(self, entry: dict[str, Any]) -> Optional[dict[str, Any]]:
        path = self._project_root(entry) / "data" / "ui_settings.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

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
                arguments.extend(self._parameter_arguments(job.parameters, action.get("parameters", [])))
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
                if detached:
                    launch_result = await self._launch_detached_process(arguments, project_root, action)
                    job.result = {
                        "ok": True,
                        "command": job.action,
                        **launch_result,
                    }
                    job.state = "completed"
                    job.updated_at = utc_now()
                    self.logger.info(
                        "job_detached id=%s launcher=%s pid=%s",
                        job.id,
                        job.result.get("launcher", "subprocess"),
                        job.result.get("pid"),
                    )
                    self._store_agent_job_message(job)
                    await self._publish(job, "completed")
                    await self._schedule_followup(job, entry, manifest, action)
                    return
                process = await asyncio.create_subprocess_exec(
                    *arguments,
                    cwd=str(project_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self.processes[job.id] = process
                timeout = max(10, int(entry.get("defaultTimeoutSeconds", 900)))
                stdout_text, stderr_text = await asyncio.wait_for(
                    self._communicate_project_process(process, job),
                    timeout=timeout,
                )
                if process.returncode != 0:
                    raise RuntimeError(stderr_text or stdout_text or f"Process exited with {process.returncode}")
                job.result = self._parse_json_output(stdout_text)
                job.state = "completed"
                job.updated_at = utc_now()
                self.logger.info("job_completed id=%s command=%s", job.id, job.result.get("command"))
                self._store_agent_job_message(job)
                await self._publish(job, "completed")
                await self._schedule_followup(job, entry, manifest, action)
            except Exception as error:
                job.state = "failed"
                job.error = str(error)[:4000]
                job.updated_at = utc_now()
                self.logger.exception("job_failed id=%s error=%s", job.id, error)
                self._store_agent_job_message(job)
                await self._publish(job, "failed")
            finally:
                self.processes.pop(job.id, None)

    def _store_agent_job_message(self, job: ProjectJob) -> None:
        if not self.store or not job.agent_id:
            return
        content, sources = self._agent_job_message_content(job)
        message = AgentChatMessage(
            id=f"{job.id}-project-output",
            task_id=job.id,
            role="assistant" if job.state == "completed" else "system",
            content=content,
            sources=sources,
            created_at=job.updated_at,
        )
        self.store.save_agent_chat_message(job.agent_id, message)

    def _agent_job_message_content(self, job: ProjectJob) -> tuple[str, list[dict[str, str]]]:
        if job.state == "failed":
            return (
                f"Project job failed.\nProject: {job.project_id}\nAction: {job.action}\nError: {job.error or 'Unknown error.'}",
                [],
            )
        result = job.result or {}
        normalized = result.get("normalized") if isinstance(result.get("normalized"), dict) else {}
        meta = normalized.get("meta_summary") if isinstance(normalized.get("meta_summary"), dict) else {}
        rows = normalized.get("rows") if isinstance(normalized.get("rows"), list) else result.get("rows")
        rows = rows if isinstance(rows, list) else []
        row_count = result.get("row_count")
        if not isinstance(row_count, int):
            row_count = normalized.get("row_count")
        if not isinstance(row_count, int):
            row_count = meta.get("row_count")
        if not isinstance(row_count, int):
            row_count = len(rows)
        search_term = meta.get("search_term") or normalized.get("search_term") or result.get("search_term") or ""
        source_name = result.get("source") or job.project_id
        lines = [
            "Project job completed.",
            f"Project: {job.project_id}",
            f"Action: {job.action}",
            f"Source: {source_name}",
            f"Rows: {row_count}",
        ]
        if search_term:
            lines.append(f"Search: {search_term}")
        if meta.get("deal_hunter_enabled"):
            lines.append(f"Deal hunter matches: {int(meta.get('deal_hunter_matches', 0) or 0)}")
        preview_rows = [row for row in rows if isinstance(row, dict)][:5]
        if preview_rows:
            lines.append("")
            lines.append("Row preview:")
            for index, row in enumerate(preview_rows, start=1):
                lines.append(f"{index}. {self._format_agent_row_preview(row)}")
        exported_files = normalized.get("exported_files")
        if isinstance(exported_files, list) and exported_files:
            lines.append("")
            lines.append(
                "Exported files: " + ", ".join(str(item) for item in exported_files[:5] if str(item).strip())
            )
        content = "\n".join(lines).strip()
        sources = self._agent_job_sources(rows)
        return content[:6000], sources[:12]

    def _store_agent_job_alert_message(self, job: ProjectJob, alert: dict[str, Any]) -> None:
        if not self.store or not job.agent_id:
            return
        title = str(alert.get("title") or "Project alert").strip()
        summary = str(alert.get("summary") or "A live project alert was emitted.").strip()
        current_url = str(alert.get("current_url") or "").strip()
        content = "\n".join(part for part in (title, summary, current_url) if part).strip()
        message = AgentChatMessage(
            id=f"{job.id}-{str(alert.get('kind') or 'alert').strip()}",
            task_id=job.id,
            role="system",
            content=content,
            sources=[],
            created_at=utc_now(),
        )
        self.store.save_agent_chat_message(job.agent_id, message)

    @staticmethod
    def _format_agent_row_preview(row: dict[str, Any]) -> str:
        title = str(
            row.get("name")
            or row.get("title")
            or row.get("item_id")
            or row.get("id")
            or "item"
        ).strip()
        price = str(
            row.get("price")
            or row.get("base_price")
            or row.get("total_price")
            or row.get("price_value")
            or row.get("total_price_value")
            or ""
        ).strip()
        reason = str(row.get("deal_hunter_reason") or row.get("deal_hunter_label") or "").strip()
        loaded = str(row.get("loaded_at") or row.get("uploaded") or row.get("published") or "").strip()
        parts = [title]
        if price:
            parts.append(price)
        if loaded:
            parts.append(loaded)
        if reason:
            parts.append(reason)
        return " | ".join(parts)

    @staticmethod
    def _agent_job_sources(rows: list[Any]) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("link") or row.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            title = str(row.get("name") or row.get("title") or row.get("item_id") or url).strip()
            sources.append({"title": title, "url": url})
        return sources

    async def _launch_detached_process(
        self,
        arguments: list[str],
        project_root: Path,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        if self._should_launch_via_macos_terminal(action):
            launcher_arguments = self._macos_terminal_command(arguments, project_root)
            process = await asyncio.create_subprocess_exec(
                *launcher_arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if process.returncode != 0:
                raise RuntimeError(stderr_text or stdout_text or "Impossibile aprire Terminal per avviare la GUI.")
            return {
                "launcher": "terminal",
                "message": "Programma avviato in Terminale.",
                "pid": process.pid,
            }
        process_kwargs: dict[str, Any] = {
            "cwd": str(project_root),
            "stdout": asyncio.subprocess.DEVNULL,
            "stderr": asyncio.subprocess.DEVNULL,
        }
        if sys.platform != "win32":
            process_kwargs["start_new_session"] = True
        process = await asyncio.create_subprocess_exec(
            *arguments,
            **process_kwargs,
        )
        return {
            "launcher": "subprocess",
            "message": "Programma avviato.",
            "pid": process.pid,
        }

    @staticmethod
    def _should_launch_via_macos_terminal(action: dict[str, Any]) -> bool:
        return sys.platform == "darwin" and str(action.get("risk", "") or "").strip().lower() == "local-ui"

    @staticmethod
    def _macos_terminal_command(arguments: list[str], project_root: Path) -> list[str]:
        shell_command = f"cd {shlex.quote(str(project_root))} && exec {shlex.join([str(value) for value in arguments])}"
        return [
            "osascript",
            "-e",
            f'tell application "Terminal" to do script {json.dumps(shell_command)}',
            "-e",
            'tell application "Terminal" to activate',
        ]

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

    @classmethod
    def _parameter_arguments(cls, parameters: dict[str, Any], definitions: list[Any] | None = None) -> list[str]:
        arguments: list[str] = []
        definition_map = {
            definition["id"]: definition
            for definition in cls._parameter_definitions(definitions or [])
        }
        for name, value in parameters.items():
            flag = f"--{name}"
            if isinstance(value, bool):
                if value:
                    arguments.append(flag)
                else:
                    definition = definition_map.get(name, {})
                    if bool(definition.get("emitFalseFlag")):
                        arguments.append(f"--no-{name}")
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

    async def _communicate_project_process(
        self,
        process: asyncio.subprocess.Process,
        job: ProjectJob,
    ) -> tuple[str, str]:
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        async def read_stream(stream: asyncio.StreamReader | None, sink: list[str], stream_name: str) -> None:
            if stream is None:
                return
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                sink.append(text)
                if stream_name == "stdout":
                    await self._handle_project_output_line(job, text)

        await asyncio.gather(
            read_stream(process.stdout, stdout_lines, "stdout"),
            read_stream(process.stderr, stderr_lines, "stderr"),
        )
        await process.wait()
        return "\n".join(stdout_lines).strip(), "\n".join(stderr_lines).strip()

    async def _handle_project_output_line(self, job: ProjectJob, line: str) -> None:
        alert = self._project_output_alert(line)
        if alert is None:
            return
        signature = self._project_alert_signature(alert)
        if self.job_alert_states.get(job.id) == signature:
            return
        self.job_alert_states[job.id] = signature
        self._store_agent_job_alert_message(job, alert)
        await self.emit(
            RuntimeEvent(
                type="project.job.alert",
                entity_id=job.id,
                agent_id=job.agent_id,
                summary=str(alert.get("summary") or "Project job alert"),
                data={
                    "job": job.model_dump(mode="json"),
                    "alert": alert,
                },
            )
        )

    @staticmethod
    def _project_output_alert(line: str) -> Optional[dict[str, Any]]:
        if line.startswith("__VINTED_LOGIN_REQUIRED__:"):
            payload = ProjectGateway._parse_project_signal_payload(line)
            current_url = str(payload.get("current_url", "") or "").strip()
            return {
                "kind": "vinted_login_required",
                "title": "Vinted login required",
                "summary": "Vinted requires login. Complete the login in the browser to resume the job.",
                "current_url": current_url,
                "payload": payload,
            }
        if line.startswith("__VINTED_ACCESS__:"):
            payload = ProjectGateway._parse_project_signal_payload(line)
            if bool(payload.get("page_not_found")):
                return {
                    "kind": "vinted_page_not_found",
                    "title": "Vinted page not found",
                    "summary": "The current Vinted page returned Page not found.",
                    "current_url": str(payload.get("current_url", "") or "").strip(),
                    "payload": payload,
                }
            if bool(payload.get("marker_present")):
                return {
                    "kind": "vinted_marker_found",
                    "title": "Vinted account marker found",
                    "summary": "The Vinted account marker is present. The session appears logged in.",
                    "current_url": str(payload.get("current_url", "") or "").strip(),
                    "payload": payload,
                }
            return {
                "kind": "vinted_marker_missing",
                "title": "Vinted account marker missing",
                "summary": "The Vinted account marker is missing. The job may need a manual login.",
                "current_url": str(payload.get("current_url", "") or "").strip(),
                "payload": payload,
            }
        return None

    @staticmethod
    def _parse_project_signal_payload(line: str) -> dict[str, Any]:
        try:
            payload = json.loads(line.split(":", 1)[1].strip())
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _project_alert_signature(alert: dict[str, Any]) -> tuple[str, str, bool, bool]:
        payload = alert.get("payload") if isinstance(alert.get("payload"), dict) else {}
        return (
            str(alert.get("kind", "") or "").strip(),
            str(alert.get("current_url", "") or "").strip(),
            bool(payload.get("marker_present")),
            bool(payload.get("page_not_found")),
        )

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
