from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import AgentRuntime
from .browser_control import BrowserControlError
from .models import (
    AgentDefinition,
    AgentChatMessage,
    AgentSnapshot,
    MemoryRecord,
    MemoryUpdate,
    RuntimeEvent,
    ProjectJobPreset,
    ProjectJobPresetCreate,
    TaskCreate,
    TaskRecord,
    WikiRecord,
    WikiUpdate,
)
from .protocols import PROTOCOLS
from .project_gateway import ProjectGateway, ProjectJob, ProjectJobCreate
from .logging_config import configure_logging
from .secrets import SecretStore
from .discord_gateway import DiscordGateway
from .briefings import MorningBriefingScheduler


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGGER = configure_logging(PROJECT_ROOT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    secrets = SecretStore(DATA_DIR / "secrets.json")
    runtime = AgentRuntime(
        DATA_DIR / "runtime.db", PROJECT_ROOT / "config" / "agents.json", secrets=secrets
    )
    app.state.runtime = runtime
    app.state.secrets = secrets
    app.state.project_gateway = ProjectGateway(PROJECT_ROOT, runtime.publish, runtime.store)
    app.state.discord_gateway = DiscordGateway(runtime)
    app.state.ai_news_briefing = MorningBriefingScheduler(runtime)
    await app.state.ai_news_briefing.start()
    await app.state.discord_gateway.start()
    yield
    await app.state.discord_gateway.shutdown()
    await app.state.ai_news_briefing.shutdown()
    await app.state.project_gateway.shutdown()
    await runtime.shutdown()


app = FastAPI(title="Agent Protocol Lab Runtime", version="0.1.0", lifespan=lifespan)


class ClientLog(BaseModel):
    level: str = Field(default="error", pattern=r"^(info|warning|error)$")
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, object] = Field(default_factory=dict)


class SecretValue(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)


class BrowserSessionCreate(BaseModel):
    project_id: str = Field(default="main-scraper", max_length=80)
    backend: str = Field(default="botasaurus", pattern=r"^(botasaurus|mock|auto)$")
    url: str = Field(default="", max_length=2000)
    browser_mode: str = Field(default="sessione_persistente", max_length=80)
    browser_user_data_dir: str = Field(default="", max_length=1000)
    browser_profile_directory: str = Field(default="Default", max_length=120)
    refresh_browser_profile: bool = False
    page_text: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=200)


class BrowserCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=80)
    parameters: dict[str, object] = Field(default_factory=dict)


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("http_failed method=%s path=%s", request.method, request.url.path)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    LOGGER.info(
        "http method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    if request.url.path == "/" or request.url.path.endswith((".mjs", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store"
    return response


def runtime() -> AgentRuntime:
    return app.state.runtime


def project_gateway() -> ProjectGateway:
    return app.state.project_gateway


def secrets() -> SecretStore:
    return app.state.secrets


def discord_gateway() -> DiscordGateway | None:
    return getattr(app.state, "discord_gateway", None)


def ai_news_briefing() -> MorningBriefingScheduler | None:
    return getattr(app.state, "ai_news_briefing", None)


@app.get("/api/health")
async def health() -> dict[str, object]:
    discord = discord_gateway()
    briefing = ai_news_briefing()
    return {
        "status": "ok",
        "runtime": "native",
        "version": "0.2.0",
        "features": {
            "projectGateway": True,
            "persistentLogs": True,
            "browserControl": True,
            "discordGateway": bool(discord and discord.enabled),
            "aiNewsBriefing": bool(briefing and briefing.config.enabled),
        },
        "agents": len(runtime().agents),
        "activeTasks": len(runtime().running_jobs),
        "browserSessions": len(runtime().browser_control.list_sessions()),
        "discord": discord.status() if discord else {"enabled": False, "connected": False},
        "aiNewsBriefing": briefing.status() if briefing else {"enabled": False},
    }


@app.get("/api/diagnostics/logs")
async def recent_logs(lines: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
    path = PROJECT_ROOT / "runtime" / "agent-lab.log"
    content = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
    return {"path": str(path), "lines": content[-lines:]}


@app.post("/api/diagnostics/client", status_code=202)
async def client_log(entry: ClientLog) -> dict[str, bool]:
    log_method = getattr(LOGGER, entry.level, LOGGER.error)
    log_method("client message=%s context=%s", entry.message, entry.context)
    return {"accepted": True}


@app.get("/api/agents", response_model=list[AgentSnapshot])
async def list_agents() -> list[AgentSnapshot]:
    return runtime().list_agents()


@app.get("/api/secrets/status")
async def secret_status(agent_id: str = Query(default="", max_length=80)) -> dict[str, object]:
    return secrets().status(agent_id or None)


@app.put("/api/secrets/project")
async def set_project_secret(value: SecretValue) -> dict[str, object]:
    try:
        secrets().set_project(value.api_key)
        LOGGER.info("secret_updated scope=project")
        return secrets().status()
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/secrets/project")
async def delete_project_secret() -> dict[str, object]:
    secrets().delete_project()
    LOGGER.info("secret_deleted scope=project")
    return secrets().status()


@app.put("/api/agents/{agent_id}/secret")
async def set_agent_secret(agent_id: str, value: SecretValue) -> dict[str, object]:
    if agent_id not in runtime().agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        secrets().set_agent(agent_id, value.api_key)
        LOGGER.info("secret_updated scope=agent agent=%s", agent_id)
        return secrets().status(agent_id)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/agents/{agent_id}/secret")
async def delete_agent_secret(agent_id: str) -> dict[str, object]:
    if agent_id not in runtime().agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    secrets().delete_agent(agent_id)
    LOGGER.info("secret_deleted scope=agent agent=%s", agent_id)
    return secrets().status(agent_id)


@app.post("/api/agents", response_model=AgentSnapshot, status_code=201)
async def create_agent(definition: AgentDefinition) -> AgentSnapshot:
    try:
        return await runtime().add_agent(definition)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.put("/api/agents/{agent_id}", response_model=AgentSnapshot)
async def update_agent(agent_id: str, definition: AgentDefinition) -> AgentSnapshot:
    try:
        return await runtime().update_agent(agent_id, definition)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/agents/{agent_id}/memory", response_model=MemoryRecord)
async def get_agent_memory(agent_id: str) -> MemoryRecord:
    try:
        return runtime().get_memory(agent_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent not found") from error


@app.put("/api/agents/{agent_id}/memory", response_model=MemoryRecord)
async def update_agent_memory(agent_id: str, update: MemoryUpdate) -> MemoryRecord:
    try:
        return await runtime().update_memory(agent_id, update)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent not found") from error


@app.get("/api/agents/{agent_id}/wiki", response_model=WikiRecord)
async def get_agent_wiki(agent_id: str) -> WikiRecord:
    try:
        return runtime().get_wiki(agent_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent not found") from error


@app.put("/api/agents/{agent_id}/wiki", response_model=WikiRecord)
async def update_agent_wiki(agent_id: str, update: WikiUpdate) -> WikiRecord:
    try:
        return await runtime().update_wiki(agent_id, update)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent not found") from error


@app.get("/api/agents/{agent_id}/chat", response_model=list[AgentChatMessage])
async def get_agent_chat(agent_id: str) -> list[AgentChatMessage]:
    try:
        return runtime().get_agent_chat(agent_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Agent not found") from error


@app.get("/api/tasks", response_model=list[TaskRecord])
async def list_tasks() -> list[TaskRecord]:
    return runtime().list_tasks()


@app.post("/api/tasks", response_model=TaskRecord, status_code=202)
async def create_task(task: TaskCreate) -> TaskRecord:
    return await runtime().create_task(task)


@app.get("/api/briefings/ai-news")
async def ai_news_briefing_status() -> dict[str, object]:
    briefing = ai_news_briefing()
    return briefing.status() if briefing else {"enabled": False}


@app.post("/api/briefings/ai-news/run", response_model=TaskRecord, status_code=202)
async def run_ai_news_briefing(force: bool = Query(default=False)) -> TaskRecord:
    briefing = ai_news_briefing()
    if briefing is None:
        raise HTTPException(status_code=404, detail="AI news briefing is not configured")
    try:
        return await briefing.create_briefing(force=force)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/events", response_model=list[RuntimeEvent])
async def list_events(limit: int = Query(default=100, ge=1, le=500)) -> list[RuntimeEvent]:
    return runtime().store.recent_events(limit)


@app.get("/api/tools")
async def list_tools() -> list[dict[str, object]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "toolset": tool.toolset,
            "risk": tool.risk,
        }
        for tool in runtime().executor.tools.DEFINITIONS.values()
    ]


@app.get("/api/browser/sessions")
async def list_browser_sessions() -> list[dict[str, object]]:
    return runtime().browser_control.list_sessions()


@app.post("/api/browser/sessions", status_code=201)
async def create_browser_session(request: BrowserSessionCreate) -> dict[str, object]:
    try:
        return await runtime().browser_control.open_session(**request.model_dump())
    except BrowserControlError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/browser/sessions/{session_id}/commands")
async def run_browser_command(session_id: str, request: BrowserCommandRequest) -> dict[str, object]:
    try:
        return await runtime().browser_control.command(session_id, request.command, request.parameters)
    except BrowserControlError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.delete("/api/browser/sessions/{session_id}")
async def close_browser_session(session_id: str) -> dict[str, object]:
    try:
        return await runtime().browser_control.close_session(session_id)
    except BrowserControlError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/projects")
async def list_projects() -> list[dict[str, object]]:
    return project_gateway().list_projects()


@app.get("/api/project-jobs", response_model=list[ProjectJob])
async def list_project_jobs() -> list[ProjectJob]:
    return project_gateway().list_jobs()


@app.post("/api/project-jobs", response_model=ProjectJob, status_code=202)
async def create_project_job(request: ProjectJobCreate) -> ProjectJob:
    try:
        return await project_gateway().create_job(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/project-presets", response_model=list[ProjectJobPreset])
async def list_project_presets(project_id: str = Query(default="", max_length=80)) -> list[ProjectJobPreset]:
    return project_gateway().list_presets(project_id or None)


@app.post("/api/project-presets", response_model=ProjectJobPreset, status_code=201)
async def create_project_preset(request: ProjectJobPresetCreate) -> ProjectJobPreset:
    try:
        return project_gateway().create_preset(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/project-presets/{preset_id}")
async def delete_project_preset(preset_id: str) -> dict[str, bool]:
    if not project_gateway().delete_preset(preset_id):
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"deleted": True}


@app.get("/api/protocols")
async def list_protocols() -> list[dict[str, object]]:
    return [
        {"id": protocol.id, "messageTypes": sorted(protocol.message_types)}
        for protocol in PROTOCOLS.values()
    ]


@app.websocket("/ws/events")
async def event_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = runtime().subscribe()
    try:
        await websocket.send_json(
            {
                "type": "runtime.snapshot",
                "agents": [agent.model_dump(mode="json") for agent in runtime().list_agents()],
                "tasks": [task.model_dump(mode="json") for task in runtime().list_tasks()],
                "events": [event.model_dump(mode="json") for event in runtime().store.recent_events(40)],
            }
        )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
                await websocket.send_json(event.model_dump(mode="json"))
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "runtime.ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        runtime().unsubscribe(queue)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "index.html")


@app.get("/app.mjs")
async def application_script() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "app.mjs", media_type="text/javascript")


@app.get("/styles.css")
async def stylesheet() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "styles.css", media_type="text/css")


app.mount("/src", StaticFiles(directory=PROJECT_ROOT / "src"), name="src")


def main() -> None:
    host = os.environ.get("AGENT_LAB_HOST", "127.0.0.1")
    port = int(os.environ.get("AGENT_LAB_PORT", "8000"))
    uvicorn.run("agent_runtime.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
