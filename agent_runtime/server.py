from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import AgentRuntime
from .models import (
    AgentDefinition,
    AgentSnapshot,
    MemoryRecord,
    MemoryUpdate,
    RuntimeEvent,
    TaskCreate,
    TaskRecord,
)
from .protocols import PROTOCOLS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = AgentRuntime(DATA_DIR / "runtime.db", PROJECT_ROOT / "config" / "agents.json")
    app.state.runtime = runtime
    yield
    await runtime.shutdown()


app = FastAPI(title="Agent Protocol Lab Runtime", version="0.1.0", lifespan=lifespan)


def runtime() -> AgentRuntime:
    return app.state.runtime


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "runtime": "native",
        "agents": len(runtime().agents),
        "activeTasks": len(runtime().running_jobs),
    }


@app.get("/api/agents", response_model=list[AgentSnapshot])
async def list_agents() -> list[AgentSnapshot]:
    return runtime().list_agents()


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
