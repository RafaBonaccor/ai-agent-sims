from __future__ import annotations

import asyncio
import base64
import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
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
    SystemSettings,
    TaskCreate,
    TaskRecord,
    WikiMaintenanceResult,
    WikiPageContent,
    WikiPageRecord,
    WikiRecord,
    WikiProposalRecord,
    WikiProposalResolveRequest,
    WikiSearchResult,
    WikiUpdate,
)
from .protocols import PROTOCOLS
from .project_gateway import ProjectGateway, ProjectJob, ProjectJobCreate
from .logging_config import configure_logging
from .secrets import SecretStore
from .discord_gateway import DiscordGateway, DiscordGatewayConfig
from .briefings import MorningBriefingScheduler
from .vinted_ai import (
    generate_vinted_ai_variants,
    DEFAULT_VINTED_AI_MODEL,
    DEFAULT_VINTED_AI_QUALITY,
    DEFAULT_VINTED_AI_SIZE,
)
from .error_reporting import RuntimeErrorReporter
from .vinted_reports import (
    build_vinted_competitor_report,
    build_vinted_report,
    deactivate_owned_profile,
    ignore_owned_profile_item,
    save_owned_profile,
    write_vinted_report_html,
)
from .linkedin_reports import (
    LinkedInReportError, archive_linkedin_media, archived_media_path,
    get_linkedin_post, list_linkedin_posts, save_linkedin_rewrite,
)
from .linkedin_publisher import (
    LinkedInPublishError, attach_source_image_to_draft, create_draft, draft_attachment_path, list_drafts, publish_draft,
    publisher_status, update_draft,
)
from .runpod_manager import RunPodManager, RunPodManagerError
from .appium_manager import AppiumManager, AppiumManagerError
from .runpod_batches import RunPodBatchError, RunPodBatchService
from .runpod_gpu_watch import RunPodGpuWatch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RUNPOD_WORKFLOW_LIBRARY_PATH = PROJECT_ROOT / "config" / "runpod_workflows.json"
COMFYUI_PROMPT_PRESETS_PATH = PROJECT_ROOT / "config" / "comfyui_prompt_presets.json"
LOGGER = configure_logging(PROJECT_ROOT)


class OwnedMarketplaceProfileRequest(BaseModel):
    profile_url: str = Field(min_length=1, max_length=512)
    display_name: str = Field(default="", max_length=120)


class MarketplaceSourcingItemRequest(BaseModel):
    item_id: str = Field(default="", max_length=80)
    name: str = Field(default="", max_length=300)
    link: str = Field(min_length=1, max_length=2048)
    image_url: str = Field(default="", max_length=4096)
    archive_image_path: str = Field(default="", max_length=4096)


class MarketplaceSourcingBatchRequest(BaseModel):
    items: list[MarketplaceSourcingItemRequest] = Field(min_length=1, max_length=50)
    max_results: int = Field(default=40, ge=1, le=200)


class LinkedInRewriteRequest(BaseModel):
    instruction: str = Field(default="", max_length=500)
    prompt: str | None = Field(default=None, max_length=15000)


class LinkedInDraftRequest(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    source_post_id: str = Field(default="", max_length=200)


class LinkedInPublishRequest(BaseModel):
    expected_body: str = Field(min_length=1, max_length=3000)


class AppiumLaunchRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=255)
    bundle_id: str = Field(min_length=3, max_length=255)


@asynccontextmanager
async def lifespan(app: FastAPI):
    secrets = SecretStore(DATA_DIR / "secrets.json")
    runtime = AgentRuntime(
        DATA_DIR / "runtime.db", PROJECT_ROOT / "config" / "agents.json", secrets=secrets
    )
    error_reporter = RuntimeErrorReporter(PROJECT_ROOT, runtime.get_system_settings)
    app.state.runtime = runtime
    app.state.secrets = secrets
    app.state.error_reporter = error_reporter
    app.state.project_gateway = ProjectGateway(
        PROJECT_ROOT, runtime.publish, runtime.store, error_reporter=error_reporter
    )
    app.state.runpod_batches = RunPodBatchService(
        DATA_DIR / "runpod_batches",
        lambda: RunPodManager(runtime.get_system_settings().runpod, secrets.get_runpod_api_key()),
        lambda: list(getattr(app.state, "runpod_gpu_watch", None).status().get("gpu_ids") or []) if getattr(app.state, "runpod_gpu_watch", None) else [],
        lambda region, gpus: app.state.runpod_gpu_watch.record_inventory(region, gpus, "batch-deploy") if getattr(app.state, "runpod_gpu_watch", None) else None,
    )
    loop = asyncio.get_running_loop()
    def gpu_available(event: dict[str, object]) -> None:
        # A GPU availability edge is also the durable queue wake-up signal.
        app.state.runpod_batches.resume_waiting_batches()
        asyncio.run_coroutine_threadsafe(runtime.publish(RuntimeEvent(
            type="runpod.gpu.available", entity_id=str(event.get("id", "")), agent_id="runpod-manager",
            summary=f"GPU available: {event.get('name', event.get('id', 'RunPod GPU'))}", data=event,
        )), loop)
    app.state.runpod_gpu_watch = RunPodGpuWatch(DATA_DIR / "runpod_gpu_watch.json", lambda: RunPodManager(runtime.get_system_settings().runpod, secrets.get_runpod_api_key()), gpu_available)
    if bool(app.state.runpod_gpu_watch.status().get("enabled")):
        app.state.runpod_gpu_watch.start()
    app.state.discord_gateway = build_discord_gateway()
    app.state.ai_news_briefing = MorningBriefingScheduler(
        runtime,
        on_task_created=app.state.discord_gateway.watch_task_result,
    )
    app.state.wiki_maintenance_task = _start_wiki_maintenance_task(runtime)
    await app.state.ai_news_briefing.start()
    await app.state.discord_gateway.start()
    yield
    if app.state.wiki_maintenance_task:
        app.state.wiki_maintenance_task.cancel()
        await asyncio.gather(app.state.wiki_maintenance_task, return_exceptions=True)
    await app.state.discord_gateway.shutdown()
    app.state.runpod_gpu_watch.shutdown()
    await app.state.ai_news_briefing.shutdown()
    await app.state.project_gateway.shutdown()
    await runtime.shutdown()


