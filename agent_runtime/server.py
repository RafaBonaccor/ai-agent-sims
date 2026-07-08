from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import AgentRuntime
from .models import (
    AgentDefinition,
    AgentSnapshot,
    MemoryRecord,
    MemoryUpdate,
    RuntimeEvent,
    ProjectJobPreset,
    ProjectJobPresetCreate,
    TaskCreate,
    TaskRecord,
)
from .protocols import PROTOCOLS
from .project_gateway import ProjectGateway, ProjectJob, ProjectJobCreate
from .logging_config import configure_logging
from .secrets import SecretStore


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
    yield
    await app.state.project_gateway.shutdown()
    await runtime.shutdown()


app = FastAPI(title="Agent Protocol Lab Runtime", version="0.1.0", lifespan=lifespan)


class ClientLog(BaseModel):
    level: str = Field(default="error", pattern=r"^(info|warning|error)$")
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, object] = Field(default_factory=dict)


class SecretValue(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)


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


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "runtime": "native",
        "version": "0.2.0",
        "features": {"projectGateway": True, "persistentLogs": True},
        "agents": len(runtime().agents),
        "activeTasks": len(runtime().running_jobs),
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
async def secret_status(agent_id: str = Query(default="", max_length=80)) -> dict[str, bool]:
    return secrets().status(agent_id or None)


@app.put("/api/secrets/project")
async def set_project_secret(value: SecretValue) -> dict[str, bool]:
    secrets().set_project(value.api_key)
    LOGGER.info("secret_updated scope=project")
    return secrets().status()


@app.delete("/api/secrets/project")
async def delete_project_secret() -> dict[str, bool]:
    secrets().delete_project()
    LOGGER.info("secret_deleted scope=project")
    return secrets().status()


@app.put("/api/agents/{agent_id}/secret")
async def set_agent_secret(agent_id: str, value: SecretValue) -> dict[str, bool]:
    if agent_id not in runtime().agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    secrets().set_agent(agent_id, value.api_key)
    LOGGER.info("secret_updated scope=agent agent=%s", agent_id)
    return secrets().status(agent_id)


@app.delete("/api/agents/{agent_id}/secret")
async def delete_agent_secret(agent_id: str) -> dict[str, bool]:
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


@app.get("/api/tasks", response_model=list[TaskRecord])
async def list_tasks() -> list[TaskRecord]:
    return runtime().list_tasks()


@app.post("/api/tasks", response_model=TaskRecord, status_code=202)
async def create_task(task: TaskCreate) -> TaskRecord:
    return await runtime().create_task(task)


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
    uvicorn.run("agent_runtime.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