app = FastAPI(title="Agent Protocol Lab Runtime", version="0.1.0", lifespan=lifespan)


def _start_wiki_maintenance_task(runtime: AgentRuntime) -> asyncio.Task[None] | None:
    raw_interval = os.environ.get("AGENT_LAB_WIKI_MAINTENANCE_INTERVAL_SECONDS", "").strip()
    if not raw_interval:
        return None
    try:
        interval = max(300, int(raw_interval))
    except ValueError:
        LOGGER.warning("wiki_maintenance_invalid_interval value=%s", raw_interval)
        return None

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await runtime.run_wiki_maintenance()
            except Exception:
                LOGGER.exception("wiki_maintenance_failed")

    return asyncio.create_task(loop(), name="wiki-maintenance")


class ClientLog(BaseModel):
    level: str = Field(default="error", pattern=r"^(info|warning|error)$")
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, object] = Field(default_factory=dict)


class ErrorReportRequest(BaseModel):
    source: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, object] = Field(default_factory=dict)
    screenshot_data_url: str = Field(default="", max_length=20_000_000)


class SecretValue(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)


class RunPodCreateRequest(BaseModel):
    name: str = Field(default="Agent Lab ComfyUI", min_length=1, max_length=120)
    gpu_id: str = Field(default="", max_length=160)


class RunPodWorkflowRequest(BaseModel):
    workflow: dict[str, object] = Field(default_factory=dict)
    media_name: str = Field(default="", max_length=500)
    media_kind: str = Field(default="", pattern=r"^(|image|video)$")
    media_loader_id: str = Field(default="", max_length=120)


class RunPodComfyUiUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    data_base64: str = Field(min_length=1, max_length=40_000_000)
    overwrite: bool = True


class RunPodBatchCreateRequest(BaseModel):
    workflow: dict[str, object] = Field(default_factory=dict)
    media_loader_id: str = Field(default="", max_length=120)
    auto_deploy: bool = True
    auto_shutdown: bool = True
    min_vram_gb: int = Field(default=0, ge=0, le=512)
    workflow_id: str = Field(default="", max_length=120)
    creative_prompt: str = Field(default="", max_length=12000)


class RunPodBatchMediaRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    data_base64: str = Field(min_length=1, max_length=40_000_000)


class RunPodGpuWatchRequest(BaseModel):
    enabled: bool = True
    gpu_ids: list[str] = Field(default_factory=list, max_length=12)
    interval_seconds: int = Field(default=60, ge=30, le=3600)

class CreativePromptRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    image_base64: str = Field(min_length=1, max_length=40_000_000)


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


class VintedAIGenerationRequest(BaseModel):
    photo_paths: list[str] = Field(default_factory=list)
    prompt: str = Field(min_length=1, max_length=8000)
    output_dir: str = Field(min_length=1, max_length=2000)
    model: str = Field(default=DEFAULT_VINTED_AI_MODEL, max_length=160)
    size: str = Field(default=DEFAULT_VINTED_AI_SIZE, max_length=32)
    quality: str = Field(default=DEFAULT_VINTED_AI_QUALITY, max_length=32)
    variants: int = Field(default=1, ge=1, le=4)


class VintedAIGenerationResponse(BaseModel):
    ok: bool
    model: str
    size: str
    quality: str
    prompt: str
    source_photo_paths: list[str]
    generated_photo_paths: list[str]
    output_dir: str
    variants: int
    generated_at: str
    log_path: str
    backend: str
    runtime_url: str
    request_url: str


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("http_failed method=%s path=%s", request.method, request.url.path)
        reporter = error_reporter()
        if reporter and request.url.path != "/api/diagnostics/report-error":
            try:
                await reporter.report(
                    source="runtime.http",
                    message="Unhandled runtime exception",
                    context={
                        "method": request.method,
                        "path": request.url.path,
                        "phase": "middleware",
                    },
                )
            except Exception:
                LOGGER.exception("http_failure_report_failed path=%s", request.url.path)
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


def error_reporter() -> RuntimeErrorReporter | None:
    return getattr(app.state, "error_reporter", None)


def build_discord_gateway() -> DiscordGateway:
    settings = runtime().get_system_settings()
    token = str(secrets().get_discord_bot_token() or "").strip()
    config = DiscordGatewayConfig.from_system_settings(settings, token)
    return DiscordGateway(runtime(), project_gateway=project_gateway(), config=config)


async def reload_discord_gateway() -> DiscordGateway:
    current = discord_gateway()
    if current is not None:
        await current.shutdown()
    app.state.discord_gateway = build_discord_gateway()
    await app.state.discord_gateway.start()
    return app.state.discord_gateway


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


@app.post("/api/diagnostics/report-error", status_code=202)
async def report_client_error(entry: ErrorReportRequest) -> dict[str, object]:
    LOGGER.error("client_error_report source=%s message=%s context=%s", entry.source, entry.message, entry.context)
    reporter = error_reporter()
    if reporter is None:
        return {"accepted": False, "reason": "reporter_unavailable"}
    result = await reporter.report(
        source=entry.source,
        message=entry.message,
        context=entry.context,
        screenshot_data_url=entry.screenshot_data_url,
    )
    return {"accepted": True, "report": result}


@app.get("/api/agents", response_model=list[AgentSnapshot])
async def list_agents() -> list[AgentSnapshot]:
    return runtime().list_agents()


@app.get("/api/system-settings", response_model=SystemSettings)
async def get_system_settings() -> SystemSettings:
    return runtime().get_system_settings()


@app.get("/api/appium/status")
async def appium_status() -> dict[str, object]:
    try:
        return AppiumManager(runtime().get_system_settings().appium).status()
    except AppiumManagerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/appium/start")
async def appium_start() -> dict[str, object]:
    try:
        result = AppiumManager(runtime().get_system_settings().appium).start_server()
        return {**result, "status": AppiumManager(runtime().get_system_settings().appium).status()}
    except AppiumManagerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/appium/stop")
async def appium_stop() -> dict[str, object]:
    try:
        result = AppiumManager(runtime().get_system_settings().appium).stop_server()
        return {**result, "status": AppiumManager(runtime().get_system_settings().appium).status()}
    except AppiumManagerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/appium/apps")
def appium_list_apps(device_id: str = Query(min_length=1, max_length=255)) -> dict[str, object]:
    try:
        manager = AppiumManager(runtime().get_system_settings().appium)
        return {"device_id": device_id, "apps": manager.list_ios_apps(device_id)}
    except AppiumManagerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/appium/launch")
def appium_launch_app(request: AppiumLaunchRequest) -> dict[str, object]:
    try:
        manager = AppiumManager(runtime().get_system_settings().appium)
        return manager.launch_ios_app(request.device_id, request.bundle_id)
    except AppiumManagerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/appium/end-session")
def appium_end_session() -> dict[str, object]:
    return AppiumManager(runtime().get_system_settings().appium).close_device_session()


@app.get("/api/appium/screenshot")
def appium_screenshot() -> Response:
    try:
        image = AppiumManager(runtime().get_system_settings().appium).get_device_screenshot()
        return Response(image, media_type="image/png", headers={"Cache-Control": "no-store"})
    except AppiumManagerError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.put("/api/system-settings", response_model=SystemSettings)
async def update_system_settings(settings: SystemSettings) -> SystemSettings:
    updated = await runtime().update_system_settings(settings)
    await reload_discord_gateway()
    return updated


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


@app.put("/api/secrets/discord-bot")
async def set_discord_bot_secret(value: SecretValue) -> dict[str, object]:
    try:
        secrets().set_discord_bot_token(value.api_key)
        await reload_discord_gateway()
        LOGGER.info("secret_updated scope=discord-bot")
        return secrets().status()
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/secrets/discord-bot")
async def delete_discord_bot_secret() -> dict[str, object]:
    secrets().delete_discord_bot_token()
    await reload_discord_gateway()
    LOGGER.info("secret_deleted scope=discord-bot")
    return secrets().status()


@app.put("/api/secrets/accordi-admin")
async def set_accordi_admin_secret(value: SecretValue) -> dict[str, object]:
    try:
        secrets().set_accordi_admin_token(value.api_key)
        LOGGER.info("secret_updated scope=accordi-admin")
        return secrets().status()
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/secrets/accordi-admin")
async def delete_accordi_admin_secret() -> dict[str, object]:
    secrets().delete_accordi_admin_token()
    LOGGER.info("secret_deleted scope=accordi-admin")
    return secrets().status()


@app.put("/api/secrets/runpod")
async def set_runpod_secret(value: SecretValue) -> dict[str, object]:
    try:
        secrets().set_runpod_api_key(value.api_key)
        LOGGER.info("secret_updated scope=runpod")
        return secrets().status()
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/secrets/runpod")
async def delete_runpod_secret() -> dict[str, object]:
    secrets().delete_runpod_api_key()
    LOGGER.info("secret_deleted scope=runpod")
    return secrets().status()


@app.get("/api/runpod/status")
async def runpod_status() -> dict[str, object]:
    return RunPodManager(runtime().get_system_settings().runpod, secrets().get_runpod_api_key()).status()


def runpod_manager() -> RunPodManager:
    return RunPodManager(runtime().get_system_settings().runpod, secrets().get_runpod_api_key())


def runpod_http_error(error: RunPodManagerError) -> HTTPException:
    message = str(error)
    status_code = 502 if message.startswith(("HTTP ", "Request to ", "Non-JSON")) else 422
    return HTTPException(status_code=status_code, detail=message)


def runpod_workflow_presets() -> list[dict[str, str]]:
    try:
        raw = json.loads(RUNPOD_WORKFLOW_LIBRARY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail=f"RunPod workflow library could not be read: {error}") from error
    presets = raw.get("presets") if isinstance(raw, dict) else []
    if not isinstance(presets, list):
        raise HTTPException(status_code=500, detail="RunPod workflow library must contain a presets list.")
    result: list[dict[str, str]] = []
    for item in presets:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get("id", "")).strip()
        path = str(item.get("path", "")).strip()
        if not preset_id or not path:
            continue
        result.append({
            "id": preset_id,
            "name": str(item.get("name", preset_id)).strip() or preset_id,
            "description": str(item.get("description", "")).strip(),
            "path": path,
            "input_kind": str(item.get("input_kind", "")),
            "output_kind": str(item.get("output_kind", "")),
            "min_vram_gb": str(item.get("min_vram_gb", "")),
            "creative_presets": item.get("creative_presets", []),
        })
    return result

@app.get("/api/comfyui/prompt-presets")
async def comfyui_prompt_presets() -> dict[str, object]:
    try:
        raw = json.loads(COMFYUI_PROMPT_PRESETS_PATH.read_text(encoding="utf-8"))
        return {"presets": raw.get("presets", []) if isinstance(raw, dict) else []}
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail=f"Creative prompt presets could not be read: {error}") from error

@app.post("/api/comfyui/generate-prompt")
async def generate_comfyui_prompt(request: CreativePromptRequest) -> dict[str, object]:
    from .vinted_ai import _build_openai_client
    key = secrets().get_project()
    if not key: raise HTTPException(status_code=422, detail="Project API key is not configured.")
    model_settings = runtime().get_system_settings().model
    try:
        client = _build_openai_client(api_key=key, base_url=str(model_settings.base_url or "").strip() or None)
        content = request.image_base64 if request.image_base64.startswith("data:") else f"data:image/jpeg;base64,{request.image_base64}"
        response = client.chat.completions.create(model=str(model_settings.model or "gpt-5.4-mini"), messages=[{"role":"system","content":"Return one concise Wan image-to-video prompt only. Preserve exact product identity. Describe camera motion, lighting and a simple coherent background. No text, logos, faces or invented details."},{"role":"user","content":[{"type":"text","text":"Write a vertical product-video prompt from this image."},{"type":"image_url","image_url":{"url":content}}]}], max_tokens=220, temperature=0.45)
        prompt = str(response.choices[0].message.content or "").strip()
        if not prompt: raise RuntimeError("Provider returned an empty prompt")
        return {"prompt": prompt, "model": str(model_settings.model or "gpt-5.4-mini")}
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Creative prompt generation failed: {type(error).__name__}: {error}") from error


def runpod_workflow_preset(preset_id: str) -> dict[str, str]:
    requested = str(preset_id or "").strip()
    preset = next((item for item in runpod_workflow_presets() if item["id"] == requested), None)
    if preset is None:
        raise HTTPException(status_code=404, detail="RunPod workflow preset not found.")
    return preset


def describe_runpod_workflow_loaders(workflow: dict[str, object]) -> list[dict[str, str]]:
    loaders: list[dict[str, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        normalized = class_type.lower()
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if normalized == "loadimage":
            loaders.append({"id": str(node_id), "kind": "image", "class_type": class_type, "input": "image", "current": str(inputs.get("image", ""))})
        elif "loadvideo" in normalized:
            input_name = "video_name" if "video_name" in inputs and "video" not in inputs else "video"
            loaders.append({"id": str(node_id), "kind": "video", "class_type": class_type, "input": input_name, "current": str(inputs.get(input_name, ""))})
    return loaders


@app.get("/api/runpod/workflows")
async def list_runpod_workflows() -> dict[str, object]:
    presets = runpod_workflow_presets()
    return {
        "workflows": [
            {
                **{key: value for key, value in preset.items() if key != "path"},
                "available": (PROJECT_ROOT / str(preset["path"])).is_file() if not Path(str(preset["path"])).expanduser().is_absolute() else Path(str(preset["path"])).expanduser().is_file(),
            }
            for preset in presets
        ]
    }


@app.get("/api/runpod/workflows/{preset_id}")
async def get_runpod_workflow(preset_id: str) -> dict[str, object]:
    preset = runpod_workflow_preset(preset_id)
    path = Path(str(preset["path"])).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Workflow file is missing: {path.name}")
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=422, detail=f"Workflow JSON is invalid: {error}") from error
    if not isinstance(workflow, dict) or "nodes" in workflow or "links" in workflow:
        raise HTTPException(status_code=422, detail="Saved workflow is not ComfyUI API format.")
    loaders = describe_runpod_workflow_loaders(workflow)
    if not loaders:
        raise HTTPException(status_code=422, detail="Saved workflow has no LoadImage or LoadVideo node.")
    return {"id": preset["id"], "name": preset["name"], "description": preset["description"], "workflow": workflow, "loaders": loaders}

@app.get("/api/runpod/workflows/{preset_id}/availability")
async def get_runpod_workflow_availability(preset_id: str) -> dict[str, object]:
    preset = runpod_workflow_preset(preset_id)
    manager = runpod_manager()
    region = str(manager.settings.data_center_id or "").strip()
    if not region and manager.settings.network_volume_id:
        volume = manager.get_network_volume(manager.settings.network_volume_id)
        region = str(volume.get("dataCenter") or volume.get("dataCenterId") or "").strip()
    if not region:
        raise HTTPException(status_code=422, detail="Network Volume region is not configured.")
    try:
        minimum = int(str(preset.get("min_vram_gb") or 0))
        allowed = {str(value).strip() for value in (app.state.runpod_gpu_watch.status().get("gpu_ids") or []) if str(value).strip()}
        inventory = manager.list_gpu_types(region)
        app.state.runpod_gpu_watch.record_inventory(region, inventory, f"workflow:{preset_id}")
        candidates = [gpu for gpu in inventory if str(gpu.get("id", "")) in allowed and bool(gpu.get("available")) and int(gpu.get("memory_gb") or 0) >= minimum]
        return {"workflow_id": preset_id, "region": region, "min_vram_gb": minimum, "available": candidates, "waiting": not bool(candidates)}
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/gpus")
async def runpod_gpus(data_center_id: str = Query(default="", max_length=80)) -> dict[str, object]:
    try:
        target_data_center = data_center_id.strip()
        gpus = runpod_manager().list_gpu_types(target_data_center)
        app.state.runpod_gpu_watch.record_inventory(target_data_center, gpus, "gpu-picker")
        return {
            "gpus": gpus,
            "data_center_id": target_data_center,
            "region_filtered": bool(target_data_center),
        }
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/gpu-watch")
async def runpod_gpu_watch_status() -> dict[str, object]:
    return app.state.runpod_gpu_watch.status()


@app.get("/api/runpod/gpu-watch/history")
async def runpod_gpu_watch_history(limit: int = Query(default=500, ge=1, le=5000)) -> dict[str, object]:
    history = app.state.runpod_gpu_watch.history(limit)
    return {"checks": history, "count": len(history)}


@app.get("/api/runpod/gpu-watch/history/summary")
async def runpod_gpu_watch_history_summary() -> dict[str, object]:
    hours = app.state.runpod_gpu_watch.availability_by_hour()
    return {"hours": hours, "count": len(hours), "timezone": "local"}


@app.put("/api/runpod/gpu-watch")
async def configure_runpod_gpu_watch(request: RunPodGpuWatchRequest) -> dict[str, object]:
    try:
        return app.state.runpod_gpu_watch.configure(request.enabled, request.gpu_ids, request.interval_seconds)
    except (RunPodManagerError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/runpod/gpu-watch/check")
async def check_runpod_gpu_watch() -> dict[str, object]:
    try:
        return app.state.runpod_gpu_watch.check_now()
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/datacenters")
async def runpod_datacenters() -> dict[str, object]:
    try:
        return {"datacenters": runpod_manager().list_datacenters()}
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/network-volumes")
async def runpod_network_volumes() -> dict[str, object]:
    try:
        return {"network_volumes": runpod_manager().list_network_volumes()}
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/network-volumes/{volume_id}")
async def runpod_network_volume(volume_id: str) -> dict[str, object]:
    try:
        return runpod_manager().get_network_volume(volume_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.post("/api/runpod/pods")
async def create_runpod_pod(request: RunPodCreateRequest) -> dict[str, object]:
    try:
        return runpod_manager().create_pod(name=request.name, gpu_id=request.gpu_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.post("/api/runpod/pods/{pod_id}/start")
async def start_runpod_pod(pod_id: str) -> dict[str, object]:
    try:
        return runpod_manager().start_pod(pod_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.post("/api/runpod/pods/{pod_id}/stop")
async def stop_runpod_pod(pod_id: str) -> dict[str, object]:
    try:
        return runpod_manager().stop_pod(pod_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.delete("/api/runpod/pods/{pod_id}")
async def terminate_runpod_pod(pod_id: str) -> dict[str, object]:
    try:
        return runpod_manager().terminate_pod(pod_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/pods/{pod_id}/comfyui/health")
async def runpod_comfyui_health(pod_id: str) -> dict[str, object]:
    try:
        return runpod_manager().comfyui_health(pod_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.post("/api/runpod/pods/{pod_id}/comfyui/prompt")
async def queue_runpod_comfyui_prompt(pod_id: str, request: RunPodWorkflowRequest) -> dict[str, object]:
    try:
        workflow, injected_nodes = runpod_manager().inject_comfyui_media(
            request.workflow,
            request.media_name,
            request.media_kind,
            request.media_loader_id,
        )
        result = runpod_manager().queue_comfyui_prompt(pod_id, workflow)
        result["media_name"] = request.media_name
        result["media_kind"] = request.media_kind
        result["media_loader_id"] = request.media_loader_id
        result["media_injected_nodes"] = injected_nodes
        return result
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.post("/api/runpod/pods/{pod_id}/comfyui/upload-image")
async def upload_runpod_comfyui_image(pod_id: str, request: RunPodComfyUiUploadRequest) -> dict[str, object]:
    try:
        encoded = request.data_base64.split(",", 1)[-1]
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="Image data must be valid base64.") from error
    try:
        return runpod_manager().upload_comfyui_image(pod_id, request.filename, content, request.overwrite)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.post("/api/runpod/pods/{pod_id}/comfyui/upload-media")
async def upload_runpod_comfyui_media(pod_id: str, request: RunPodComfyUiUploadRequest) -> dict[str, object]:
    try:
        encoded = request.data_base64.split(",", 1)[-1]
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="Media data must be valid base64.") from error
    try:
        return runpod_manager().upload_comfyui_media(pod_id, request.filename, content, request.overwrite)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


@app.get("/api/runpod/pods/{pod_id}/comfyui/history/{prompt_id}")
async def runpod_comfyui_history(pod_id: str, prompt_id: str) -> dict[str, object]:
    try:
        return runpod_manager().comfyui_history(pod_id, prompt_id)
    except RunPodManagerError as error:
        raise runpod_http_error(error) from error


def runpod_batches() -> RunPodBatchService:
    return app.state.runpod_batches


def runpod_batch_http_error(error: RunPodBatchError | RunPodManagerError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@app.get("/api/runpod/batches")
async def list_runpod_batches() -> dict[str, object]:
    try:
        return {"batches": runpod_batches().list_batches()}
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.post("/api/runpod/batches")
async def create_runpod_batch(request: RunPodBatchCreateRequest) -> dict[str, object]:
    try:
        return runpod_batches().create_batch(
            request.workflow,
            media_loader_id=request.media_loader_id,
            auto_deploy=request.auto_deploy,
            auto_shutdown=request.auto_shutdown,
            min_vram_gb=request.min_vram_gb,
            workflow_id=request.workflow_id,
            creative_prompt=request.creative_prompt,
        )
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.get("/api/runpod/batches/{batch_id}")
async def get_runpod_batch(batch_id: str) -> dict[str, object]:
    try:
        return runpod_batches().get_batch(batch_id)
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.get("/api/runpod/batches/{batch_id}/items/{item_id}/outputs/{output_index}", response_class=FileResponse)
async def get_runpod_batch_output(batch_id: str, item_id: str, output_index: int) -> FileResponse:
    try:
        output = runpod_batches().output_file(batch_id, item_id, output_index)
        return FileResponse(output, filename=output.name)
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.post("/api/runpod/batches/{batch_id}/items")
async def add_runpod_batch_item(batch_id: str, request: RunPodBatchMediaRequest) -> dict[str, object]:
    try:
        content = base64.b64decode(request.data_base64.split(",", 1)[-1], validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="Batch media data must be valid base64.") from error
    try:
        return runpod_batches().add_item(batch_id, request.filename, content)
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.post("/api/runpod/batches/{batch_id}/start")
async def start_runpod_batch(batch_id: str) -> dict[str, object]:
    try:
        # A creative queue must not rely on a separately configured watcher:
        # enable it with its persisted tracked-GPU list before queueing work.
        watch = app.state.runpod_gpu_watch.status()
        if not bool(watch.get("enabled")):
            app.state.runpod_gpu_watch.configure(True, list(watch.get("gpu_ids") or []), int(watch.get("interval_seconds") or 60))
        return runpod_batches().start_batch(batch_id)
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.post("/api/runpod/batches/{batch_id}/cancel")
async def cancel_runpod_batch(batch_id: str) -> dict[str, object]:
    try:
        return runpod_batches().cancel_batch(batch_id)
    except RunPodBatchError as error:
        raise runpod_batch_http_error(error) from error


@app.post("/api/vinted-ai/generate", response_model=VintedAIGenerationResponse)
async def generate_vinted_ai_image_variants(request: VintedAIGenerationRequest) -> VintedAIGenerationResponse:
    project_key = secrets().get_project()
    if not project_key:
        raise HTTPException(status_code=422, detail="Project API key not configured in the game runtime.")
    system_settings = runtime().get_system_settings()
    base_url = str(system_settings.model.base_url or "").strip() or None
    try:
        result = generate_vinted_ai_variants(
            api_key=project_key,
            photo_paths=list(request.photo_paths),
            prompt=request.prompt,
            output_dir=request.output_dir,
            model=request.model,
            size=request.size,
            quality=request.quality,
            variants=request.variants,
            base_url=base_url,
        )
        LOGGER.info(
            "vinted_ai_generated output_dir=%s variants=%s model=%s size=%s",
            result.get("output_dir", ""),
            result.get("variants", 0),
            result.get("model", ""),
            result.get("size", ""),
        )
        runtime_url = f"http://{os.environ.get('AGENT_LAB_HOST', '127.0.0.1')}:{int(os.environ.get('AGENT_LAB_PORT', '8000'))}"
        result["runtime_url"] = runtime_url
        result["request_url"] = f"{runtime_url}/api/vinted-ai/generate"
        return VintedAIGenerationResponse.model_validate(result)
    except Exception as error:
        LOGGER.exception("vinted_ai_generation_failed")
        raise HTTPException(status_code=422, detail=str(error)) from error


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


@app.get("/api/wiki/proposals", response_model=list[WikiProposalRecord])
async def list_wiki_proposals(
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[WikiProposalRecord]:
    return runtime().list_wiki_proposals(limit=limit)


@app.get("/api/wiki/pages", response_model=list[WikiPageRecord])
async def list_wiki_pages() -> list[WikiPageRecord]:
    return runtime().list_wiki_pages()


@app.get("/api/wiki/search", response_model=WikiSearchResult)
async def search_wiki(
    query: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> WikiSearchResult:
    return runtime().search_wiki(query=query, limit=limit)


@app.get("/api/wiki/pages/{name:path}", response_model=WikiPageContent)
async def get_wiki_page(name: str) -> WikiPageContent:
    try:
        return runtime().get_wiki_page(name)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/wiki/maintenance/run", response_model=WikiMaintenanceResult)
async def run_wiki_maintenance() -> WikiMaintenanceResult:
    return await runtime().run_wiki_maintenance()


@app.post("/api/wiki/proposals/{name}/resolve", response_model=WikiProposalRecord)
async def resolve_wiki_proposal(name: str, request: WikiProposalResolveRequest) -> WikiProposalRecord:
    try:
        return await runtime().resolve_wiki_proposal(
            name=name,
            status=request.status,
            reviewer=request.reviewer,
            reason=request.reason,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


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


@app.get("/api/vinted/reports")
async def vinted_reports(
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=200, ge=1, le=5000),
) -> dict[str, object]:
    try:
        return build_vinted_report(PROJECT_ROOT, days=days, limit=limit)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/linkedin/posts")
async def linkedin_posts(limit: int = Query(default=500, ge=1, le=2000),
                         search: str = Query(default="", max_length=100)) -> dict:
    return await asyncio.to_thread(list_linkedin_posts, PROJECT_ROOT, limit=limit, search=search)


@app.get("/api/linkedin/posts/{post_id}")
async def linkedin_post_detail(post_id: str) -> dict:
    try:
        return await asyncio.to_thread(get_linkedin_post, PROJECT_ROOT, post_id)
    except LinkedInReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/linkedin/posts/{post_id}/media/{media_index}/archive")
async def archive_linkedin_post_media(post_id: str, media_index: int,
                                      poster: bool = Query(default=False)) -> dict:
    try:
        return await asyncio.to_thread(archive_linkedin_media, PROJECT_ROOT, post_id, media_index, poster=poster)
    except LinkedInReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/linkedin/posts/{post_id}/media/{media_index}/file")
async def download_linkedin_post_media(post_id: str, media_index: int,
                                       variant: str = Query(default="original")) -> FileResponse:
    try:
        path = await asyncio.to_thread(archived_media_path, PROJECT_ROOT, post_id, media_index, variant)
    except LinkedInReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@app.post("/api/linkedin/posts/{post_id}/rewrite")
async def rewrite_linkedin_post(post_id: str, request: LinkedInRewriteRequest) -> dict:
    try:
        post = await asyncio.to_thread(get_linkedin_post, PROJECT_ROOT, post_id)
    except LinkedInReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not str(post.get("text") or "").strip():
        raise HTTPException(status_code=422, detail="This post has no text to rewrite")
    key = secrets().get_project()
    if not key:
        raise HTTPException(status_code=422, detail="Set the project OpenAI API key in Settings first")
    from .vinted_ai import _build_openai_client
    model_settings = runtime().get_system_settings().model
    # Keep LinkedIn rewriting independent from a stale global model override.
    # GPT-5.4 Mini is a current text-capable API model suited to short rewrites.
    model_name = "gpt-5.4-mini"
    instruction = request.instruction.strip()
    prompt = request.prompt
    if prompt is None:
        prompt = (f"Post di partenza:\n{str(post['text'])[:10000]}\n\n"
                  f"Indicazioni aggiuntive: {instruction or 'tono tranquillo, come se spiegassi a un amico'}")
    if not prompt.strip():
        raise HTTPException(status_code=422, detail="The prompt cannot be empty")

    def generate() -> str:
        client = _build_openai_client(api_key=key, base_url=str(model_settings.base_url or "").strip() or None)
        response = client.responses.create(
            model=model_name,
            input=prompt,
            store=False,
        )
        return str(response.output_text or "").strip()

    try:
        draft = await asyncio.to_thread(generate)
        return await asyncio.to_thread(save_linkedin_rewrite, PROJECT_ROOT, post_id, draft, instruction, model_name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Rewrite failed: {type(exc).__name__}: {exc}") from exc


@app.get("/api/linkedin/publisher/status")
async def linkedin_publisher_status() -> dict:
    return await asyncio.to_thread(publisher_status, PROJECT_ROOT)


@app.get("/api/linkedin/publisher/drafts")
async def linkedin_publisher_drafts() -> dict:
    return {"drafts": await asyncio.to_thread(list_drafts, PROJECT_ROOT)}


@app.post("/api/linkedin/publisher/drafts/{draft_id}/source-image")
async def linkedin_publisher_attach_source_image(draft_id: int) -> dict:
    try:
        return await asyncio.to_thread(attach_source_image_to_draft, PROJECT_ROOT, draft_id)
    except LinkedInPublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LinkedInReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/linkedin/publisher/drafts/{draft_id}/attachment")
async def linkedin_publisher_draft_attachment(draft_id: int) -> FileResponse:
    try:
        path = await asyncio.to_thread(draft_attachment_path, PROJECT_ROOT, draft_id)
    except LinkedInPublishError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)


@app.post("/api/linkedin/publisher/drafts")
async def linkedin_publisher_create_draft(request: LinkedInDraftRequest) -> dict:
    try:
        attachment_path = ""
        if request.source_post_id:
            post = await asyncio.to_thread(get_linkedin_post, PROJECT_ROOT, request.source_post_id)
            media = next((item for item in post.get("media", []) if item.get("kind") == "image"), None)
            if media is not None:
                try:
                    attachment_path = str(await asyncio.to_thread(
                        archived_media_path, PROJECT_ROOT, request.source_post_id, media["index"], "original"))
                except LinkedInReportError:
                    await asyncio.to_thread(archive_linkedin_media, PROJECT_ROOT, request.source_post_id, media["index"])
                    attachment_path = str(await asyncio.to_thread(
                        archived_media_path, PROJECT_ROOT, request.source_post_id, media["index"], "original"))
        return await asyncio.to_thread(create_draft, PROJECT_ROOT, request.body, request.source_post_id, attachment_path)
    except LinkedInPublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LinkedInReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/linkedin/publisher/drafts/{draft_id}")
async def linkedin_publisher_update_draft(draft_id: int, request: LinkedInDraftRequest) -> dict:
    try:
        return await asyncio.to_thread(update_draft, PROJECT_ROOT, draft_id, request.body)
    except LinkedInPublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/linkedin/publisher/drafts/{draft_id}/publish")
async def linkedin_publisher_publish(draft_id: int, request: LinkedInPublishRequest,
                                     http_request: Request) -> dict:
    if http_request.headers.get("x-agent-lab-confirm") != "publish":
        raise HTTPException(status_code=403, detail="Explicit publish confirmation is required")
    try:
        return await asyncio.to_thread(publish_draft, PROJECT_ROOT, draft_id, request.expected_body)
    except LinkedInPublishError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/vinted/reports/competitors/{member_id}")
async def vinted_competitor_report(member_id: str, limit: int = Query(default=5000, ge=1, le=5000)) -> dict[str, object]:
    report = build_vinted_competitor_report(PROJECT_ROOT, member_id, limit=limit)
    if not report.get("available"):
        raise HTTPException(status_code=404, detail="Competitor profile not found")
    return report


@app.post("/api/vinted/reports/competitors/{member_id}/check-sales", response_model=ProjectJob, status_code=202)
async def check_vinted_competitor_sales(member_id: str, category: str = Query(default="", max_length=160)) -> ProjectJob:
    """Queue an explicit listing-page sold-state verification for one competitor."""
    report = build_vinted_competitor_report(PROJECT_ROOT, member_id, limit=1)
    if not report.get("available"):
        raise HTTPException(status_code=404, detail="Competitor profile not found")
    profile_url = str(report.get("seller_profile_url", "") or "").strip()
    if not profile_url:
        raise HTTPException(status_code=422, detail="The competitor has no saved profile URL")
    try:
        return await project_gateway().create_job(
            ProjectJobCreate(
                project_id="main-scraper",
                action="vinted.profile_sale_check",
                parameters={"profile-urls": profile_url, "profile-categories": category.strip(), "max-items": 0, "db-path": "data/scraper.db"},
                agent_id="vinted-analyst",
            )
        )
    except (KeyError, PermissionError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/vinted/reports/sourcing-batch", response_model=ProjectJob, status_code=202)
async def create_vinted_report_sourcing_batch(request: MarketplaceSourcingBatchRequest) -> ProjectJob:
    """Queue an isolated AliExpress visual-search job from report card selections."""
    archive_root = (PROJECT_ROOT / "projects" / "main-scraper" / "data" / "deal_archive").resolve()
    selected: list[dict[str, str]] = []
    for item in request.items:
        archive_path = ""
        if item.archive_image_path.strip():
            candidate = Path(item.archive_image_path).expanduser().resolve()
            if candidate.is_relative_to(archive_root) and candidate.is_file():
                archive_path = str(candidate)
        image_url = item.image_url.strip()
        if not archive_path and not image_url:
            continue
        selected.append(
            {
                "item_id": item.item_id.strip(),
                "name": item.name.strip(),
                "link": item.link.strip(),
                "image_url": image_url,
                "archive_image_path": archive_path,
            }
        )
    if not selected:
        raise HTTPException(status_code=422, detail="Selected articles need an archived image or an image URL.")

    batch_dir = PROJECT_ROOT / "projects" / "main-scraper" / "output" / "aliexpress_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_dir / f"report_selection_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000:06d}.json"
    manifest_path.write_text(
        json.dumps({"source": "vinted-reports", "items": selected}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        return await project_gateway().create_job(
            ProjectJobCreate(
                project_id="main-scraper",
                action="aliexpress.image_search",
                parameters={
                    "items-file": str(manifest_path),
                    "max-results": request.max_results,
                    "reuse-cache-hours": 24,
                    "db-path": "data/aliexpress_sourcing.db",
                },
                agent_id="sourcing-agent",
            )
        )
    except (KeyError, PermissionError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/vinted/owned-profiles")
async def add_vinted_owned_profile(request: OwnedMarketplaceProfileRequest) -> dict[str, object]:
    try:
        return save_owned_profile(
            PROJECT_ROOT,
            profile_url=request.profile_url,
            display_name=request.display_name,
        )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/vinted/owned-profiles/{member_id}")
async def remove_vinted_owned_profile(member_id: str) -> dict[str, object]:
    try:
        return deactivate_owned_profile(PROJECT_ROOT, member_id)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.delete("/api/vinted/owned-profiles/{member_id}/items/{item_id}")
async def ignore_vinted_owned_profile_item(member_id: str, item_id: str) -> dict[str, object]:
    try:
        return ignore_owned_profile_item(PROJECT_ROOT, member_id, item_id)
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/vinted/reports/export", response_class=FileResponse)
async def export_vinted_report(
    days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=5000, ge=1, le=5000),
) -> FileResponse:
    try:
        report_path = write_vinted_report_html(PROJECT_ROOT, days=days, limit=limit)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FileResponse(
        report_path,
        media_type="text/html; charset=utf-8",
        filename=report_path.name,
    )


@app.get("/api/vinted/archive", response_class=FileResponse)
async def vinted_archive(path: str = Query(min_length=1, max_length=2048)) -> FileResponse:
    archive_root = (PROJECT_ROOT / "projects" / "main-scraper" / "data" / "deal_archive").resolve()
    requested = Path(path).expanduser()
    requested = requested.resolve() if requested.is_absolute() else (PROJECT_ROOT / requested).resolve()
    if not requested.is_relative_to(archive_root) or not requested.is_file():
        raise HTTPException(status_code=404, detail="Archived marketplace artifact not found")
    return FileResponse(requested)


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


@app.delete("/api/project-jobs/{job_id}", response_model=ProjectJob)
async def cancel_project_job(job_id: str) -> ProjectJob:
    try:
        return await project_gateway().cancel_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Job not found") from error


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
