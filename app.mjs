import * as THREE from "three";
import { AgentNetwork } from "./src/agentProtocol.mjs";
import {
  AgentWorld,
  addRoomToLayout,
  doorLayout,
  findAvailableRoomRect,
  isDoorTile,
  isInsideTile,
  removeRoomFromLayout,
  roomConfig,
  roomCells,
  roomLayout,
  resetRoomLayout,
  setDoorLayout,
  setRoomLayout,
  tileEquals,
  tileKey,
  tileToWorld,
  toggleDoorAt,
  toggleRoomCell,
  workstations,
  worldToTile,
} from "./src/agentWorld.mjs";
import { defaultScenario } from "./src/scenarios.mjs";
import { RuntimeClient } from "./src/runtimeClient.mjs";

const canvas = document.querySelector("#game");
const bootMessage = document.querySelector("#boot-message");
const runToggle = document.querySelector("#run-toggle");
const speedControl = document.querySelector("#speed-control");
const autoToggle = document.querySelector("#auto-toggle");
const cameraLeft = document.querySelector("#camera-left");
const cameraRight = document.querySelector("#camera-right");
const selectedName = document.querySelector("#selected-name");
const selectedRole = document.querySelector("#selected-role");
const selectedJob = document.querySelector("#selected-job");
const selectedStatus = document.querySelector("#selected-status");
const selectedLoad = document.querySelector("#selected-load");
const selectedTile = document.querySelector("#selected-tile");
const eventLog = document.querySelector("#event-log");
const metrics = document.querySelector("#metrics");
const stationList = document.querySelector("#station-list");
const roomList = document.querySelector("#room-list");
const runtimeStatus = document.querySelector("#runtime-status");
const addAgentButton = document.querySelector("#add-agent");
const layoutToggle = document.querySelector("#layout-toggle");
const layoutEditor = document.querySelector("#layout-editor");
const layoutEditorStatus = document.querySelector("#layout-editor-status");
const layoutEditorHint = document.querySelector("#layout-editor-hint");
const editorCloseButton = document.querySelector("#editor-close");
const roomDrawToggle = document.querySelector("#room-draw-toggle");
const doorToggle = document.querySelector("#door-toggle");
const addRoomButton = document.querySelector("#add-room");
const deleteRoomButton = document.querySelector("#delete-room");
const resetLayoutButton = document.querySelector("#reset-layout");
const themeToggle = document.querySelector("#theme-toggle");
const agentDialog = document.querySelector("#agent-dialog");
const agentForm = document.querySelector("#agent-form");
const agentFormError = document.querySelector("#agent-form-error");
const configureAgentButton = document.querySelector("#configure-agent");
const agentSettingsDialog = document.querySelector("#agent-settings-dialog");
const agentSettingsForm = document.querySelector("#agent-settings-form");
const agentSettingsError = document.querySelector("#agent-settings-error");
const quickChat = document.querySelector("#agent-quick-chat");
const quickChatAgent = document.querySelector("#quick-chat-agent");
const quickChatInput = document.querySelector("#quick-chat-input");
const quickChatStatus = document.querySelector("#quick-chat-status");
const quickChatHistory = document.querySelector("#quick-chat-history");
const projectKeyStatus = document.querySelector("#project-key-status");
const agentKeyStatus = document.querySelector("#agent-key-status");
const agentActionDialog = document.querySelector("#agent-action-dialog");
const agentActionTitle = document.querySelector("#agent-action-title");
const agentActionRole = document.querySelector("#agent-action-role");
const agentActionStatus = document.querySelector("#agent-action-status");
const workOptions = document.querySelector("#work-options");
const projectDialog = document.querySelector("#project-dialog");
const projectForm = document.querySelector("#project-form");
const projectSelect = document.querySelector("#project-select");
const projectAction = document.querySelector("#project-action");
const projectParameters = document.querySelector("#project-parameters");
const projectApprovalRow = document.querySelector("#project-approval-row");
const projectScheduleSection = document.querySelector("#project-schedule-section");
const projectScheduleMode = document.querySelector("#project-schedule-mode");
const projectScheduleDate = document.querySelector("#project-schedule-date");
const projectScheduleTime = document.querySelector("#project-schedule-time");
const projectScheduleRepeat = document.querySelector("#project-schedule-repeat");
const projectScheduleCron = document.querySelector("#project-schedule-cron");
const projectScheduleNow = document.querySelector("#project-schedule-now");
const projectScheduleHint = document.querySelector("#project-schedule-hint");
const projectWeekdayPicker = document.querySelector("#project-weekday-picker");
const projectRisk = document.querySelector("#project-risk");
const projectResult = document.querySelector("#project-result");
const projectError = document.querySelector("#project-error");
const projectPresetSelect = document.querySelector("#project-preset");
const projectPresetName = document.querySelector("#project-preset-name");
const jobToastStack = document.querySelector("#job-toast-stack");
const jobNotificationsButton = document.querySelector("#job-notifications");
const jobNotificationCount = document.querySelector("#job-notification-count");
const projectJobList = document.querySelector("#project-job-list");
const projectPanelTabs = Array.from(document.querySelectorAll("[data-panel-tab]"));
const projectPanels = Array.from(document.querySelectorAll("[data-project-panel]"));
const projectOutputSummary = document.querySelector("#project-output-summary");
const projectOutputView = document.querySelector("#project-output-view");
const projectOutputMeta = document.querySelector("#project-output-meta");
const projectOutputHead = document.querySelector("#project-output-head");
const projectOutputRows = document.querySelector("#project-output-rows");

const LAYOUT_STORAGE_KEY = "agent-protocol-lab-layout-v1";

function loadStoredLayout() {
  try {
    const raw = window.localStorage?.getItem(LAYOUT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_error) {
    return {};
  }
}

function tileFromStored(value) {
  if (!value || !Number.isFinite(Number(value.col)) || !Number.isFinite(Number(value.row))) {
    return null;
  }
  return { col: Number(value.col), row: Number(value.row) };
}

function applyStoredLayoutBeforeWorld(layout) {
  if (Array.isArray(layout.rooms) && layout.rooms.length) {
    setRoomLayout(layout.rooms);
  }
  if (Array.isArray(layout.doors)) {
    setDoorLayout(layout.doors);
  }
  for (const [stationId, storedTile] of Object.entries(layout.stations ?? {})) {
    const tile = tileFromStored(storedTile);
    const station = workstations.find((item) => item.id === stationId);
    if (station && tile && isInsideTile(tile)) {
      station.position = tileToWorld(tile);
    }
  }
}

const storedLayout = loadStoredLayout();
applyStoredLayoutBeforeWorld(storedLayout);

const network = new AgentNetwork(defaultScenario);
const agentWorld = new AgentWorld(network);
agentWorld.restoreAgentTiles(storedLayout.agents ?? {});
const runtimeClient = new RuntimeClient();
const runtimeSnapshots = new Map();
const agentReplies = new Map();
const chatMessageIds = new Set();
const projectJobToasts = new Map();
const projectJobsCache = new Map();
const seenCompletedProjectJobs = new Set();
let availableProjects = [];
let availableProjectPresets = [];
let projectPanel = "output";
let unreadCompletedProjectJobs = 0;

const providerDefaults = {
  simulated: { model: "native-simulator", baseUrl: "" },
  openai: { model: "gpt-5.5", baseUrl: "https://api.openai.com/v1" },
  "openai-compatible": { model: "", baseUrl: "" },
  anthropic: { model: "", baseUrl: "https://api.anthropic.com" },
  gemini: { model: "", baseUrl: "https://generativelanguage.googleapis.com/v1beta" },
  ollama: { model: "llama3.2", baseUrl: "http://127.0.0.1:11434" },
};

const MODEL_CATALOGS = {
  simulated: [
    { label: "Native simulator", value: "native-simulator" },
  ],
  openai: [
    { group: "Recommended", options: [
      { label: "GPT-5.5", value: "gpt-5.5" },
      { label: "GPT-5.5 Pro", value: "gpt-5.5-pro" },
      { label: "GPT-5.4", value: "gpt-5.4" },
      { label: "GPT-5.4 Mini", value: "gpt-5.4-mini" },
      { label: "GPT-5.4 Nano", value: "gpt-5.4-nano" },
    ] },
    { group: "Reasoning", options: [
      { label: "o3", value: "o3" },
      { label: "o4 Mini", value: "o4-mini" },
    ] },
    { group: "Compatibility", options: [
      { label: "GPT-4.1", value: "gpt-4.1" },
      { label: "GPT-4.1 Mini", value: "gpt-4.1-mini" },
      { label: "GPT-4.1 Nano", value: "gpt-4.1-nano" },
      { label: "GPT-4o", value: "gpt-4o" },
      { label: "GPT-4o Mini", value: "gpt-4o-mini" },
    ] },
  ],
  "openai-compatible": [],
  anthropic: [],
  gemini: [],
  ollama: [],
};

const MODEL_PICKER_CUSTOM = "__custom__";

const PERFORMANCE = {
  maxFps: 45,
  maxPixelRatio: 1.5,
  shadows: true,
  hudRefreshMs: 500,
  relationRefreshMs: 120,
  messageLineSegments: 12,
  fog: true,
};

const THEME_STORAGE_KEY = "agent-protocol-lab-theme-v1";
const WORLD_THEMES = {
  dark: {
    label: "Dark",
    sceneBg: 0x070c16,
    fog: 0x070c16,
    fogNear: 17,
    fogFar: 31,
    exposure: 1.15,
    floor: 0x151f31,
    wall: 0x111a2a,
    trim: 0x050912,
    glass: 0x67e8f9,
    glassEmissive: 0x123c48,
    glassOpacity: 0.38,
    shadow: 0x000000,
    shadowOpacity: 0.3,
    stationSurface: 0x111a2a,
    stationSurfaceEmissive: 0x000000,
    tileEven: 0x172238,
    tileOdd: 0x131d30,
    tileBlocked: 0x0b1120,
    tileCurrent: 0x1d7180,
    tileDestination: 0x725b2b,
    tileOccupied: 0x273650,
    tileStation: 0x7c5b18,
    tileRoom: 0x20304e,
    tileDoor: 0xb8892f,
  },
  light: {
    label: "White",
    sceneBg: 0xdbeafe,
    fog: 0xdbeafe,
    fogNear: 20,
    fogFar: 40,
    exposure: 1.05,
    floor: 0xe8f4ff,
    wall: 0xf8fafc,
    trim: 0xb7c9e8,
    glass: 0x38bdf8,
    glassEmissive: 0xbae6fd,
    glassOpacity: 0.5,
    shadow: 0x2b4a6f,
    shadowOpacity: 0.16,
    stationSurface: 0xffffff,
    stationSurfaceEmissive: 0xe0f2fe,
    tileEven: 0xf8fbff,
    tileOdd: 0xe7f2ff,
    tileBlocked: 0xcbd5e1,
    tileCurrent: 0x6ee7f9,
    tileDestination: 0xfde68a,
    tileOccupied: 0xc7d2fe,
    tileStation: 0xfbbf24,
    tileRoom: 0xdbeafe,
    tileDoor: 0xf59e0b,
  },
};

function loadStoredTheme() {
  try {
    const stored = window.localStorage?.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "dark";
  } catch (_error) {
    return "dark";
  }
}

let currentTheme = loadStoredTheme();

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, PERFORMANCE.maxPixelRatio));
renderer.shadowMap.enabled = PERFORMANCE.shadows;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = WORLD_THEMES[currentTheme].exposure;

const scene = new THREE.Scene();
scene.background = new THREE.Color(WORLD_THEMES[currentTheme].sceneBg);
scene.fog = PERFORMANCE.fog
  ? new THREE.Fog(WORLD_THEMES[currentTheme].fog, WORLD_THEMES[currentTheme].fogNear, WORLD_THEMES[currentTheme].fogFar)
  : null;

const camera = new THREE.OrthographicCamera(-8, 8, 5, -5, 0.1, 100);
let cameraYaw = Math.PI * 0.25;
let cameraZoom = 8.4;
const cameraTarget = new THREE.Vector3(0, 0, 0);

const raycaster = new THREE.Raycaster();
const pointerNdc = new THREE.Vector2();
const pointerState = {
  x: 0,
  y: 0,
  startX: 0,
  startY: 0,
  dragging: false,
  panning: false,
};

const clock = new THREE.Clock();
let running = true;
let speed = 1;
let autoAgents = true;
let selectedAgentId = "orchestrator";
let selectedStationId = null;
let selectedRoomId = roomLayout[0]?.id ?? null;
let roomDrawMode = false;
let doorMode = false;
let nextUiRefresh = 0;
let nextRelationRefresh = 0;
let lastFrameAt = 0;
let quickChatAgentId = null;
let quickChatFocusTimer = null;
let layoutMode = false;

const selectableObjects = [];
const agentVisuals = new Map();
const stationVisuals = new Map();
const relationVisuals = new Map();
const messageVisuals = new Map();
const roomVisuals = new Map();
const tileVisuals = new Map();
const editorTileVisuals = new Map();
let doorVisualGroup = null;
const initialWorldTheme = WORLD_THEMES[currentTheme];

const sharedMaterials = {
  floor: new THREE.MeshStandardMaterial({ color: initialWorldTheme.floor, roughness: 0.84, metalness: 0.08 }),
  wall: new THREE.MeshStandardMaterial({ color: initialWorldTheme.wall, roughness: 0.74, metalness: 0.14 }),
  trim: new THREE.MeshStandardMaterial({ color: initialWorldTheme.trim, roughness: 0.55, metalness: 0.32 }),
  glass: new THREE.MeshStandardMaterial({
    color: initialWorldTheme.glass,
    emissive: initialWorldTheme.glassEmissive,
    transparent: true,
    opacity: initialWorldTheme.glassOpacity,
    roughness: 0.12,
    metalness: 0.26,
  }),
  shadow: new THREE.MeshBasicMaterial({
    color: initialWorldTheme.shadow,
    transparent: true,
    opacity: initialWorldTheme.shadowOpacity,
    depthWrite: false,
  }),
};

const scratchStart = new THREE.Vector3();
const scratchMid = new THREE.Vector3();
const scratchEnd = new THREE.Vector3();
const quickChatPosition = new THREE.Vector3();
const scratchCurve = new THREE.QuadraticBezierCurve3(
  new THREE.Vector3(),
  new THREE.Vector3(),
  new THREE.Vector3()
);

const tilePalette = {
  even: new THREE.Color(initialWorldTheme.tileEven),
  odd: new THREE.Color(initialWorldTheme.tileOdd),
  blocked: new THREE.Color(initialWorldTheme.tileBlocked),
  current: new THREE.Color(initialWorldTheme.tileCurrent),
  destination: new THREE.Color(initialWorldTheme.tileDestination),
  occupied: new THREE.Color(initialWorldTheme.tileOccupied),
  station: new THREE.Color(initialWorldTheme.tileStation),
  room: new THREE.Color(initialWorldTheme.tileRoom),
  door: new THREE.Color(initialWorldTheme.tileDoor),
};

const editorGridMaterial = new THREE.MeshBasicMaterial({
  color: initialWorldTheme.tileRoom,
  transparent: true,
  opacity: 0,
  depthWrite: false,
});

function setBootMessage(message) {
  if (bootMessage) {
    bootMessage.textContent = message;
  }
}

function tileBaseColorFor(tile) {
  if (isDoorTile(tile)) {
    return tilePalette.door;
  }
  if (agentWorld.isBlockedTile(tile)) {
    return tilePalette.blocked;
  }
  return (tile.row + tile.col) % 2 === 0 ? tilePalette.even : tilePalette.odd;
}

function applyTheme(theme, options = {}) {
  currentTheme = theme === "light" ? "light" : "dark";
  const colors = WORLD_THEMES[currentTheme];
  document.body.classList.toggle("theme-light", currentTheme === "light");
  if (themeToggle) {
    themeToggle.textContent = currentTheme === "light" ? "Dark" : "White";
    themeToggle.classList.toggle("button--primary", currentTheme === "light");
    themeToggle.setAttribute("aria-label", `Switch to ${currentTheme === "light" ? "dark" : "white"} mode`);
  }
  renderer.toneMappingExposure = colors.exposure;
  scene.background = new THREE.Color(colors.sceneBg);
  scene.fog = PERFORMANCE.fog ? new THREE.Fog(colors.fog, colors.fogNear, colors.fogFar) : null;

  sharedMaterials.floor.color.setHex(colors.floor);
  sharedMaterials.wall.color.setHex(colors.wall);
  sharedMaterials.trim.color.setHex(colors.trim);
  sharedMaterials.glass.color.setHex(colors.glass);
  sharedMaterials.glass.emissive.setHex(colors.glassEmissive);
  sharedMaterials.glass.opacity = colors.glassOpacity;
  sharedMaterials.shadow.color.setHex(colors.shadow);
  sharedMaterials.shadow.opacity = colors.shadowOpacity;

  for (const group of stationVisuals.values()) {
    group.traverse((child) => {
      const material = child.material;
      if (material?.userData?.themeRole === "station-surface") {
        material.color.setHex(colors.stationSurface);
        material.emissive?.setHex(colors.stationSurfaceEmissive);
      }
    });
  }
  doorVisualGroup?.traverse((child) => {
    const material = child.material;
    if (material?.userData?.themeRole === "door-marker") {
      material.color.setHex(colors.tileDoor);
      material.emissive?.setHex(colors.tileDoor);
      material.emissive?.multiplyScalar(0.18);
    }
  });

  tilePalette.even.setHex(colors.tileEven);
  tilePalette.odd.setHex(colors.tileOdd);
  tilePalette.blocked.setHex(colors.tileBlocked);
  tilePalette.current.setHex(colors.tileCurrent);
  tilePalette.destination.setHex(colors.tileDestination);
  tilePalette.occupied.setHex(colors.tileOccupied);
  tilePalette.station.setHex(colors.tileStation);
  tilePalette.room.setHex(colors.tileRoom);
  tilePalette.door.setHex(colors.tileDoor);
  editorGridMaterial.color.setHex(colors.tileRoom);

  for (const mesh of tileVisuals.values()) {
    mesh.userData.baseColor = tileBaseColorFor(mesh.userData.tile).clone();
    mesh.userData.renderState = "";
  }
  updateTiles();

  if (options.persist !== false) {
    try {
      window.localStorage?.setItem(THEME_STORAGE_KEY, currentTheme);
    } catch (_error) {
      // Ignore storage failures; the theme still changes for the current session.
    }
  }
}

function currentLayoutState() {
  const agents = {};
  for (const agent of network.agents) {
    const state = agentWorld.getAgentState(agent.id);
    if (state) {
      agents[agent.id] = { ...state.tile };
    }
  }
  return {
    version: 1,
    rooms: roomLayout.map((room) => ({ ...room })),
    doors: doorLayout.map((door) => ({ ...door })),
    stations: Object.fromEntries(workstations.map((station) => [station.id, worldToTile(station.position)])),
    agents,
  };
}

function saveLayoutState() {
  try {
    window.localStorage?.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(currentLayoutState()));
  } catch (error) {
    runtimeClient.logClient?.("warning", error.message, { operation: "saveLayoutState" });
  }
}

function stationsInRoom(room) {
  return workstations.filter((station) => roomContainsTile(room, worldToTile(station.position)));
}

function updateLayoutEditor() {
  const room = selectedRoomId ? roomLayout.find((item) => item.id === selectedRoomId) : null;
  layoutEditor?.toggleAttribute("hidden", !layoutMode);
  if (layoutToggle) {
    layoutToggle.textContent = layoutMode ? "Close editor" : "Editor";
    layoutToggle.classList.toggle("button--primary", layoutMode);
  }
  roomDrawToggle?.classList.toggle("button--primary", layoutMode && roomDrawMode);
  doorToggle?.classList.toggle("button--primary", layoutMode && doorMode);

  const hasAgents = room ? agentsInRoom(room).length > 0 : false;
  const hasStations = room ? stationsInRoom(room).length > 0 : false;
  if (deleteRoomButton) {
    deleteRoomButton.disabled = !room || roomLayout.length <= 1 || hasAgents || hasStations;
  }
  if (layoutEditorStatus) {
    const mode = roomDrawMode ? "modella stanza" : doorMode ? "porte/corridoi" : "sposta oggetti";
    const roomText = room ? `${room.label} · ${roomCells(room).length} celle` : "nessuna stanza selezionata";
    layoutEditorStatus.textContent = `${roomText} · ${mode}`;
  }
  if (layoutEditorHint) {
    if (!room) {
      layoutEditorHint.textContent = "Seleziona una stanza dal pannello Stanze, poi scegli cosa modificare.";
    } else if (roomDrawMode) {
      layoutEditorHint.textContent = "Clicca celle adiacenti per aggiungerle alla stanza; clicca celle della stanza per rimuoverle.";
    } else if (doorMode) {
      layoutEditorHint.textContent = "Clicca celle sulla griglia per aggiungere o rimuovere porte/corridoi camminabili.";
    } else {
      layoutEditorHint.textContent = "Clicca un agente o tavolo, poi clicca un tile per spostarlo. Usa i pulsanti per stanze e porte.";
    }
  }
}

function setLayoutMode(enabled) {
  layoutMode = enabled;
  canvas.classList.toggle("layout-mode", layoutMode);
  editorGridMaterial.opacity = layoutMode ? 0.07 : 0;
  setBootMessage(
    layoutMode
      ? "Editor: seleziona agente/tavolo e clicca un tile. Usa Modella stanza o Porte per modificare la griglia."
      : ""
  );
  if (layoutMode) {
    closeQuickChat();
    setAutoAgents(false);
  } else {
    roomDrawMode = false;
    doorMode = false;
  }
  updateLayoutEditor();
  updateHud();
}

function setRoomDrawMode(enabled) {
  roomDrawMode = Boolean(enabled);
  if (roomDrawMode) {
    doorMode = false;
    setLayoutMode(true);
  }
  updateLayoutEditor();
  setBootMessage(
    roomDrawMode
      ? "Modella stanza: seleziona una stanza, poi clicca celle della griglia per aggiungerle/toglierle."
      : "Editor: sposta agenti/tavoli o usa Porte per creare passaggi."
  );
}

function setDoorMode(enabled) {
  doorMode = Boolean(enabled);
  if (doorMode) {
    roomDrawMode = false;
    setLayoutMode(true);
  }
  updateLayoutEditor();
  setBootMessage(
    doorMode
      ? "Porte: clicca celle vuote o bordi stanza per creare porte/corridoi camminabili."
      : "Editor: sposta agenti/tavoli o usa Modella stanza per cambiare le stanze."
  );
}

function roomColor(index) {
  return ["#38bdf8", "#a78bfa", "#34d399", "#f97316", "#f472b6", "#eab308"][index % 6];
}

function moveStationVisual(stationId) {
  const station = agentWorld.getStation(stationId);
  const visual = stationVisuals.get(stationId);
  if (station && visual) {
    visual.position.set(station.position.x, 0, station.position.z);
  }
}

function addLayoutRoom() {
  const rect = findAvailableRoomRect(5, 4);
  if (!rect) {
    setBootMessage("Non c'e spazio libero per un'altra stanza nel layout attuale.");
    return;
  }
  const room = addRoomToLayout({
    ...rect,
    id: `room-${roomLayout.length + 1}`,
    label: `Room ${roomLayout.length + 1}`,
    color: roomColor(roomLayout.length),
  });
  createRoomVisual(room);
  agentWorld.refreshBlockedTiles();
  selectedRoomId = room.id;
  focusRoom(room);
  setLayoutMode(true);
  saveLayoutState();
  setBootMessage(`${room.label} aggiunta. Seleziona un agente/tavolo e clicca un tile nella nuova stanza.`);
  updateHud();
}

function resetSavedLayout() {
  try {
    window.localStorage?.removeItem(LAYOUT_STORAGE_KEY);
  } catch (_error) {
    // Best effort; reload still restores source defaults if storage is unavailable.
  }
  resetRoomLayout();
  window.location.reload();
}

function colorMaterial(color, options = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: options.roughness ?? 0.72,
    metalness: options.metalness ?? 0.02,
    emissive: options.emissive ?? 0x000000,
    transparent: options.transparent ?? false,
    opacity: options.opacity ?? 1,
  });
}

function makeCanvasTexture(draw, width = 512, height = 128) {
  const labelCanvas = document.createElement("canvas");
  labelCanvas.width = width;
  labelCanvas.height = height;
  const labelCtx = labelCanvas.getContext("2d");
  draw(labelCtx, width, height);
  const texture = new THREE.CanvasTexture(labelCanvas);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  return texture;
}

function drawRoundedRect(labelCtx, x, y, width, height, radius) {
  labelCtx.beginPath();
  if (typeof labelCtx.roundRect === "function") {
    labelCtx.roundRect(x, y, width, height, radius);
    return;
  }
  const r = Math.min(radius, width / 2, height / 2);
  labelCtx.moveTo(x + r, y);
  labelCtx.arcTo(x + width, y, x + width, y + height, r);
  labelCtx.arcTo(x + width, y + height, x, y + height, r);
  labelCtx.arcTo(x, y + height, x, y, r);
  labelCtx.arcTo(x, y, x + width, y, r);
  labelCtx.closePath();
}

function createTextSprite(text, options = {}) {
  const texture = makeCanvasTexture((labelCtx, width, height) => {
    labelCtx.clearRect(0, 0, width, height);
    if (options.background) {
      labelCtx.fillStyle = options.background;
      drawRoundedRect(labelCtx, 8, 8, width - 16, height - 16, options.radius ?? 26);
      labelCtx.fill();
    }
    labelCtx.font = `${options.weight ?? 800} ${options.size ?? 42}px Inter, Arial, sans-serif`;
    labelCtx.textAlign = "center";
    labelCtx.textBaseline = "middle";
    labelCtx.fillStyle = options.color ?? "#eef6ff";
    labelCtx.fillText(text, width / 2, height / 2 + (options.offsetY ?? 0));
  }, options.width ?? 512, options.height ?? 128);

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(options.scaleX ?? 2.5, options.scaleY ?? 0.62, 1);
  sprite.userData.texture = texture;
  return sprite;
}

function replaceSpriteText(sprite, text, options = {}) {
  if (sprite.userData.text === text) {
    return;
  }
  sprite.userData.text = text;
  const oldTexture = sprite.material.map;
  const texture = makeCanvasTexture((labelCtx, width, height) => {
    labelCtx.clearRect(0, 0, width, height);
    labelCtx.fillStyle = options.background ?? "rgba(8, 14, 25, 0.92)";
    drawRoundedRect(labelCtx, 8, 8, width - 16, height - 16, options.radius ?? 26);
    labelCtx.fill();
    labelCtx.strokeStyle = options.border ?? "rgba(167, 196, 226, 0.24)";
    labelCtx.lineWidth = 4;
    labelCtx.stroke();
    labelCtx.font = `${options.weight ?? 800} ${options.size ?? 34}px Inter, Arial, sans-serif`;
    labelCtx.textAlign = "center";
    labelCtx.textBaseline = "middle";
    labelCtx.fillStyle = options.color ?? "#eef6ff";
    labelCtx.fillText(text.slice(0, 28), width / 2, height / 2 + 1);
  }, options.width ?? 512, options.height ?? 128);
  sprite.material.map = texture;
  sprite.material.needsUpdate = true;
  if (oldTexture) {
    oldTexture.dispose();
  }
}

function addMesh(group, geometry, material, position, scale = null, castShadow = true) {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(position.x ?? 0, position.y ?? 0, position.z ?? 0);
  if (scale) {
    mesh.scale.set(scale.x ?? 1, scale.y ?? 1, scale.z ?? 1);
  }
  mesh.castShadow = castShadow;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

function roomCenter(room) {
  return {
    x: (room.col + room.columns / 2) * roomConfig.cellSize - roomConfig.width / 2,
    z: (room.row + room.rows / 2) * roomConfig.cellSize - roomConfig.depth / 2,
  };
}

function roomContainsTile(room, tile) {
  return Boolean(
    room
    && tile
    && roomCells(room).some((cell) => tileEquals(cell, tile))
  );
}

function roomForTile(tile) {
  return roomLayout.find((room) => roomContainsTile(room, tile)) ?? null;
}

function tileForRoomCenter(room) {
  const cells = roomCells(room);
  if (!cells.length) {
    return {
      col: Math.floor(room.col + room.columns / 2),
      row: Math.floor(room.row + room.rows / 2),
    };
  }
  const centerCol = room.col + (room.columns - 1) / 2;
  const centerRow = room.row + (room.rows - 1) / 2;
  return cells.reduce((best, cell) => {
    const bestDistance = Math.hypot(best.col - centerCol, best.row - centerRow);
    const distance = Math.hypot(cell.col - centerCol, cell.row - centerRow);
    return distance < bestDistance ? cell : best;
  }, cells[0]);
}

function focusRoom(room) {
  const center = roomCenter(room);
  cameraTarget.set(center.x, 0, center.z);
  updateCamera();
}

function agentsInRoom(room) {
  return network.agents.filter((agent) => {
    const state = agentWorld.getAgentState(agent.id);
    return roomContainsTile(room, state?.tile);
  });
}

function placeSelectionInRoom(roomId) {
  const room = roomLayout.find((item) => item.id === roomId);
  if (!room) {
    return;
  }
  const target = tileForRoomCenter(room);
  let moved = false;
  if (selectedStationId) {
    moved = agentWorld.commandMoveStation(selectedStationId, target);
    if (moved) {
      moveStationVisual(selectedStationId);
      setBootMessage(`${agentWorld.getStation(selectedStationId)?.label ?? "Postazione"} spostata in ${room.label}.`);
    }
  } else if (selectedAgentId) {
    moved = agentWorld.commandPlaceAgent(selectedAgentId, target, `assigned to ${room.label}`);
    if (moved) {
      setAutoAgents(false);
      setBootMessage(`${network.getAgent(selectedAgentId)?.label ?? "Agente"} spostato in ${room.label}.`);
    }
  }
  if (moved) {
    selectedRoomId = room.id;
    focusRoom(room);
    saveLayoutState();
    updateHud();
  } else {
    setBootMessage(`Non riesco a trovare un tile libero in ${room.label}.`);
  }
}

function createRoomVisual(room) {
  if (roomVisuals.has(room.id)) {
    return roomVisuals.get(room.id);
  }
  const group = new THREE.Group();
  const center = roomCenter(room);
  const cells = roomCells(room);
  const cellKeys = new Set(cells.map(tileKey));
  const roomWidth = Math.max(1, room.columns) * roomConfig.cellSize;
  const roomDepth = Math.max(1, room.rows) * roomConfig.cellSize;
  const accentColor = new THREE.Color(room.color ?? "#38bdf8");

  const tileGeometry = new THREE.BoxGeometry(0.94, roomConfig.blockHeight, 0.94);
  for (const tile of cells) {
    const key = tileKey(tile);
    if (tileVisuals.has(key)) {
      continue;
    }
    const world = tileToWorld(tile);
    const baseColor = tileBaseColorFor(tile);
    const material = new THREE.MeshStandardMaterial({
      color: baseColor,
      emissive: baseColor.clone().multiplyScalar(0.035),
      roughness: 0.76,
      metalness: 0.12,
    });
    const mesh = new THREE.Mesh(tileGeometry, material);
    mesh.position.set(world.x, -roomConfig.blockHeight / 2, world.z);
    mesh.receiveShadow = true;
    mesh.userData.tile = tile;
    mesh.userData.tileKey = key;
    mesh.userData.roomId = room.id;
    mesh.userData.baseColor = baseColor.clone();
    group.add(mesh);
    tileVisuals.set(key, mesh);
    selectableObjects.push(mesh);
  }

  const wallHeight = 1.05;
  const wallThickness = 0.13;
  const wallDirections = [
    { dc: 0, dr: -1, width: 1, depth: wallThickness, offsetX: 0, offsetZ: -0.5, accentY: 0.18, accentOffsetX: 0, accentOffsetZ: -0.43 },
    { dc: 0, dr: 1, width: 1, depth: wallThickness, offsetX: 0, offsetZ: 0.5, accentY: 0.08, accentOffsetX: 0, accentOffsetZ: 0.43 },
    { dc: -1, dr: 0, width: wallThickness, depth: 1, offsetX: -0.5, offsetZ: 0, accentY: 0.18, accentOffsetX: -0.43, accentOffsetZ: 0 },
    { dc: 1, dr: 0, width: wallThickness, depth: 1, offsetX: 0.5, offsetZ: 0, accentY: 0.08, accentOffsetX: 0.43, accentOffsetZ: 0 },
  ];

  const accentMaterial = new THREE.MeshBasicMaterial({
    color: accentColor,
    transparent: true,
    opacity: 0.55,
  });

  for (const tile of cells) {
    const world = tileToWorld(tile);
    for (const direction of wallDirections) {
      const neighbor = { col: tile.col + direction.dc, row: tile.row + direction.dr };
      const neighborRoom = roomForTile(neighbor);
      if (cellKeys.has(tileKey(neighbor)) || isDoorTile(tile) || isDoorTile(neighbor)) {
        continue;
      }
      if (neighborRoom && neighborRoom.id !== room.id && String(room.id) > String(neighborRoom.id)) {
        continue;
      }
      const wall = new THREE.Mesh(
        new THREE.BoxGeometry(direction.width, wallHeight, direction.depth),
        sharedMaterials.wall
      );
      wall.position.set(world.x + direction.offsetX, 0.52, world.z + direction.offsetZ);
      wall.castShadow = true;
      wall.receiveShadow = true;
      group.add(wall);

      const trim = new THREE.Mesh(
        new THREE.BoxGeometry(direction.width, 0.07, direction.depth),
        sharedMaterials.trim
      );
      trim.position.set(world.x + direction.offsetX, 0.055, world.z + direction.offsetZ);
      group.add(trim);

      const accent = new THREE.Mesh(
        new THREE.BoxGeometry(
          Math.max(0.02, direction.width - (direction.width > direction.depth ? 0.18 : 0)),
          0.025,
          Math.max(0.02, direction.depth - (direction.depth > direction.width ? 0.18 : 0))
        ),
        accentMaterial
      );
      accent.position.set(world.x + direction.accentOffsetX, direction.accentY, world.z + direction.accentOffsetZ);
      group.add(accent);
    }
  }

  const label = createTextSprite(room.label, {
    background: "rgba(8, 14, 25, 0.62)",
    color: "#c7d2fe",
    size: 30,
    scaleX: 2.1,
    scaleY: 0.42,
  });
  label.position.set(center.x, 0.08, center.z + roomDepth / 2 - 0.7);
  label.rotation.x = -Math.PI / 2;
  group.add(label);

  if (room.id === "main") {
    const rug = new THREE.Mesh(
      new THREE.CylinderGeometry(2.15, 2.15, 0.035, 32),
      new THREE.MeshStandardMaterial({
        color: 0x17172e,
        emissive: 0x151030,
        roughness: 0.62,
        metalness: 0.22,
      })
    );
    rug.position.set(0, 0.03, -3.75);
    rug.receiveShadow = true;
    group.add(rug);

    const rugRing = new THREE.Mesh(
      new THREE.TorusGeometry(2.02, 0.025, 8, 64),
      new THREE.MeshBasicMaterial({ color: 0x9b87f5, transparent: true, opacity: 0.6 })
    );
    rugRing.rotation.x = Math.PI / 2;
    rugRing.position.set(0, 0.065, -3.75);
    group.add(rugRing);
  }

  scene.add(group);
  roomVisuals.set(room.id, group);
  return group;
}

function createDoorVisuals() {
  if (doorVisualGroup) {
    return doorVisualGroup;
  }
  doorVisualGroup = new THREE.Group();
  const doorTileGeometry = new THREE.BoxGeometry(0.88, roomConfig.blockHeight * 0.82, 0.88);
  const markerGeometry = new THREE.BoxGeometry(0.56, 0.08, 0.18);
  for (const tile of doorLayout) {
    const key = tileKey(tile);
    const world = tileToWorld(tile);
    let floorMesh = tileVisuals.get(key);
    if (!floorMesh) {
      const baseColor = tileBaseColorFor(tile);
      const material = new THREE.MeshStandardMaterial({
        color: baseColor,
        emissive: baseColor.clone().multiplyScalar(0.08),
        roughness: 0.62,
        metalness: 0.18,
      });
      floorMesh = new THREE.Mesh(doorTileGeometry, material);
      floorMesh.position.set(world.x, -roomConfig.blockHeight / 2 + 0.01, world.z);
      floorMesh.receiveShadow = true;
      floorMesh.userData.tile = tile;
      floorMesh.userData.tileKey = key;
      floorMesh.userData.doorTile = true;
      floorMesh.userData.baseColor = baseColor.clone();
      doorVisualGroup.add(floorMesh);
      tileVisuals.set(key, floorMesh);
      selectableObjects.push(floorMesh);
    } else {
      floorMesh.userData.baseColor = tileBaseColorFor(tile).clone();
      floorMesh.material.color.copy(floorMesh.userData.baseColor);
      floorMesh.material.emissive?.copy(floorMesh.userData.baseColor).multiplyScalar(0.08);
    }

    const markerMaterial = new THREE.MeshStandardMaterial({
      color: tilePalette.door,
      emissive: tilePalette.door.clone().multiplyScalar(0.18),
      roughness: 0.4,
      metalness: 0.25,
    });
    markerMaterial.userData.themeRole = "door-marker";
    const marker = new THREE.Mesh(markerGeometry, markerMaterial);
    marker.position.set(world.x, 0.08, world.z);
    marker.rotation.y = tile.col % 2 === 0 ? 0 : Math.PI / 2;
    marker.userData.tile = tile;
    marker.userData.doorMarker = true;
    marker.castShadow = true;
    marker.receiveShadow = true;
    doorVisualGroup.add(marker);
    selectableObjects.push(marker);
  }
  scene.add(doorVisualGroup);
  return doorVisualGroup;
}

function buildRoom() {
  for (const room of roomLayout) {
    createRoomVisual(room);
  }
  createDoorVisuals();
}

function buildEditorGrid() {
  if (editorTileVisuals.size > 0) {
    return;
  }
  const geometry = new THREE.BoxGeometry(0.92, 0.018, 0.92);
  for (let row = 0; row < roomConfig.rows; row += 1) {
    for (let col = 0; col < roomConfig.columns; col += 1) {
      const tile = { col, row };
      const key = tileKey(tile);
      const world = tileToWorld(tile);
      const mesh = new THREE.Mesh(geometry, editorGridMaterial);
      mesh.position.set(world.x, -roomConfig.blockHeight - 0.03, world.z);
      mesh.userData.tile = tile;
      mesh.userData.tileKey = key;
      mesh.userData.editorTile = true;
      mesh.renderOrder = -1;
      scene.add(mesh);
      selectableObjects.push(mesh);
      editorTileVisuals.set(key, mesh);
    }
  }
}

function clearLayoutVisuals() {
  for (const group of roomVisuals.values()) {
    scene.remove(group);
  }
  roomVisuals.clear();
  if (doorVisualGroup) {
    scene.remove(doorVisualGroup);
    doorVisualGroup = null;
  }
  tileVisuals.clear();
  for (let index = selectableObjects.length - 1; index >= 0; index -= 1) {
    const object = selectableObjects[index];
    if (object.userData.tile && !object.userData.editorTile) {
      selectableObjects.splice(index, 1);
    }
  }
}

function rebuildLayoutVisuals() {
  clearLayoutVisuals();
  buildRoom();
  agentWorld.refreshBlockedTiles();
  applyTheme(currentTheme, { persist: false });
  updateHud();
}

function toggleSelectedRoomCell(tile) {
  if (!selectedRoomId) {
    selectedRoomId = roomLayout[0]?.id ?? null;
  }
  const room = roomLayout.find((item) => item.id === selectedRoomId);
  if (!room) {
    setBootMessage("Seleziona prima una stanza dal pannello Stanze.");
    return;
  }
  const removing = roomContainsTile(room, tile);
  if (removing && agentWorld.isOccupiedTile(tile)) {
    setBootMessage("Non posso rimuovere una cella occupata da un agente.");
    return;
  }
  if (removing && agentWorld.isStationTileOccupied(tile)) {
    setBootMessage("Non posso rimuovere una cella occupata da un tavolo.");
    return;
  }
  const result = toggleRoomCell(room.id, tile);
  if (!result.changed) {
    const reason = result.reason === "occupied-by-room"
      ? `Cella gia usata da ${result.room?.label ?? "un'altra stanza"}.`
      : result.reason === "room-too-small"
        ? "Una stanza deve avere almeno 3 celle."
        : result.reason === "room-not-contiguous"
          ? "Aggiungi celle adiacenti alla stanza selezionata."
          : result.reason === "room-disconnected"
            ? "Non posso spezzare una stanza in isole separate."
            : "Cella non valida per questa stanza.";
    setBootMessage(reason);
    return;
  }
  selectedRoomId = room.id;
  rebuildLayoutVisuals();
  saveLayoutState();
  setBootMessage(`${room.label}: cella ${result.added ? "aggiunta" : "rimossa"}.`);
}

function toggleDoorCell(tile) {
  const removingOnlyPassage = isDoorTile(tile) && !roomForTile(tile);
  if (removingOnlyPassage && agentWorld.isOccupiedTile(tile)) {
    setBootMessage("Non posso rimuovere una porta/corridoio occupata da un agente.");
    return;
  }
  if (removingOnlyPassage && agentWorld.isStationTileOccupied(tile)) {
    setBootMessage("Non posso rimuovere una porta/corridoio occupata da un tavolo.");
    return;
  }
  const result = toggleDoorAt(tile);
  if (!result.changed) {
    setBootMessage("Cella porta non valida.");
    return;
  }
  selectedRoomId = roomForTile(tile)?.id ?? selectedRoomId;
  rebuildLayoutVisuals();
  saveLayoutState();
  setBootMessage(`Porta/corridoio ${result.added ? "aggiunto" : "rimosso"}.`);
}

function deleteSelectedRoom() {
  const room = selectedRoomId ? roomLayout.find((item) => item.id === selectedRoomId) : null;
  if (!room) {
    setBootMessage("Seleziona prima una stanza da rimuovere.");
    return;
  }
  if (roomLayout.length <= 1) {
    setBootMessage("Non posso rimuovere l'ultima stanza.");
    return;
  }
  const roomAgents = agentsInRoom(room);
  if (roomAgents.length > 0) {
    setBootMessage(`Sposta prima gli agenti fuori da ${room.label}.`);
    return;
  }
  const roomStations = stationsInRoom(room);
  if (roomStations.length > 0) {
    setBootMessage(`Sposta prima i tavoli fuori da ${room.label}.`);
    return;
  }

  const roomIndex = roomLayout.findIndex((item) => item.id === room.id);
  const deletedKeys = new Set(roomCells(room).map(tileKey));
  const result = removeRoomFromLayout(room.id);
  if (!result.changed) {
    setBootMessage(result.reason === "last-room" ? "Non posso rimuovere l'ultima stanza." : "Stanza non trovata.");
    return;
  }
  setDoorLayout(doorLayout.filter((door) => !deletedKeys.has(tileKey(door))));
  selectedRoomId = roomLayout[Math.min(roomIndex, roomLayout.length - 1)]?.id ?? null;
  rebuildLayoutVisuals();
  saveLayoutState();
  setBootMessage(`${room.label} rimossa.`);
}

function buildLights() {
  scene.add(new THREE.HemisphereLight(0xbfe9ff, 0x070b14, 1.25));

  const key = new THREE.DirectionalLight(0xddeeff, 2.8);
  key.position.set(5, 9, 6);
  key.castShadow = PERFORMANCE.shadows;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -11;
  key.shadow.camera.right = 11;
  key.shadow.camera.top = 11;
  key.shadow.camera.bottom = -11;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0x647dff, 1.1);
  fill.position.set(-7, 6, -3);
  scene.add(fill);

  const cyanGlow = new THREE.PointLight(0x5ee7f2, 10, 12, 2);
  cyanGlow.position.set(-3.8, 2.8, 2.5);
  scene.add(cyanGlow);

  const violetGlow = new THREE.PointLight(0x9b87f5, 8, 10, 2);
  violetGlow.position.set(3.8, 2.5, -2.8);
  scene.add(violetGlow);
}

function createStationProp(station) {
  const group = new THREE.Group();
  const theme = WORLD_THEMES[currentTheme];
  const stationMaterial = colorMaterial(station.color, {
    emissive: new THREE.Color(station.color).multiplyScalar(0.12),
    roughness: 0.48,
    metalness: 0.18,
  });
  const darkMaterial = colorMaterial(theme.stationSurface, {
    emissive: theme.stationSurfaceEmissive,
    roughness: 0.52,
    metalness: 0.3,
  });
  darkMaterial.userData.themeRole = "station-surface";
  const lightMaterial = colorMaterial(station.color, {
    emissive: new THREE.Color(station.color).multiplyScalar(0.8),
    roughness: 0.24,
    metalness: 0.16,
  });

  const base = new THREE.Mesh(
    new THREE.CylinderGeometry(0.88, 0.92, 0.08, 24),
    new THREE.MeshStandardMaterial({
      color: station.color,
      transparent: true,
      opacity: 0.16,
      emissive: new THREE.Color(station.color).multiplyScalar(0.2),
      roughness: 0.42,
      metalness: 0.24,
    })
  );
  base.position.y = 0.04;
  base.receiveShadow = true;
  group.add(base);

  const baseRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.84, 0.018, 8, 40),
    new THREE.MeshBasicMaterial({ color: station.color, transparent: true, opacity: 0.72 })
  );
  baseRing.rotation.x = Math.PI / 2;
  baseRing.position.y = 0.085;
  group.add(baseRing);

  if (station.id === "hub") {
    addMesh(group, new THREE.CylinderGeometry(0.76, 0.9, 0.42, 8), darkMaterial, { y: 0.26 });
    for (let i = 0; i < 4; i += 1) {
      const monitor = addMesh(
        group,
        new THREE.BoxGeometry(0.55, 0.36, 0.06),
        lightMaterial,
        { x: Math.cos(i * Math.PI * 0.5) * 0.72, y: 0.72, z: Math.sin(i * Math.PI * 0.5) * 0.72 }
      );
      monitor.lookAt(0, 0.72, 0);
    }
  } else if (station.id === "planning") {
    addMesh(group, new THREE.BoxGeometry(1.7, 0.12, 0.55), darkMaterial, { y: 0.38 });
    const board = addMesh(group, new THREE.BoxGeometry(1.9, 1.12, 0.1), stationMaterial, {
      y: 1.08,
      z: -0.35,
    });
    board.rotation.x = -0.08;
    for (let i = 0; i < 5; i += 1) {
      addMesh(group, new THREE.BoxGeometry(0.18, 0.1, 0.035), lightMaterial, {
        x: -0.68 + i * 0.34,
        y: 1.16 + (i % 2) * 0.18,
        z: -0.41,
      });
    }
  } else if (station.id === "research") {
    addMesh(group, new THREE.BoxGeometry(1.6, 0.16, 0.72), darkMaterial, { y: 0.46 });
    addMesh(group, new THREE.BoxGeometry(0.86, 0.56, 0.08), lightMaterial, { y: 0.94, z: -0.22 });
    addMesh(group, new THREE.BoxGeometry(0.9, 0.06, 0.34), stationMaterial, { y: 0.58, z: 0.24 });
  } else if (station.id === "build") {
    addMesh(group, new THREE.BoxGeometry(1.76, 0.32, 0.82), darkMaterial, { y: 0.34 });
    for (let i = 0; i < 4; i += 1) {
      addMesh(group, new THREE.BoxGeometry(0.28, 0.22 + i * 0.03, 0.28), stationMaterial, {
        x: -0.58 + i * 0.38,
        y: 0.68 + i * 0.025,
        z: -0.12 + (i % 2) * 0.3,
      });
    }
  } else if (station.id === "review") {
    addMesh(group, new THREE.BoxGeometry(1.55, 0.2, 0.95), darkMaterial, { y: 0.42 });
    addMesh(group, new THREE.ConeGeometry(0.3, 0.55, 16), stationMaterial, { y: 0.88, z: -0.2 });
    addMesh(group, new THREE.BoxGeometry(1.1, 0.035, 0.54), lightMaterial, { y: 0.58, z: 0.16 });
  } else if (station.id === "memory") {
    addMesh(group, new THREE.CylinderGeometry(0.48, 0.58, 1.35, 20), sharedMaterials.glass, { y: 0.78 });
    const core = addMesh(group, new THREE.IcosahedronGeometry(0.42, 1), lightMaterial, { y: 0.84 });
    core.userData.spin = 1.2;
  } else {
    addMesh(group, new THREE.CylinderGeometry(1.08, 1.08, 0.22, 20), darkMaterial, { y: 0.14 });
    for (let i = 0; i < 6; i += 1) {
      addMesh(group, new THREE.BoxGeometry(0.32, 0.28, 0.32), stationMaterial, {
        x: Math.cos((i / 6) * Math.PI * 2) * 1.18,
        y: 0.18,
        z: Math.sin((i / 6) * Math.PI * 2) * 1.18,
      });
    }
  }

  const label = createTextSprite(station.label, {
    background: "rgba(8, 14, 25, 0.88)",
    color: "#eef6ff",
    size: 34,
    scaleX: 2.3,
    scaleY: 0.48,
  });
  label.position.set(0, 1.85, 0);
  group.add(label);

  group.position.set(station.position.x, 0, station.position.z);
  group.userData.stationId = station.id;
  for (const child of group.children) {
    child.userData.stationId = station.id;
  }
  scene.add(group);
  stationVisuals.set(station.id, group);
  selectableObjects.push(...group.children.filter((child) => child.isMesh));
}

function createAgentVisual(agent) {
  const group = new THREE.Group();
  const bodyMaterial = colorMaterial(agent.color, {
    emissive: new THREE.Color(agent.color).multiplyScalar(0.1),
    roughness: 0.42,
    metalness: 0.2,
  });
  const headMaterial = colorMaterial(0xdce7f3, { roughness: 0.36, metalness: 0.28 });
  const darkMaterial = colorMaterial(0x111827, { roughness: 0.5, metalness: 0.34 });
  const glowMaterial = colorMaterial(agent.color, {
    emissive: new THREE.Color(agent.color).multiplyScalar(0.95),
    roughness: 0.18,
    metalness: 0.1,
  });

  const shadow = new THREE.Mesh(new THREE.CircleGeometry(0.48, 16), sharedMaterials.shadow);
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.018;
  shadow.userData.agentId = agent.id;
  group.add(shadow);

  const selectionRing = new THREE.Mesh(
    new THREE.RingGeometry(0.46, 0.54, 32),
    new THREE.MeshBasicMaterial({
      color: agent.color,
      transparent: true,
      opacity: 0.8,
      side: THREE.DoubleSide,
      depthWrite: false,
    })
  );
  selectionRing.rotation.x = -Math.PI / 2;
  selectionRing.position.y = 0.025;
  selectionRing.visible = false;
  group.add(selectionRing);

  const torso = addMesh(group, new THREE.CylinderGeometry(0.28, 0.34, 0.72, 12), bodyMaterial, {
    y: 0.72,
  });
  const head = addMesh(group, new THREE.SphereGeometry(0.25, 16, 12), headMaterial, { y: 1.22 });
  const visor = addMesh(group, new THREE.BoxGeometry(0.32, 0.08, 0.035), glowMaterial, { y: 1.24, z: 0.22 });
  const leftLeg = addMesh(group, new THREE.BoxGeometry(0.13, 0.46, 0.14), darkMaterial, {
    x: -0.11,
    y: 0.28,
  });
  const rightLeg = addMesh(group, new THREE.BoxGeometry(0.13, 0.46, 0.14), darkMaterial, {
    x: 0.11,
    y: 0.28,
  });
  const leftArm = addMesh(group, new THREE.BoxGeometry(0.11, 0.52, 0.12), bodyMaterial, {
    x: -0.37,
    y: 0.72,
  });
  const rightArm = addMesh(group, new THREE.BoxGeometry(0.11, 0.52, 0.12), bodyMaterial, {
    x: 0.37,
    y: 0.72,
  });

  const diamondTop = new THREE.Mesh(new THREE.ConeGeometry(0.18, 0.34, 4), glowMaterial);
  diamondTop.position.y = 1.85;
  diamondTop.rotation.y = Math.PI * 0.25;
  diamondTop.userData.agentId = agent.id;
  group.add(diamondTop);

  const diamondBottom = new THREE.Mesh(new THREE.ConeGeometry(0.18, 0.34, 4), glowMaterial);
  diamondBottom.position.y = 1.52;
  diamondBottom.rotation.x = Math.PI;
  diamondBottom.rotation.y = Math.PI * 0.25;
  diamondBottom.userData.agentId = agent.id;
  group.add(diamondBottom);

  const name = createTextSprite(agent.label, {
    background: "rgba(8, 14, 25, 0.9)",
    color: "#f3f8ff",
    size: 36,
    scaleX: 1.7,
    scaleY: 0.42,
  });
  name.position.set(0, 2.2, 0);
  group.add(name);

  const bubble = createTextSprite("", {
    background: "rgba(8, 14, 25, 0.94)",
    color: "#f3f8ff",
    size: 32,
    scaleX: 1.75,
    scaleY: 0.44,
  });
  bubble.position.set(0, 2.62, 0);
  bubble.visible = false;
  group.add(bubble);

  for (const child of group.children) {
    child.userData.agentId = agent.id;
  }

  scene.add(group);
  selectableObjects.push(torso, head, visor, leftLeg, rightLeg, leftArm, rightArm, diamondTop, diamondBottom);
  agentVisuals.set(agent.id, {
    group,
    torso,
    head,
    leftLeg,
    rightLeg,
    leftArm,
    rightArm,
    diamondTop,
    diamondBottom,
    selectionRing,
    bubble,
    name,
  });
}

function buildRelationVisuals() {
  for (const relation of network.relations) {
    createRelationVisual(relation);
  }
}

function createRelationVisual(relation) {
  if (relationVisuals.has(relation.id)) {
    return relationVisuals.get(relation.id);
  }
  const protocol = network.getProtocol(relation.protocolId);
  if (!protocol) {
    return null;
  }
  const material = new THREE.LineBasicMaterial({
    color: protocol.color,
    transparent: true,
    opacity: 0.28,
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3));
  const line = new THREE.Line(geometry, material);
  line.position.y = 0.06;
  scene.add(line);
  relationVisuals.set(relation.id, line);
  return line;
}

function updateRelationVisuals() {
  for (const relation of network.relations) {
    const line = relationVisuals.get(relation.id);
    const from = agentWorld.getAgentPosition(relation.from);
    const to = agentWorld.getAgentPosition(relation.to);
    const positions = line.geometry.attributes.position;
    positions.setXYZ(0, from.x, 0.05, from.z);
    positions.setXYZ(1, (from.x + to.x) / 2, 0.05, (from.z + to.z) / 2);
    positions.setXYZ(2, to.x, 0.05, to.z);
    positions.needsUpdate = true;
    line.geometry.computeBoundingSphere();
  }
}

function curveForMessage(message) {
  const from = agentWorld.getAgentPosition(message.from);
  const to = agentWorld.getAgentPosition(message.to);
  scratchStart.set(from.x, 1.55, from.z);
  scratchEnd.set(to.x, 1.55, to.z);
  scratchMid.lerpVectors(scratchStart, scratchEnd, 0.5);
  scratchMid.y += 1.2 + message.priority * 0.18;
  scratchCurve.v0.copy(scratchStart);
  scratchCurve.v1.copy(scratchMid);
  scratchCurve.v2.copy(scratchEnd);
  return scratchCurve;
}

function createMessageVisual(message) {
  const protocol = network.getProtocol(message.protocolId);
  const material = new THREE.LineBasicMaterial({
    color: message.color,
    transparent: true,
    opacity: 0.86,
  });
  const lineGeometry = new THREE.BufferGeometry();
  lineGeometry.setAttribute(
    "position",
    new THREE.BufferAttribute(new Float32Array((PERFORMANCE.messageLineSegments + 1) * 3), 3)
  );
  const line = new THREE.Line(lineGeometry, material);
  scene.add(line);

  const packet = new THREE.Mesh(
    new THREE.SphereGeometry(0.11 + message.priority * 0.025, 12, 8),
    colorMaterial(message.color, {
      emissive: new THREE.Color(message.color).multiplyScalar(0.75),
      roughness: 0.2,
    })
  );
  packet.castShadow = true;
  scene.add(packet);

  const label = createTextSprite(protocol.messageTypes[message.type]?.shortLabel ?? message.type, {
    background: "rgba(8, 14, 25, 0.94)",
    color: "#f3f8ff",
    size: 30,
    scaleX: 1.4,
    scaleY: 0.34,
  });
  label.visible = message.priority >= 3;
  scene.add(label);

  messageVisuals.set(message.id, { line, packet, label });
}

function updateMessageVisuals() {
  const liveIds = new Set(network.messages.map((message) => message.id));

  for (const message of network.messages) {
    if (!messageVisuals.has(message.id)) {
      createMessageVisual(message);
    }
    const visual = messageVisuals.get(message.id);
    const curve = curveForMessage(message);
    const positions = visual.line.geometry.attributes.position;
    for (let i = 0; i <= PERFORMANCE.messageLineSegments; i += 1) {
      const point = curve.getPoint(i / PERFORMANCE.messageLineSegments);
      positions.setXYZ(i, point.x, point.y, point.z);
    }
    positions.needsUpdate = true;
    visual.line.geometry.computeBoundingSphere();
    const packetPosition = curve.getPoint(message.progress);
    visual.packet.position.copy(packetPosition);
    visual.label.position.copy(packetPosition).add(new THREE.Vector3(0, 0.34, 0));
  }

  for (const [id, visual] of messageVisuals) {
    if (liveIds.has(id)) {
      continue;
    }
    scene.remove(visual.line, visual.packet, visual.label);
    visual.line.geometry.dispose();
    visual.line.material.dispose();
    visual.packet.geometry.dispose();
    visual.packet.material.dispose();
    visual.label.material.map?.dispose();
    visual.label.material.dispose();
    messageVisuals.delete(id);
  }
}

function buildScene() {
  buildLights();
  buildRoom();
  buildEditorGrid();
  for (const station of workstations) {
    createStationProp(station);
  }
  for (const agent of network.agents) {
    createAgentVisual(agent);
  }
  buildRelationVisuals();
}

function updateCamera() {
  const aspect = window.innerWidth / window.innerHeight;
  camera.left = -cameraZoom * aspect;
  camera.right = cameraZoom * aspect;
  camera.top = cameraZoom;
  camera.bottom = -cameraZoom;
  const distance = 12;
  const height = 9.2;
  camera.position.set(
    cameraTarget.x + Math.sin(cameraYaw) * distance,
    height,
    cameraTarget.z + Math.cos(cameraYaw) * distance
  );
  camera.lookAt(cameraTarget.x, 0, cameraTarget.z);
  camera.updateProjectionMatrix();
}

function resize() {
  renderer.setSize(window.innerWidth, window.innerHeight);
  updateCamera();
}

function updateAgents(elapsed) {
  for (const agent of network.agents) {
    const state = agentWorld.getAgentState(agent.id);
    const visual = agentVisuals.get(agent.id);
    if (!state || !visual) {
      continue;
    }

    visual.group.position.set(state.x, state.y, state.z);
    visual.group.rotation.y = state.facing;

    const walking = state.mode === "walking";
    const stride = Math.sin(state.walkPhase) * (walking ? 0.42 : 0.08);
    visual.leftLeg.rotation.x = stride;
    visual.rightLeg.rotation.x = -stride;
    visual.leftArm.rotation.x = -stride * 0.8;
    visual.rightArm.rotation.x = stride * 0.8;
    visual.torso.position.y = 0.72 + Math.sin(state.walkPhase * 2) * (walking ? 0.035 : 0.012);
    visual.head.position.y = 1.22 + Math.sin(elapsed * 2.5 + state.seed) * 0.015;
    visual.diamondTop.rotation.y += 0.018;
    visual.diamondBottom.rotation.y += 0.018;

    const selected = selectedAgentId === agent.id;
    const scale = selected ? 1.1 : 1;
    visual.diamondTop.scale.setScalar(scale);
    visual.diamondBottom.scale.setScalar(scale);
    visual.selectionRing.visible = selected;
    visual.selectionRing.material.opacity = 0.64 + Math.sin(elapsed * 3) * 0.14;

    const reply = agentReplies.get(agent.id);
    if (reply && reply.expiresAt <= performance.now()) {
      agentReplies.delete(agent.id);
    }
    const activeReply = agentReplies.get(agent.id);
    const bubbleText = activeReply?.text.slice(0, 52) || state.bubble || agent.runtime.status;
    visual.bubble.visible = Boolean(bubbleText)
      && (Boolean(activeReply) || selectedAgentId === agent.id)
      && quickChatAgentId !== agent.id;
    if (visual.bubble.visible) {
      replaceSpriteText(visual.bubble, bubbleText, {
        background: "rgba(8, 14, 25, 0.95)",
        color: activeReply?.isError ? "#fecdd3" : "#f3f8ff",
        border: selected ? agent.color : "rgba(167, 196, 226, 0.24)",
      });
    }
  }
}

function updateStations(elapsed) {
  for (const station of workstations) {
    const group = stationVisuals.get(station.id);
    if (!group) {
      continue;
    }
    group.traverse((child) => {
      if (child.userData.spin) {
        child.rotation.y += child.userData.spin * 0.012;
        child.position.y = 0.84 + Math.sin(elapsed * 2) * 0.05;
      }
    });
    const selected = selectedStationId === station.id;
    group.scale.setScalar(selected ? 1.04 : 1);
  }
}

function updateTiles() {
  const selectedState = agentWorld.getAgentState(selectedAgentId);
  const selectedStation = selectedStationId ? agentWorld.getStation(selectedStationId) : null;
  const selectedStationTile = selectedStation ? worldToTile(selectedStation.position) : null;
  const selectedRoom = selectedRoomId ? roomLayout.find((room) => room.id === selectedRoomId) : null;
  const occupiedKeys = new Set();
  for (const agent of network.agents) {
    const state = agentWorld.getAgentState(agent.id);
    if (state) {
      occupiedKeys.add(tileKey(state.tile));
    }
  }

  for (const [key, mesh] of tileVisuals) {
    const tile = mesh.userData.tile;
    const baseColor = mesh.userData.baseColor;
    let renderState = "base";
    if (selectedStationTile && tileEquals(tile, selectedStationTile)) {
      renderState = "station";
    } else if (selectedState && tileEquals(tile, selectedState.destinationTile)) {
      renderState = "destination";
    } else if (selectedState && tileEquals(tile, selectedState.tile)) {
      renderState = "current";
    } else if (occupiedKeys.has(key)) {
      renderState = "occupied";
    } else if (selectedRoom && roomContainsTile(selectedRoom, tile)) {
      renderState = "room";
    }

    if (mesh.userData.renderState === renderState) {
      continue;
    }

    mesh.userData.renderState = renderState;
    if (renderState === "destination") {
      mesh.material.color.copy(tilePalette.destination);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.035;
    } else if (renderState === "station") {
      mesh.material.color.copy(tilePalette.station);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.04;
    } else if (renderState === "current") {
      mesh.material.color.copy(tilePalette.current);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.045;
    } else if (renderState === "occupied") {
      mesh.material.color.copy(tilePalette.occupied);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.015;
    } else if (renderState === "room") {
      mesh.material.color.copy(tilePalette.room);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.01;
    } else {
      mesh.material.color.copy(baseColor);
      mesh.position.y = -roomConfig.blockHeight / 2;
    }
  }
}

function updateHud() {
  const agent = network.getAgent(selectedAgentId) ?? network.agents[0];
  const state = agentWorld.getAgentState(agent.id);
  const station = agentWorld.getStation(state?.stationId);
  const currentRoom = roomForTile(state?.tile);

  selectedName.textContent = agent.label;
  selectedRole.textContent = agent.role;
  selectedJob.textContent = `${state?.jobLabel ?? "idle"} @ ${currentRoom?.label ?? station?.label ?? "room"}`;
  selectedStatus.textContent = agent.runtime.status;
  selectedLoad.textContent = `${Math.round(agent.runtime.load * 100)}%`;
  selectedTile.textContent = state ? `${state.tile.col + 1}, ${state.tile.row + 1}` : "-";

  metrics.innerHTML = `
    <span>${network.agents.length} agenti</span>
    <span>${roomLayout.length} stanze</span>
    <span>${network.messages.length} messaggi</span>
    <span>${network.relations.length} canali</span>
    <span>${speed}x</span>
    <span>${layoutMode ? "layout" : autoAgents ? "auto" : "manuale"}</span>
  `;

  eventLog.innerHTML = network.events
    .slice(0, 6)
    .map((event) => `<li><time>${event.timeLabel}</time><span>${event.text}</span></li>`)
    .join("");

  stationList.innerHTML = workstations
    .map((station) => {
      const workers = network.agents.filter((agentItem) => {
        const stateItem = agentWorld.getAgentState(agentItem.id);
        return stateItem?.stationId === station.id;
      });
      return `
        <button class="station-row ${station.id === selectedStationId ? "station-row--active" : ""}" data-station="${station.id}" type="button">
          <span class="station-row__dot" style="--station-color: ${station.color}"></span>
          <span>
            <strong>${station.label}</strong>
            <small>${workers.map((worker) => worker.label).join(", ") || "libera"}</small>
          </span>
        </button>
      `;
    })
    .join("");

  if (roomList) {
    roomList.innerHTML = roomLayout
      .map((room) => {
        const agents = agentsInRoom(room);
        const selected = room.id === selectedRoomId;
        const occupantText = agents.map((roomAgent) => roomAgent.label).join(", ") || "nessun agente";
        const cellCount = roomCells(room).length;
        return `
          <div class="room-row ${selected ? "room-row--active" : ""}" style="--room-color: ${room.color}">
            <button class="room-row__main" data-room="${escapeHtml(room.id)}" type="button">
              <span class="station-row__dot" style="--station-color: ${room.color}"></span>
              <span>
                <strong>${escapeHtml(room.label)}</strong>
                <small>${agents.length} agenti · ${cellCount} celle · ${escapeHtml(occupantText)}</small>
              </span>
            </button>
            <button class="room-row__action" data-room-place="${escapeHtml(room.id)}" type="button">
              Porta qui
            </button>
          </div>
        `;
      })
      .join("");
  }
  updateLayoutEditor();
}

function appendChatMessage(message) {
  if (message.id && chatMessageIds.has(message.id)) {
    return;
  }
  if (message.id) {
    chatMessageIds.add(message.id);
  }
  const item = document.createElement("li");
  item.className = `agent-quick-chat__message agent-quick-chat__message--${message.role}`;
  item.append(document.createTextNode(String(message.content)));
  const validSources = (message.sources ?? [])
    .map((source) => ({ ...source, safeUrl: safeWebUrl(source.url) }))
    .filter((source) => source.safeUrl);
  if (validSources.length) {
    const list = document.createElement("span");
    list.className = "agent-quick-chat__sources";
    for (const [index, source] of validSources.entries()) {
      const link = document.createElement("a");
      link.href = source.safeUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = `[${index + 1}] ${source.title || source.safeUrl}`;
      list.append(link);
    }
    item.append(list);
  }
  quickChatHistory.append(item);
  quickChatHistory.scrollTop = quickChatHistory.scrollHeight;
}

function renderChatHistory(messages) {
  quickChatHistory.replaceChildren();
  chatMessageIds.clear();
  for (const message of messages) {
    appendChatMessage(message);
  }
}

function openQuickChat(agentId) {
  const agent = network.getAgent(agentId);
  if (!agent) {
    return;
  }
  quickChatAgentId = agentId;
  quickChatAgent.textContent = agent.label;
  quickChatStatus.textContent = "";
  quickChatStatus.classList.remove("agent-quick-chat__status--error");
  quickChat.hidden = false;
  quickChatHistory.innerHTML = '<li class="agent-quick-chat__message">Caricamento...</li>';
  chatMessageIds.clear();
  updateQuickChatPosition();
  window.clearTimeout(quickChatFocusTimer);
  quickChatFocusTimer = window.setTimeout(() => quickChatInput.focus(), 220);
  runtimeClient.getAgentChat(agentId)
    .then((messages) => {
      if (quickChatAgentId === agentId) {
        renderChatHistory(messages);
      }
    })
    .catch((error) => {
      if (quickChatAgentId === agentId) {
        renderChatHistory([{ role: "system", content: error.message }]);
      }
    });
}

function closeQuickChat() {
  window.clearTimeout(quickChatFocusTimer);
  quickChatAgentId = null;
  quickChat.hidden = true;
  quickChatInput.value = "";
  quickChatHistory.replaceChildren();
  chatMessageIds.clear();
  quickChatStatus.textContent = "";
  quickChatStatus.classList.remove("agent-quick-chat__status--error");
}

function updateQuickChatPosition() {
  if (!quickChatAgentId || quickChat.hidden) {
    return;
  }
  const position = agentWorld.getAgentPosition(quickChatAgentId);
  quickChatPosition.set(position.x, 3.25, position.z).project(camera);
  const visible = quickChatPosition.z > -1 && quickChatPosition.z < 1;
  quickChat.style.visibility = visible ? "visible" : "hidden";
  if (!visible) {
    return;
  }
  const margin = Math.min((quickChat.offsetWidth || 360) / 2 + 12, window.innerWidth / 2);
  const x = Math.max(margin, Math.min(window.innerWidth - margin, (quickChatPosition.x + 1) * 0.5 * window.innerWidth));
  const minimumY = Math.min(window.innerHeight - 20, (quickChat.offsetHeight || 220) + 20);
  const y = Math.max(minimumY, Math.min(window.innerHeight - 20, (1 - quickChatPosition.y) * 0.5 * window.innerHeight));
  quickChat.style.left = `${x}px`;
  quickChat.style.top = `${y}px`;
}

function animate(now = 0) {
  requestAnimationFrame(animate);
  const frameInterval = 1000 / PERFORMANCE.maxFps;
  if (now - lastFrameAt < frameInterval) {
    return;
  }
  lastFrameAt = now;

  const delta = Math.min(clock.getDelta(), 0.08);
  const elapsed = clock.elapsedTime;

  if (running) {
    network.tick(delta * speed);
    agentWorld.tick(delta * speed, network, { autoEnabled: autoAgents });
  }

  updateAgents(elapsed);
  updateStations(elapsed);
  updateTiles();
  if (now >= nextRelationRefresh) {
    updateRelationVisuals();
    nextRelationRefresh = now + PERFORMANCE.relationRefreshMs;
  }
  updateMessageVisuals();
  updateQuickChatPosition();
  renderer.render(scene, camera);

  if (now >= nextUiRefresh) {
    updateHud();
    nextUiRefresh = now + PERFORMANCE.hudRefreshMs;
  }
}

function setSpeed(nextSpeed) {
  speed = nextSpeed;
  for (const button of speedControl.querySelectorAll("[data-speed]")) {
    button.classList.toggle("segment--active", Number(button.dataset.speed) === speed);
  }
}

function setRunning(nextRunning) {
  running = nextRunning;
  runToggle.textContent = running ? "Pausa" : "Avvia";
}

function setAutoAgents(nextAutoAgents) {
  autoAgents = nextAutoAgents;
  autoToggle.textContent = autoAgents ? "Auto" : "Manuale";
  autoToggle.classList.toggle("button--primary", autoAgents);
  updateHud();
}

async function triggerIntent(intentId) {
  if (runtimeClient.connected) {
    const taskRecipes = {
      task: {
        title: "Plan the next agent workflow",
        description: "Create and execute a structured plan through the native runtime.",
        capability: "planning",
        priority: 3,
      },
      schedule: {
        title: "Prepare the next runtime schedule",
        description: "Review upcoming work, propose concrete run times, and explain which tasks should be delegated to the native scheduler.",
        capability: "scheduling",
        priority: 3,
        requested_agent_id: "scheduler",
      },
      "memory-sync": {
        title: "Synchronize shared runtime context",
        description: "Review current state and prepare a memory update.",
        capability: "memory",
        priority: 2,
      },
      review: {
        title: "Review the latest runtime result",
        description: "Check protocol consistency, risks, and expected output.",
        capability: "review",
        priority: 3,
      },
    };
    try {
      await runtimeClient.createTask(taskRecipes[intentId]);
    } catch (error) {
      setBootMessage(error.message);
    }
  } else {
    network.triggerIntent(intentId);
    agentWorld.triggerIntent(intentId, network, { autoEnabled: autoAgents });
    updateHud();
  }
}

function positionForAgent(id) {
  let hash = 0;
  for (const character of id) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return {
    x: 0.22 + (hash % 57) / 100,
    y: 0.2 + (Math.floor(hash / 57) % 59) / 100,
  };
}

function ensureSupervisorRelation(agentId) {
  if (agentId === "orchestrator" || network.findRelation("orchestrator", agentId, "contract-net")) {
    return;
  }
  const relation = network.registerRelation({
    id: `runtime-orchestrator-${agentId}`,
    from: "orchestrator",
    to: agentId,
    kind: "delegation",
    protocolId: "contract-net",
    latency: 0.75,
    trust: 0.82,
    bandwidth: 2,
    bidirectional: true,
  });
  createRelationVisual(relation);
}

function ensureRuntimeAgent(snapshot) {
  runtimeSnapshots.set(snapshot.id, snapshot);
  const existing = network.getAgent(snapshot.id);
  if (existing) {
    existing.label = snapshot.name;
    existing.role = snapshot.role;
    existing.color = snapshot.color;
    existing.capabilities = [...snapshot.capabilities];
    existing.runtime.status = snapshot.state;
    existing.runtime.load = snapshot.load;
    applyAgentAppearance(existing);
    const state = agentWorld.getAgentState(existing.id);
    if (state) {
      state.lastRuntimeStatus = "";
    }
    ensureSupervisorRelation(snapshot.id);
    return existing;
  }

  const agent = network.registerAgent({
    id: snapshot.id,
    label: snapshot.name,
    initials: snapshot.name.slice(0, 2).toUpperCase(),
    role: snapshot.role,
    color: snapshot.color,
    reliability: 0.84,
    capabilities: snapshot.capabilities,
    position: positionForAgent(snapshot.id),
    summary: `${snapshot.role} agent managed by the native runtime.`,
    runtime: { status: snapshot.state, load: snapshot.load },
  });
  agentWorld.registerAgent(agent);
  createAgentVisual(agent);
  ensureSupervisorRelation(snapshot.id);
  return agent;
}

function applyAgentAppearance(agent) {
  const visual = agentVisuals.get(agent.id);
  if (!visual) {
    return;
  }
  const color = new THREE.Color(agent.color);
  visual.torso.material.color.copy(color);
  visual.torso.material.emissive.copy(color).multiplyScalar(0.1);
  visual.diamondTop.material.color.copy(color);
  visual.diamondTop.material.emissive.copy(color).multiplyScalar(0.95);
  visual.selectionRing.material.color.copy(color);
  replaceSpriteText(visual.name, agent.label, {
    background: "rgba(8, 14, 25, 0.9)",
    color: "#f3f8ff",
    size: 36,
  });
}

function renderRuntimeMessage(event) {
  const message = event.data?.message;
  if (!message || !network.getAgent(message.sender) || !network.getAgent(message.recipient)) {
    return;
  }
  const typeMap = {
    "task.announce": "task.announce",
    "task.award": "task.award",
    "task.accept": "task.proposal",
    "task.progress": "task.status",
    "task.result": "task.status",
  };
  const type = typeMap[message.type];
  if (!type) {
    return;
  }
  network.enqueue({
    from: message.sender,
    to: message.recipient,
    protocolId: "contract-net",
    type,
    payload: message.payload,
    priority: message.priority,
    external: true,
  });
}

function safeWebUrl(value) {
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;
  } catch (_error) {
    return null;
  }
}

function renderQuickChatReply(text, sources = [], isError = false, taskId = "") {
  appendChatMessage({
    id: taskId ? `${taskId}-${isError ? "error" : "assistant"}` : "",
    role: isError ? "system" : "assistant",
    content: String(text),
    sources,
  });
  quickChatStatus.textContent = isError ? "Task fallito." : "Risposta ricevuta.";
  quickChatStatus.classList.toggle("agent-quick-chat__status--error", isError);
}

function showAgentReply(agentId, text, isError = false, sources = [], taskId = "") {
  if (!agentId || !text) {
    return;
  }
  agentReplies.set(agentId, {
    text: String(text),
    isError,
    expiresAt: performance.now() + 12000,
  });
  if (quickChatAgentId === agentId && !quickChat.hidden) {
    renderQuickChatReply(text, sources, isError, taskId);
  }
}

function handleRuntimeEvent(event) {
  if (event.type === "runtime.snapshot") {
    for (const agent of event.agents ?? []) {
      ensureRuntimeAgent(agent);
    }
    for (const historicEvent of (event.events ?? []).slice(-8)) {
      network.log(historicEvent.summary);
    }
  } else if (event.type === "agent.created" || event.type === "agent.updated") {
    ensureRuntimeAgent(event.data.agent);
  } else if (event.type === "agent.state.changed") {
    const agent = network.getAgent(event.agent_id);
    if (agent) {
      agent.runtime.status = event.data.to;
      agent.runtime.load = event.data.load;
    }
  } else if (event.type === "protocol.message") {
    renderRuntimeMessage(event);
    const message = event.data?.message;
    if (message?.type === "task.result") {
      showAgentReply(
        message.sender,
        message.payload?.summary ?? "Task completato.",
        false,
        message.payload?.sources ?? [],
        message.task_id ?? ""
      );
    }
  } else if (event.type === "task.state.changed" && event.data?.to === "failed") {
    const task = event.data?.task;
    showAgentReply(task?.assigned_agent_id, task?.error ?? "Task fallito.", true, [], task?.id ?? "");
  } else if (event.type?.startsWith("project.job.")) {
    const job = event.data?.job;
    const agent = job?.agent_id ? network.getAgent(job.agent_id) : null;
    if (agent) {
      const active = event.type === "project.job.queued" || event.type === "project.job.started";
      agent.runtime.status = active ? "executing" : event.type.endsWith("failed") ? "failed" : "idle";
      agent.runtime.load = active ? 0.82 : 0.08;
    }
    syncProjectJobToast(job, event.type);
    if (job?.state === "completed" || job?.state === "failed") {
      markCompletedJobUnread(job.id);
      if (projectDialog.open) {
        refreshProjectJobHistory(projectPanel === "finished");
      }
    }
    if (job && projectDialog.open) {
      if (projectPanel === "output") {
        renderProjectJobDetail(job);
      }
    }
  } else if (event.type === "runtime.disconnected") {
    setRuntimeConnection(false);
  }

  if (event.summary) {
    network.log(event.summary);
  }
  updateHud();
}

function selectedProject() {
  return availableProjects.find((project) => project.id === projectSelect.value);
}

function selectedProjectAction() {
  return selectedProject()?.actions.find((action) => action.id === projectAction.value);
}

function renderProjectActions() {
  const project = selectedProject();
  projectAction.innerHTML = (project?.actions ?? [])
    .map((action) => `<option value="${action.id}">${action.label ?? action.id}</option>`)
    .join("");
  renderProjectParameters();
}

function renderProjectParameters() {
  const action = selectedProjectAction();
  const booleanParameters = new Set(["refresh-browser-profile", "include-details", "llm-screening"]);
  projectParameters.innerHTML = (action?.parameters ?? [])
    .map((name) => {
      const type = booleanParameters.has(name) ? "checkbox" : name.includes("max-") ? "number" : "text";
      const checkedClass = type === "checkbox" ? " project-parameter--check" : "";
      return `<label class="${checkedClass}"><span>${name}</span><input data-project-parameter="${name}" type="${type}" /></label>`;
    })
    .join("");
  projectRisk.textContent = action ? `Rischio: ${action.risk}` : "";
  if (action?.description) {
    projectRisk.textContent += ` | ${action.description}`;
  }
  projectApprovalRow.hidden = !action?.requiresApproval;
  projectForm.elements.namedItem("approved").checked = false;
}

function readProjectParameters() {
  const parameters = {};
  for (const input of projectParameters.querySelectorAll("[data-project-parameter]")) {
    const value = input.type === "checkbox" ? input.checked : input.value.trim();
    if (value !== "" && value !== false) {
      parameters[input.dataset.projectParameter] = input.type === "number" ? Number(value) : value;
    }
  }
  return parameters;
}

async function refreshProjectPresets(selectedId = "") {
  availableProjectPresets = await runtimeClient.listProjectPresets(projectSelect.value);
  projectPresetSelect.replaceChildren(
    new Option("Nessun preset", ""),
    ...availableProjectPresets.map((preset) => new Option(preset.name, preset.id))
  );
  projectPresetSelect.value = selectedId;
}

function loadSelectedProjectPreset() {
  const preset = availableProjectPresets.find((item) => item.id === projectPresetSelect.value);
  if (!preset) {
    return;
  }
  projectAction.value = preset.action;
  renderProjectParameters();
  for (const input of projectParameters.querySelectorAll("[data-project-parameter]")) {
    const value = preset.parameters[input.dataset.projectParameter];
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else if (value !== undefined && value !== null) {
      input.value = String(value);
    }
  }
  projectPresetName.value = preset.name;
  projectResult.textContent = `Preset caricato: ${preset.name}`;
}

async function openProjectGateway() {
  projectError.textContent = "";
  projectResult.textContent = "Caricamento progetti...";
  try {
    availableProjects = await runtimeClient.listProjects();
    const ready = availableProjects.filter((project) => project.enabled && project.available);
    projectSelect.innerHTML = ready.map((project) => `<option value="${project.id}">${project.name}</option>`).join("");
    if (!ready.length) {
      throw new Error("Nessun progetto configurato e disponibile.");
    }
    renderProjectActions();
    await refreshProjectPresets();
    refreshProjectScheduleDefaults();
    setProjectPanel("output");
    projectResult.textContent = "Seleziona un'azione da eseguire con l'agente corrente.";
    projectDialog.showModal();
    await refreshProjectJobHistory(true);
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "openProjectGateway", agentId: selectedAgentId });
    setBootMessage(error.message);
  }
}

function projectNameFor(job) {
  return availableProjects.find((project) => project.id === job.project_id)?.name ?? job.project_id ?? "Project";
}

function projectActionLabelFor(job) {
  const project = availableProjects.find((item) => item.id === job.project_id);
  return project?.actions?.find((action) => action.id === job.action)?.label ?? job.action ?? "job";
}

function projectAgentLabelFor(job) {
  if (!job.agent_id) {
    return "unassigned";
  }
  return network.getAgent(job.agent_id)?.label ?? job.agent_id;
}

function localDateParts(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return {
    date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    time: `${pad(date.getHours())}:${pad(date.getMinutes())}`,
  };
}

function formatLocalDateTime(date = new Date()) {
  try {
    return new Intl.DateTimeFormat("it-IT", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  } catch (_error) {
    return date.toLocaleString();
  }
}

function updateProjectScheduleHint() {
  if (!projectScheduleHint) {
    return;
  }
  projectScheduleHint.textContent = `Ora locale corrente: ${formatLocalDateTime(new Date())}`;
}

function setProjectScheduleNow() {
  const parts = localDateParts(new Date());
  projectScheduleDate.value = parts.date;
  projectScheduleTime.value = parts.time;
}

function updateProjectScheduleVisibility() {
  const mode = projectScheduleMode.value;
  const atMode = mode === "at";
  const cronMode = mode === "cron";
  projectScheduleDate.hidden = !atMode;
  projectScheduleTime.hidden = !atMode;
  projectScheduleRepeat.hidden = !atMode;
  projectScheduleCron.hidden = !cronMode;
  projectWeekdayPicker.hidden = !(atMode && projectScheduleRepeat.value === "weekdays");
  if (projectScheduleSection) {
    projectScheduleSection.dataset.mode = mode;
  }
  if (projectScheduleNow) {
    projectScheduleNow.textContent = "Usa ora corrente";
  }
}

function refreshProjectScheduleDefaults() {
  updateProjectScheduleHint();
  setProjectScheduleNow();
  projectScheduleMode.value = "immediate";
  projectScheduleRepeat.value = "once";
  projectScheduleCron.value = "";
  clearProjectWeekdays();
  updateProjectScheduleVisibility();
}

function clearProjectWeekdays() {
  projectWeekdayPicker?.querySelectorAll("[data-weekday]").forEach((input) => {
    input.checked = false;
  });
}

function selectedProjectWeekdays() {
  return Array.from(projectWeekdayPicker?.querySelectorAll("[data-weekday]") ?? [])
    .filter((input) => input.checked)
    .map((input) => Number(input.dataset.weekday))
    .filter((value) => Number.isInteger(value));
}

function buildProjectSchedulePayload() {
  const mode = projectScheduleMode.value;
  if (mode === "at") {
    const dateValue = projectScheduleDate.value;
    const timeValue = projectScheduleTime.value;
    if (!dateValue || !timeValue) {
      throw new Error("Inserisci data e ora per la pianificazione.");
    }
    const scheduledDate = new Date(`${dateValue}T${timeValue}:00`);
    if (Number.isNaN(scheduledDate.getTime())) {
      throw new Error("Data o ora non valida.");
    }
    const repeatMode = projectScheduleRepeat.value;
    if (repeatMode === "weekdays" && selectedProjectWeekdays().length === 0) {
      throw new Error("Seleziona almeno un giorno della settimana.");
    }
    return {
      schedule_mode: "at",
      scheduled_for: scheduledDate.toISOString(),
      cron_expression: "",
      repeat_mode: repeatMode,
      weekdays: selectedProjectWeekdays(),
    };
  }
  if (mode === "cron") {
    const expression = projectScheduleCron.value.trim().replace(/\s+/g, " ");
    if (!expression) {
      throw new Error("Inserisci un'espressione cron valida.");
    }
    return {
      schedule_mode: "cron",
      scheduled_for: null,
      cron_expression: expression,
      repeat_mode: "once",
      weekdays: [],
    };
  }
  return {
    schedule_mode: "immediate",
    scheduled_for: null,
    cron_expression: "",
    repeat_mode: "once",
    weekdays: [],
  };
}

function clampText(value, maxLength = 1400) {
  const text = String(value ?? "");
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trimEnd()}\n…`;
}

function formatProjectJobOutput(job) {
  if (!job) {
    return "";
  }
  if (job.state === "failed") {
    return `Errore\n${clampText(job.error || "Job fallito.")}`;
  }
  if (job.state === "scheduled") {
    const planned = {
      state: job.state,
      schedule_mode: job.schedule_mode,
      scheduled_for: job.scheduled_for,
      cron_expression: job.cron_expression,
      repeat_mode: job.repeat_mode,
      weekdays: job.weekdays,
    };
    return clampText(JSON.stringify(planned, null, 2));
  }
  if (job.state === "queued" || job.state === "running") {
    return "Job in corso...";
  }
  const result = job.result ?? {};
  const compact = {};
  if (result.message) compact.message = result.message;
  if (result.command) compact.command = result.command;
  if (result.source) compact.source = result.source;
  if (typeof result.row_count === "number") compact.row_count = result.row_count;
  if (Array.isArray(result.files)) compact.files = result.files;
  if (result.normalized?.meta_summary) compact.meta_summary = result.normalized.meta_summary;
  if (result.normalized?.exported_files) {
    compact.exported_files = result.normalized.exported_files;
    if (Array.isArray(result.normalized.exported_files) && result.normalized.exported_files.length === 0) {
      compact.output_note = "Nessun file esportato";
    }
  }
  if (job.schedule_mode && job.schedule_mode !== "immediate") compact.schedule_mode = job.schedule_mode;
  if (job.scheduled_for) compact.scheduled_for = job.scheduled_for;
  if (job.cron_expression) compact.cron_expression = job.cron_expression;
  if (job.repeat_mode && job.repeat_mode !== "once") compact.repeat_mode = job.repeat_mode;
  if (Array.isArray(job.weekdays) && job.weekdays.length) compact.weekdays = job.weekdays;
  if (!Object.keys(compact).length) {
    return clampText(JSON.stringify(result, null, 2));
  }
  return clampText(JSON.stringify(compact, null, 2));
}

function formatProjectJobSummary(job) {
  if (!job) {
    return "";
  }
  const parts = [];
  const result = job.result ?? {};
  const normalized = result.normalized ?? {};
  const meta = normalized.meta_summary ?? result.meta_summary ?? {};
  const source = result.source ?? job.project_id;
  const command = result.command ?? job.action;
  const rowCount = result.row_count ?? normalized.row_count ?? meta.row_count;
  const exported = normalized.exported_files ?? result.exported_files ?? result.files ?? [];
  const searchTerm = meta.search_term ?? normalized.search_term;
  if (source) parts.push(`source=${source}`);
  if (command) parts.push(`command=${command}`);
  if (searchTerm) parts.push(`search=${searchTerm}`);
  if (typeof rowCount === "number") parts.push(`rows=${rowCount}`);
  if (job.repeat_mode && job.repeat_mode !== "once") parts.push(`repeat=${job.repeat_mode}`);
  if (Array.isArray(job.weekdays) && job.weekdays.length) parts.push(`days=${job.weekdays.join(",")}`);
  if (Array.isArray(exported) && exported.length) parts.push(`files=${exported.length}`);
  return parts.join(" · ");
}

function formatProjectJobTime(job) {
  const value = job?.updated_at || job?.created_at;
  if (!value) {
    return "";
  }
  try {
    return new Intl.DateTimeFormat("it-IT", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch (_error) {
    return String(value);
  }
}

function projectJobSource(job) {
  const result = job?.result ?? {};
  return String(result.source ?? job?.project_id ?? "").toLowerCase();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderProjectOutputSummary(job) {
  if (!projectOutputSummary) {
    return;
  }
  if (!job) {
    projectOutputSummary.textContent = "";
    return;
  }
  const parts = [];
  const result = job.result ?? {};
  const normalized = result.normalized ?? {};
  const meta = normalized.meta_summary ?? result.meta_summary ?? {};
  const source = projectJobSource(job);
  const rowCount = result.row_count ?? normalized.row_count ?? meta.row_count;
  const searchTerm = meta.search_term ?? normalized.search_term ?? result.search_term;
  if (source) parts.push(`source=${source}`);
  if (searchTerm) parts.push(`search=${searchTerm}`);
  if (typeof rowCount === "number") parts.push(`rows=${rowCount}`);
  if (job.state === "scheduled") {
    parts.push(`repeat=${job.repeat_mode ?? "once"}`);
    if (Array.isArray(job.weekdays) && job.weekdays.length) {
      parts.push(`days=${job.weekdays.join(",")}`);
    }
  }
  if (job.schedule_mode && job.schedule_mode !== "immediate") {
    parts.push(`schedule=${job.schedule_mode}`);
  }
  if (job.scheduled_for) {
    parts.push(`run_at=${formatProjectJobTime({ created_at: job.scheduled_for })}`);
  }
  projectOutputSummary.textContent = parts.join(" · ");
}

function clearProjectOutputView() {
  if (projectOutputView) {
    projectOutputView.hidden = true;
  }
  if (projectOutputMeta) {
    projectOutputMeta.textContent = "";
  }
  if (projectOutputHead) {
    projectOutputHead.innerHTML = "";
  }
  if (projectOutputRows) {
    projectOutputRows.innerHTML = "";
  }
}

function isRenderableObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function projectPreviewValueText(value) {
  if (value == null || value === "") {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch (_error) {
    return String(value);
  }
}

function projectPreviewLabel(column) {
  return String(column ?? "").replaceAll("_", " ");
}

function projectPreviewColumnsFromRows(rows) {
  const preferredColumns = ["title", "name", "search_term", "price_text", "price", "shipping_text", "shipping_price", "total_text", "total_price", "link"];
  const extraColumns = [];
  for (const row of rows) {
    if (!isRenderableObject(row)) {
      continue;
    }
    for (const key of Object.keys(row)) {
      if (!preferredColumns.includes(key) && !extraColumns.includes(key)) {
        extraColumns.push(key);
      }
    }
  }
  return preferredColumns.filter((column) => rows.some((row) => isRenderableObject(row) && row[column] !== undefined)).concat(extraColumns.slice(0, 6));
}

function projectPreviewColumnsFromObject(value) {
  if (!isRenderableObject(value)) {
    return [];
  }
  const preferredColumns = ["key", "name", "title", "value", "description", "path", "link", "url", "type"];
  const columns = [];
  for (const key of preferredColumns) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      columns.push(key);
    }
  }
  for (const key of Object.keys(value)) {
    if (!columns.includes(key)) {
      columns.push(key);
    }
  }
  return columns.slice(0, 12);
}

function renderProjectStructuredOutput(job) {
  if (!projectOutputView || !projectOutputRows || !projectOutputMeta || !projectOutputHead) {
    return false;
  }
  const result = job?.result ?? {};
  const normalized = result.normalized ?? {};
  const rowsCandidate = Array.isArray(normalized.rows) ? normalized.rows : Array.isArray(result.rows) ? result.rows : null;
  const filesCandidate = Array.isArray(normalized.exported_files) ? normalized.exported_files : Array.isArray(result.exported_files) ? result.exported_files : Array.isArray(result.files) ? result.files : null;
  const summaryCandidate = normalized.summary ?? result.summary ?? normalized.meta_summary ?? result.meta_summary ?? null;

  let preview = null;
  if (Array.isArray(rowsCandidate) && rowsCandidate.length > 0) {
    preview = { kind: "rows", label: "Risultati", value: rowsCandidate.slice(0, 40), total: rowsCandidate.length };
  } else if (Array.isArray(filesCandidate) && filesCandidate.length) {
    preview = { kind: "list", label: "File", value: filesCandidate.slice(0, 40), total: filesCandidate.length };
  } else if (Array.isArray(rowsCandidate)) {
    preview = { kind: "rows", label: "Risultati", value: rowsCandidate.slice(0, 40), total: rowsCandidate.length };
  } else if (summaryCandidate != null) {
    preview = { kind: "summary", label: "Dettaglio", value: summaryCandidate };
  }

  if (!preview) {
    clearProjectOutputView();
    return false;
  }

  if (preview.kind === "rows") {
    const columns = projectPreviewColumnsFromRows(preview.value);
    if (!columns.length) {
      clearProjectOutputView();
      return false;
    }
    projectOutputHead.innerHTML = columns.map((column) => `<th>${escapeHtml(projectPreviewLabel(column))}</th>`).join("");
    projectOutputMeta.textContent = `Righe mostrate: ${preview.value.length}${preview.total > preview.value.length ? ` di ${preview.total}` : ""}`;
    projectOutputRows.innerHTML = preview.value.length
      ? preview.value.map((row) => {
        if (!isRenderableObject(row)) {
          return `<tr><td colspan="${columns.length}" class="project-output-cell--muted">${escapeHtml(projectPreviewValueText(row))}</td></tr>`;
        }
        const cells = columns.map((column) => {
          const value = row[column];
          if (value == null || value === "") {
            return "<td><span class='project-output-cell--muted'>-</span></td>";
          }
          if (column === "link" || /_link$|url$/i.test(column)) {
            const href = String(value).trim();
            if (!href) {
              return "<td><span class='project-output-cell--muted'>-</span></td>";
            }
            return `<td><a class="project-output-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">Apri</a></td>`;
          }
          return `<td>${escapeHtml(projectPreviewValueText(value))}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("")
      : `<tr><td colspan="${Math.max(columns.length, 1)}" class="project-output-cell--muted">Nessun risultato disponibile.</td></tr>`;
    projectOutputView.hidden = false;
    return true;
  }

  if (preview.kind === "list") {
    projectOutputHead.innerHTML = "<th>#</th><th>Valore</th>";
    projectOutputMeta.textContent = `Elementi mostrati: ${preview.value.length}${preview.total > preview.value.length ? ` di ${preview.total}` : ""}`;
    projectOutputRows.innerHTML = preview.value.length
      ? preview.value.map((item, index) => {
        if (isRenderableObject(item)) {
          const columns = projectPreviewColumnsFromObject(item);
          const value = columns.map((column) => {
            const cellValue = item[column];
            if (cellValue == null || cellValue === "") {
              return `${escapeHtml(projectPreviewLabel(column))}: -`;
            }
            if (column === "link" || /_link$|url$/i.test(column)) {
              const href = String(cellValue).trim();
              return href
                ? `${escapeHtml(projectPreviewLabel(column))}: <a class="project-output-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">Apri</a>`
                : `${escapeHtml(projectPreviewLabel(column))}: -`;
            }
            return `${escapeHtml(projectPreviewLabel(column))}: ${escapeHtml(projectPreviewValueText(cellValue))}`;
          }).join("<br>");
          return `<tr><td>${index + 1}</td><td>${value}</td></tr>`;
        }
        return `<tr><td>${index + 1}</td><td>${escapeHtml(projectPreviewValueText(item))}</td></tr>`;
      }).join("")
      : '<tr><td colspan="2" class="project-output-cell--muted">Nessun elemento disponibile.</td></tr>';
    projectOutputView.hidden = false;
    return true;
  }

  projectOutputHead.innerHTML = "<th>Campo</th><th>Valore</th>";
  projectOutputMeta.textContent = "Dettaglio output";
  const entries = isRenderableObject(preview.value) ? Object.entries(preview.value).slice(0, 40) : [["value", preview.value]];
  projectOutputRows.innerHTML = entries.length
    ? entries.map(([key, value]) => {
      const renderedValue = Array.isArray(value)
        ? value.map((item) => projectPreviewValueText(item)).join(", ")
        : projectPreviewValueText(value);
      return `<tr><td>${escapeHtml(projectPreviewLabel(key))}</td><td>${escapeHtml(renderedValue)}</td></tr>`;
    }).join("")
    : '<tr><td colspan="2" class="project-output-cell--muted">Nessun dettaglio disponibile.</td></tr>';
  projectOutputView.hidden = false;
  return true;
}

function renderProjectJobDetail(job) {
  renderProjectOutputSummary(job);
  if (renderProjectStructuredOutput(job)) {
    projectResult.hidden = true;
    projectResult.textContent = formatProjectJobOutput(job);
    return;
  }
  clearProjectOutputView();
  projectResult.hidden = false;
  projectResult.textContent = formatProjectJobOutput(job);
}

function jobToastStatus(job) {
  if (!job) {
    return "";
  }
  if (job.state === "queued") return "In coda";
  if (job.state === "running") return "In corso";
  if (job.state === "scheduled") return "Pianificato";
  if (job.state === "completed") return "Completato";
  if (job.state === "failed") return "Fallito";
  return String(job.state || "");
}

function jobToastTone(job) {
  if (!job) {
    return "neutral";
  }
  if (job.state === "completed") return "success";
  if (job.state === "failed") return "danger";
  if (job.state === "running" || job.state === "queued" || job.state === "scheduled") return "active";
  return "neutral";
}

function ensureProjectJobToast(job) {
  if (!job || !job.id) {
    return null;
  }
  let toast = projectJobToasts.get(job.id);
  if (toast) {
    return toast;
  }

  const card = document.createElement("article");
  card.className = "job-toast";
  card.dataset.jobId = job.id;
  card.innerHTML = `
    <div class="job-toast__header">
      <div class="job-toast__title">
        <strong></strong>
        <span></span>
      </div>
      <div class="job-toast__meta">
        <span class="job-toast__status"></span>
        <button type="button" aria-label="Chiudi job">x</button>
      </div>
    </div>
    <p class="job-toast__summary"></p>
    <pre class="job-toast__output"></pre>
  `;
  const dismissButton = card.querySelector("button");
  const summary = card.querySelector(".job-toast__summary");
  const output = card.querySelector(".job-toast__output");
  const title = card.querySelector(".job-toast__title strong");
  const subtitle = card.querySelector(".job-toast__title span");
  const status = card.querySelector(".job-toast__status");
  dismissButton.addEventListener("click", () => {
    card.remove();
    projectJobToasts.delete(job.id);
  });

  toast = { card, summary, output, title, subtitle, status };
  projectJobToasts.set(job.id, toast);
  jobToastStack.prepend(card);
  return toast;
}

function syncProjectJobToast(job, phase = "") {
  if (!job || !job.id) {
    return;
  }
  const toast = ensureProjectJobToast(job);
  if (!toast) {
    return;
  }
  const titleText = `${projectNameFor(job)} · ${projectActionLabelFor(job)}`;
  const subtitleText = `Agente: ${projectAgentLabelFor(job)} · ID: ${job.id}`;
  const summaryText = phase === "project.job.queued"
    ? "Job ricevuto e messo in coda."
    : phase === "project.job.scheduled"
      ? "Job pianificato per l'orario scelto."
    : phase === "project.job.started"
      ? "Job avviato."
      : job.state === "scheduled"
        ? "In attesa dell'orario scelto."
      : job.state === "completed"
        ? "Output finale."
        : job.state === "failed"
          ? "Esecuzione fallita."
          : "Job aggiornato.";

  toast.card.classList.toggle("job-toast--active", job.state === "queued" || job.state === "running" || job.state === "scheduled");
  toast.card.classList.toggle("job-toast--success", job.state === "completed");
  toast.card.classList.toggle("job-toast--danger", job.state === "failed");
  toast.title.textContent = titleText;
  toast.subtitle.textContent = subtitleText;
  toast.status.textContent = jobToastStatus(job);
  toast.status.dataset.tone = jobToastTone(job);
  toast.summary.textContent = summaryText;
  toast.output.textContent = formatProjectJobOutput(job);
}

async function refreshProjectJobToasts() {
  if (!runtimeClient.connected) {
    return;
  }
  try {
    const jobs = await runtimeClient.listProjectJobs();
    for (const job of jobs.filter((item) => ["scheduled", "queued", "running"].includes(item.state))) {
      syncProjectJobToast(job);
    }
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "refreshProjectJobToasts" });
  }
}

function setProjectPanel(panel) {
  projectPanel = panel === "finished" ? "finished" : "output";
  for (const tab of projectPanelTabs) {
    const active = tab.dataset.panelTab === projectPanel;
    tab.classList.toggle("project-panel-tab--active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const pane of projectPanels) {
    pane.hidden = pane.dataset.projectPanel !== projectPanel;
  }
  if (projectPanel === "finished") {
    unreadCompletedProjectJobs = 0;
    renderJobNotificationBadge();
    refreshProjectJobHistory(true);
  }
}

function renderJobNotificationBadge() {
  if (!jobNotificationCount) {
    return;
  }
  if (unreadCompletedProjectJobs > 0) {
    jobNotificationCount.hidden = false;
    jobNotificationCount.textContent = unreadCompletedProjectJobs > 99 ? "99+" : String(unreadCompletedProjectJobs);
    jobNotificationsButton?.classList.add("is-pulse");
    window.setTimeout(() => jobNotificationsButton?.classList.remove("is-pulse"), 900);
    return;
  }
  jobNotificationCount.hidden = true;
  jobNotificationCount.textContent = "0";
}

function acknowledgeCompletedJobs(jobIds = []) {
  for (const jobId of jobIds) {
    seenCompletedProjectJobs.add(jobId);
  }
  unreadCompletedProjectJobs = 0;
  renderJobNotificationBadge();
}

function markCompletedJobUnread(jobId) {
  if (!jobId || seenCompletedProjectJobs.has(jobId)) {
    return;
  }
  seenCompletedProjectJobs.add(jobId);
  unreadCompletedProjectJobs += 1;
  renderJobNotificationBadge();
}

function projectJobsForHistory(jobs) {
  const currentProjectId = projectSelect.value;
  return jobs
    .filter((job) => job.state === "completed" || job.state === "failed")
    .filter((job) => !currentProjectId || job.project_id === currentProjectId)
    .sort((left, right) => String(right.updated_at ?? right.created_at).localeCompare(String(left.updated_at ?? left.created_at)));
}

function renderProjectJobHistory(jobs) {
  if (!projectJobList) {
    return;
  }
  projectJobsCache.clear();
  for (const job of jobs) {
    projectJobsCache.set(job.id, job);
  }
  if (!jobs.length) {
    projectJobList.innerHTML = '<p class="project-job-empty">Nessun job finito per questo progetto.</p>';
    return;
  }
  projectJobList.innerHTML = jobs
    .map((job) => {
      const tone = job.state === "failed" ? "project-job-item--failed" : "project-job-item--completed";
      const summary = formatProjectJobSummary(job);
      const time = formatProjectJobTime(job);
      return `
        <button class="project-job-item ${tone}" type="button" data-job-id="${job.id}">
          <strong>${projectNameFor(job)} · ${projectActionLabelFor(job)}</strong>
          <small>${projectAgentLabelFor(job)} · ${jobToastStatus(job)}${time ? ` · ${time}` : ""}</small>
          <small>${summary || job.id}</small>
        </button>
      `;
    })
    .join("");
  projectJobList.querySelectorAll("[data-job-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const job = projectJobsCache.get(button.dataset.jobId);
      if (job) {
        openJobOutput(job);
      }
    });
  });
}

async function refreshProjectJobHistory(markSeen = false) {
  if (!runtimeClient.connected) {
    return;
  }
  try {
    const jobs = await runtimeClient.listProjectJobs();
    const filtered = projectJobsForHistory(jobs);
    renderProjectJobHistory(filtered);
    if (markSeen) {
      acknowledgeCompletedJobs(filtered.map((job) => job.id));
    }
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "refreshProjectJobHistory" });
  }
}

function openJobOutput(job) {
  if (!job) {
    return;
  }
  setProjectPanel("output");
  if (!projectDialog.open) {
    projectDialog.showModal();
  }
  renderProjectJobDetail(job);
}

function openAgentActions(agentId) {
  const agent = network.getAgent(agentId);
  if (!agent) {
    return;
  }
  agentActionTitle.textContent = agent.label;
  agentActionRole.textContent = agent.role;
  agentActionStatus.textContent = agent.runtime.status;
  workOptions.hidden = true;
  if (!agentActionDialog.open) {
    agentActionDialog.showModal();
  }
}

function setRuntimeConnection(connected) {
  runtimeStatus.textContent = connected ? "Runtime live" : "Offline demo";
  runtimeStatus.classList.toggle("live-status--connecting", false);
  runtimeStatus.classList.toggle("live-status--offline", !connected);
}

async function connectRuntime() {
  runtimeClient.onEvent(handleRuntimeEvent);
  try {
    await runtimeClient.connect();
    network.autopilotClock = Number.POSITIVE_INFINITY;
    setRuntimeConnection(true);
    await refreshProjectJobToasts();
    await refreshProjectJobHistory(true);
  } catch (error) {
    setRuntimeConnection(false);
    setBootMessage(error.message);
  }
}

function splitValues(value) {
  return value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function slugify(value) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40);
}

function settingsField(name) {
  return agentSettingsForm.elements.namedItem(name);
}

function modelPickerField() {
  return settingsField("model_picker");
}

function modelInputField() {
  return settingsField("model");
}

function renderSecretStatus(status) {
  projectKeyStatus.textContent = `Progetto: ${status.project_configured ? "configurata" : "non configurata"}`;
  agentKeyStatus.textContent = `Agente: ${status.agent_configured ? "configurata" : "non configurata"}`;
  projectKeyStatus.classList.toggle("secret-status--configured", status.project_configured);
  agentKeyStatus.classList.toggle("secret-status--configured", status.agent_configured);
}

function renderModelPicker(provider, selectedModel = "") {
  const picker = modelPickerField();
  const modelInput = modelInputField();
  const help = document.querySelector("#model-help");
  const catalog = MODEL_CATALOGS[provider] ?? [];
  picker.innerHTML = "";

  if (!catalog.length) {
    picker.disabled = true;
    picker.hidden = true;
    modelInput.hidden = false;
    modelInput.placeholder = provider === "ollama" ? "llama3.2" : "model-id";
    help.textContent = provider === "openai-compatible"
      ? "Enter the exact model ID exposed by your compatible endpoint."
      : "Enter the exact model ID for this provider.";
    modelInput.value = selectedModel;
    return;
  }

  picker.disabled = false;
  picker.hidden = false;
  modelInput.placeholder = "Custom model ID";

  for (const entry of catalog) {
    if (entry.group) {
      const group = document.createElement("optgroup");
      group.label = entry.group;
      for (const optionData of entry.options) {
        const option = document.createElement("option");
        option.value = optionData.value;
        option.textContent = optionData.label;
        group.append(option);
      }
      picker.append(group);
      continue;
    }
    const option = document.createElement("option");
    option.value = entry.value;
    option.textContent = entry.label;
    picker.append(option);
  }

  const customOption = document.createElement("option");
  customOption.value = MODEL_PICKER_CUSTOM;
  customOption.textContent = "Custom model ID";
  picker.append(customOption);

  const knownModels = new Set(
    catalog.flatMap((entry) => entry.group ? entry.options.map((option) => option.value) : [entry.value])
  );
  const usingCustom = !selectedModel || !knownModels.has(selectedModel);
  picker.value = usingCustom ? MODEL_PICKER_CUSTOM : selectedModel;
  modelInput.hidden = !usingCustom;
  modelInput.value = usingCustom ? selectedModel : picker.value;
  help.textContent = provider === "openai"
    ? "Official OpenAI models as of July 8, 2026, plus custom ID support."
    : "Select a built-in model or switch to a custom model ID.";
}

function syncModelFieldFromPicker() {
  const picker = modelPickerField();
  const modelInput = modelInputField();
  if (picker.hidden) {
    return;
  }
  if (picker.value === MODEL_PICKER_CUSTOM) {
    modelInput.hidden = false;
    if (!modelInput.value) {
      modelInput.value = "";
    }
    modelInput.focus();
    return;
  }
  modelInput.hidden = true;
  modelInput.value = picker.value;
}

function updateProviderControls(resetDefaults = false) {
  const provider = settingsField("provider").value;
  const defaults = providerDefaults[provider];
  const currentModel = modelInputField().value;
  if (resetDefaults && defaults) {
    modelInputField().value = defaults.model;
    settingsField("base_url").value = defaults.baseUrl;
  }
  renderModelPicker(provider, resetDefaults && defaults ? defaults.model : currentModel);
  syncModelFieldFromPicker();
  const usesLocalRuntime = provider === "ollama";
  settingsField("api_key").disabled = usesLocalRuntime;
  settingsField("api_key_scope").disabled = usesLocalRuntime;
}

async function openAgentSettings() {
  if (!runtimeClient.connected) {
    setBootMessage("Start the project with run.command to edit persistent agent settings.");
    return;
  }
  const snapshot = runtimeSnapshots.get(selectedAgentId);
  if (!snapshot) {
    setBootMessage("The selected object is not registered in the runtime yet.");
    return;
  }
  agentSettingsError.textContent = "";
  document.querySelector("#agent-settings-title").textContent = `${snapshot.name} settings`;
  settingsField("id").value = snapshot.id;
  settingsField("name").value = snapshot.name;
  settingsField("role").value = snapshot.role;
  settingsField("color").value = snapshot.color;
  settingsField("instructions").value = snapshot.instructions ?? "";
  settingsField("capabilities").value = snapshot.capabilities.join(", ");
  settingsField("protocols").value = snapshot.protocols.join(", ");
  settingsField("provider").value = snapshot.model.provider;
  settingsField("model").value = snapshot.model.model;
  settingsField("base_url").value = snapshot.model.base_url;
  settingsField("api_key_env").value = snapshot.model.api_key_env;
  settingsField("api_key_scope").value = snapshot.model.api_key_scope ?? "project";
  settingsField("api_key").value = "";
  updateProviderControls(false);
  settingsField("temperature").value = snapshot.model.temperature;
  settingsField("toolsets").value = snapshot.toolsets.join(", ");
  settingsField("max_iterations").value = snapshot.limits.max_iterations;
  settingsField("timeout_seconds").value = snapshot.limits.timeout_seconds;
  settingsField("max_parallel_tasks").value = snapshot.limits.max_parallel_tasks;
  settingsField("approvals").value = snapshot.approvals.required_for.join(", ");
  settingsField("memory").value = "Loading memory…";
  settingsField("wiki").value = "Loading wiki…";
  agentSettingsDialog.showModal();
  try {
    const [memory, wiki, secretStatus] = await Promise.all([
      runtimeClient.getAgentMemory(snapshot.id),
      runtimeClient.getAgentWiki(snapshot.id),
      runtimeClient.getSecretStatus(snapshot.id),
    ]);
    settingsField("memory").value = memory.content;
    settingsField("wiki").value = wiki.content;
    renderSecretStatus(secretStatus);
  } catch (error) {
    settingsField("memory").value = "";
    settingsField("wiki").value = "";
    agentSettingsError.textContent = error.message;
  }
}

function setPointerNdc(event) {
  const rect = canvas.getBoundingClientRect();
  pointerNdc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointerNdc.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
}

function objectFromPointer(event) {
  setPointerNdc(event);
  raycaster.setFromCamera(pointerNdc, camera);
  const hits = raycaster.intersectObjects(selectableObjects, true);
  return hits.find(
    (item) => item.object.userData.agentId || item.object.userData.stationId || item.object.userData.tile
  );
}

function selectFromPointer(event) {
  const hit = objectFromPointer(event);
  if (!hit) {
    if (!layoutMode) {
      selectedStationId = null;
      closeQuickChat();
    }
    updateHud();
    return;
  }

  const agentId = hit.object.userData.agentId;
  const stationId = hit.object.userData.stationId;
  const tile = hit.object.userData.tile;
  const editorTile = hit.object.userData.editorTile;
  if (layoutMode) {
    if (tile && roomDrawMode) {
      toggleSelectedRoomCell(tile);
    } else if (tile && doorMode) {
      toggleDoorCell(tile);
    } else if (agentId) {
      selectedAgentId = agentId;
      selectedStationId = null;
      selectedRoomId = roomForTile(agentWorld.getAgentState(agentId)?.tile)?.id ?? selectedRoomId;
      closeQuickChat();
      setBootMessage(`Editor: ${network.getAgent(agentId)?.label ?? agentId} selezionato. Clicca un tile per spostarlo.`);
    } else if (stationId) {
      selectedStationId = stationId;
      selectedRoomId = roomForTile(worldToTile(agentWorld.getStation(stationId)?.position ?? { x: 0, z: 0 }))?.id ?? selectedRoomId;
      closeQuickChat();
      setBootMessage(`Editor: ${agentWorld.getStation(stationId)?.label ?? stationId} selezionato. Clicca un tile per spostarlo.`);
    } else if (tile) {
      selectedRoomId = roomForTile(tile)?.id ?? selectedRoomId;
      if (selectedStationId) {
        const moved = agentWorld.commandMoveStation(selectedStationId, tile);
        if (moved) {
          moveStationVisual(selectedStationId);
          saveLayoutState();
          setBootMessage(`${agentWorld.getStation(selectedStationId)?.label ?? "Tavolo"} spostato.`);
        } else {
          setBootMessage("Quel tile non e disponibile per il tavolo selezionato.");
        }
      } else if (selectedAgentId) {
        const moved = agentWorld.commandPlaceAgent(selectedAgentId, tile, "layout move");
        if (moved) {
          setAutoAgents(false);
          saveLayoutState();
          setBootMessage(`${network.getAgent(selectedAgentId)?.label ?? "Agente"} spostato.`);
        } else {
          setBootMessage("Quel tile non e disponibile per l'agente selezionato.");
        }
      }
    }
    updateHud();
    return;
  }

  if (editorTile && tile && !isInsideTile(tile)) {
    selectedStationId = null;
    closeQuickChat();
    updateHud();
    return;
  }

  if (agentId) {
    selectedAgentId = agentId;
    selectedStationId = null;
    selectedRoomId = roomForTile(agentWorld.getAgentState(agentId)?.tile)?.id ?? selectedRoomId;
    openQuickChat(agentId);
  } else if (stationId) {
    selectedStationId = stationId;
    selectedRoomId = roomForTile(worldToTile(agentWorld.getStation(stationId)?.position ?? { x: 0, z: 0 }))?.id ?? selectedRoomId;
    closeQuickChat();
  } else if (tile) {
    selectedStationId = null;
    selectedRoomId = roomForTile(tile)?.id ?? selectedRoomId;
    closeQuickChat();
    const moved = agentWorld.commandMoveAgent(selectedAgentId, tile, "manual move");
    if (moved) {
      setAutoAgents(false);
      saveLayoutState();
    }
  }
  updateHud();
}

function panCamera(dx, dy) {
  const scale = cameraZoom / Math.max(window.innerHeight, 1) * 1.45;
  const right = new THREE.Vector3(Math.cos(cameraYaw), 0, -Math.sin(cameraYaw));
  const forward = new THREE.Vector3(Math.sin(cameraYaw), 0, Math.cos(cameraYaw));
  cameraTarget.addScaledVector(right, -dx * scale);
  cameraTarget.addScaledVector(forward, -dy * scale);
  cameraTarget.x = Math.max(-roomConfig.width / 2, Math.min(roomConfig.width / 2, cameraTarget.x));
  cameraTarget.z = Math.max(-roomConfig.depth / 2, Math.min(roomConfig.depth / 2, cameraTarget.z));
  updateCamera();
}

canvas.addEventListener("pointerdown", (event) => {
  pointerState.x = event.clientX;
  pointerState.y = event.clientY;
  pointerState.startX = event.clientX;
  pointerState.startY = event.clientY;
  pointerState.dragging = true;
  pointerState.panning = false;
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", (event) => {
  if (!pointerState.dragging) {
    return;
  }
  const dx = event.clientX - pointerState.x;
  const dy = event.clientY - pointerState.y;
  const total = Math.hypot(event.clientX - pointerState.startX, event.clientY - pointerState.startY);
  if (total > 5) {
    pointerState.panning = true;
  }
  if (pointerState.panning) {
    panCamera(dx, dy);
  }
  pointerState.x = event.clientX;
  pointerState.y = event.clientY;
});

canvas.addEventListener("pointerup", (event) => {
  if (!pointerState.panning) {
    selectFromPointer(event);
  }
  pointerState.dragging = false;
  pointerState.panning = false;
});

canvas.addEventListener("wheel", (event) => {
  event.preventDefault();
  cameraZoom = Math.max(5.2, Math.min(11.5, cameraZoom + Math.sign(event.deltaY) * 0.45));
  updateCamera();
}, { passive: false });

window.addEventListener("keydown", (event) => {
  const editing = event.target instanceof HTMLElement && event.target.matches("input, textarea, select");
  if (editing && event.code !== "Escape") {
    return;
  }
  if (event.code === "Escape" && quickChatAgentId) {
    closeQuickChat();
  } else if (event.code === "Escape" && layoutMode) {
    setLayoutMode(false);
  } else if (event.code === "Space") {
    event.preventDefault();
    setRunning(!running);
  } else if (event.code === "KeyQ") {
    cameraYaw -= Math.PI / 12;
    updateCamera();
  } else if (event.code === "KeyE") {
    cameraYaw += Math.PI / 12;
    updateCamera();
  } else if (event.code === "KeyL") {
    setLayoutMode(!layoutMode);
  } else if (event.code === "KeyT") {
    applyTheme(currentTheme === "light" ? "dark" : "light");
  } else if (event.code === "KeyR" && layoutMode) {
    addLayoutRoom();
  } else if (event.code === "Digit1") {
    triggerIntent("task");
  } else if (event.code === "Digit2") {
    triggerIntent("schedule");
  } else if (event.code === "Digit3") {
    triggerIntent("memory-sync");
  } else if (event.code === "Digit4") {
    triggerIntent("review");
  }
});

runToggle.addEventListener("click", () => setRunning(!running));
autoToggle.addEventListener("click", () => setAutoAgents(!autoAgents));
layoutToggle?.addEventListener("click", () => setLayoutMode(!layoutMode));
editorCloseButton?.addEventListener("click", () => setLayoutMode(false));
roomDrawToggle?.addEventListener("click", () => setRoomDrawMode(!roomDrawMode));
doorToggle?.addEventListener("click", () => setDoorMode(!doorMode));
addRoomButton?.addEventListener("click", addLayoutRoom);
deleteRoomButton?.addEventListener("click", deleteSelectedRoom);
resetLayoutButton?.addEventListener("click", resetSavedLayout);
themeToggle?.addEventListener("click", () => applyTheme(currentTheme === "light" ? "dark" : "light"));
speedControl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-speed]");
  if (button) {
    setSpeed(Number(button.dataset.speed));
  }
});
cameraLeft.addEventListener("click", () => {
  cameraYaw -= Math.PI / 12;
  updateCamera();
});
cameraRight.addEventListener("click", () => {
  cameraYaw += Math.PI / 12;
  updateCamera();
});
document.querySelector("#intent-task").addEventListener("click", () => triggerIntent("task"));
document.querySelector("#intent-schedule").addEventListener("click", () => triggerIntent("schedule"));
document.querySelector("#intent-memory").addEventListener("click", () => triggerIntent("memory-sync"));
document.querySelector("#intent-review").addEventListener("click", () => triggerIntent("review"));
stationList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-station]");
  if (!button) {
    return;
  }
  selectedStationId = button.dataset.station;
  const station = agentWorld.getStation(selectedStationId);
  if (station) {
    selectedRoomId = roomForTile(worldToTile(station.position))?.id ?? selectedRoomId;
    cameraTarget.set(station.position.x, 0, station.position.z);
    updateCamera();
    if (layoutMode) {
      setBootMessage(`Editor: ${station.label} selezionato. Clicca un tile per spostarlo.`);
    }
  }
  updateHud();
});

roomList?.addEventListener("click", (event) => {
  const placeButton = event.target.closest("[data-room-place]");
  if (placeButton) {
    placeSelectionInRoom(placeButton.dataset.roomPlace);
    return;
  }
  const roomButton = event.target.closest("[data-room]");
  if (!roomButton) {
    return;
  }
  const room = roomLayout.find((item) => item.id === roomButton.dataset.room);
  if (!room) {
    return;
  }
  selectedRoomId = room.id;
  focusRoom(room);
  if (layoutMode) {
    setBootMessage(`Editor: ${room.label} selezionata. Usa "Porta qui" o i controlli stanza/porte.`);
  }
  updateHud();
});

addAgentButton.addEventListener("click", () => {
  agentFormError.textContent = "";
  if (!runtimeClient.connected) {
    setBootMessage("Start the project with run.command to create persistent agents.");
    return;
  }
  agentDialog.showModal();
});

canvas.addEventListener("dblclick", (event) => {
  const hit = objectFromPointer(event);
  const agentId = hit?.object.userData.agentId;
  if (!agentId) {
    return;
  }
  selectedAgentId = agentId;
  selectedStationId = null;
  closeQuickChat();
  updateHud();
  openAgentActions(agentId);
});

document.querySelector("#close-quick-chat").addEventListener("click", closeQuickChat);

quickChat.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = quickChatInput.value.trim();
  const agentId = quickChatAgentId;
  if (!message || !agentId) {
    return;
  }
  if (!runtimeClient.connected) {
    quickChatStatus.textContent = "Runtime offline.";
    return;
  }
  const submitButton = quickChat.querySelector('[type="submit"]');
  submitButton.disabled = true;
  quickChatStatus.textContent = "Assegnazione...";
  quickChatStatus.classList.remove("agent-quick-chat__status--error");
  try {
    const task = await runtimeClient.createTask({
      title: message.slice(0, 160),
      description: message,
      priority: 3,
      requested_agent_id: agentId,
      channel: "chat",
    });
    appendChatMessage({
      id: `${task.id}-user`,
      role: "user",
      content: message,
      sources: [],
    });
    const state = agentWorld.getAgentState(agentId);
    if (state) {
      state.bubble = message.slice(0, 34);
    }
    quickChatInput.value = "";
    quickChatStatus.textContent = `Assegnato: ${task.id}`;
  } catch (error) {
    quickChatStatus.textContent = error.message;
    quickChatStatus.classList.add("agent-quick-chat__status--error");
    runtimeClient.logClient("error", error.message, { operation: "quickChat", agentId });
  } finally {
    submitButton.disabled = false;
    quickChatInput.focus();
  }
});

agentActionDialog.querySelectorAll("[data-agent-action-close]").forEach((button) => {
  button.addEventListener("click", () => agentActionDialog.close());
});
document.querySelector("#assign-work").addEventListener("click", () => {
  workOptions.hidden = false;
});
document.querySelector("#action-configure-agent").addEventListener("click", () => {
  agentActionDialog.close();
  openAgentSettings();
});
document.querySelector("#work-projects").addEventListener("click", () => {
  agentActionDialog.close();
  openProjectGateway();
});
document.querySelector("#work-internal-task").addEventListener("click", () => {
  agentActionDialog.close();
  triggerIntent("task");
});
projectSelect.addEventListener("change", async () => {
  renderProjectActions();
  projectPresetName.value = "";
  try {
    await refreshProjectPresets();
    await refreshProjectJobHistory(true);
  } catch (error) {
    projectError.textContent = error.message;
  }
});
projectAction.addEventListener("change", renderProjectParameters);
document.querySelector("#load-project-preset").addEventListener("click", loadSelectedProjectPreset);
projectPresetSelect.addEventListener("change", loadSelectedProjectPreset);
projectScheduleMode.addEventListener("change", () => {
  updateProjectScheduleVisibility();
  updateProjectScheduleHint();
});
projectScheduleRepeat.addEventListener("change", () => {
  updateProjectScheduleVisibility();
});
projectScheduleNow.addEventListener("click", () => {
  projectScheduleMode.value = "at";
  setProjectScheduleNow();
  updateProjectScheduleVisibility();
  updateProjectScheduleHint();
});
projectWeekdayPicker?.querySelectorAll("[data-weekday]").forEach((input) => {
  input.addEventListener("change", () => {
    if (projectScheduleRepeat.value === "weekdays" && !selectedProjectWeekdays().length) {
      input.checked = true;
    }
  });
});
projectPanelTabs.forEach((button) => {
  button.addEventListener("click", () => setProjectPanel(button.dataset.panelTab));
});
jobNotificationsButton?.addEventListener("click", async () => {
  if (!projectDialog.open) {
    await openProjectGateway();
    if (!projectDialog.open) {
      return;
    }
  }
  setProjectPanel("finished");
});

document.querySelector("#save-project-preset").addEventListener("click", async () => {
  const name = projectPresetName.value.trim();
  projectError.textContent = "";
  if (name.length < 2) {
    projectError.textContent = "Inserisci un nome per il preset.";
    return;
  }
  try {
    const preset = await runtimeClient.createProjectPreset({
      name,
      project_id: projectSelect.value,
      action: projectAction.value,
      parameters: readProjectParameters(),
    });
    await refreshProjectPresets(preset.id);
    projectResult.textContent = `Preset salvato: ${preset.name}`;
  } catch (error) {
    projectError.textContent = error.message;
  }
});

document.querySelector("#delete-project-preset").addEventListener("click", async () => {
  const preset = availableProjectPresets.find((item) => item.id === projectPresetSelect.value);
  if (!preset || !window.confirm(`Eliminare il preset "${preset.name}"?`)) {
    return;
  }
  projectError.textContent = "";
  try {
    await runtimeClient.deleteProjectPreset(preset.id);
    await refreshProjectPresets();
    projectPresetName.value = "";
    projectResult.textContent = `Preset eliminato: ${preset.name}`;
  } catch (error) {
    projectError.textContent = error.message;
  }
});
projectDialog.querySelectorAll("[data-project-close]").forEach((button) => {
  button.addEventListener("click", () => projectDialog.close());
});

projectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = selectedProjectAction();
  if (!action) {
    return;
  }
  const parameters = readProjectParameters();
  const runButton = document.querySelector("#run-project-action");
  runButton.disabled = true;
  projectError.textContent = "";
  projectResult.textContent = "Avvio in corso...";
  try {
    const schedule = buildProjectSchedulePayload();
    const job = await runtimeClient.createProjectJob({
      project_id: projectSelect.value,
      action: action.id,
      parameters,
      agent_id: selectedAgentId,
      approved: projectForm.elements.namedItem("approved").checked,
      ...schedule,
    });
    renderProjectJobDetail(job);
    syncProjectJobToast(job, job.state === "scheduled" ? "project.job.scheduled" : "project.job.queued");
    if (job.state === "scheduled") {
      setProjectPanel("output");
    }
  } catch (error) {
    runtimeClient.logClient("error", error.message, {
      operation: "createProjectJob",
      projectId: projectSelect.value,
      action: action.id,
      agentId: selectedAgentId,
    });
    projectError.textContent = error.message;
    projectResult.textContent = "Esecuzione non avviata.";
  } finally {
    runButton.disabled = false;
  }
});

agentDialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
  button.addEventListener("click", () => agentDialog.close());
});

agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(agentForm);
  const name = String(formData.get("name") ?? "").trim();
  const capabilities = splitValues(String(formData.get("capabilities") ?? ""));
  const createButton = document.querySelector("#create-agent");
  createButton.disabled = true;
  agentFormError.textContent = "";
  try {
    await runtimeClient.createAgent({
      id: `${slugify(name)}-${Date.now().toString(36).slice(-4)}`,
      name,
      role: String(formData.get("role") ?? "specialist"),
      color: String(formData.get("color") ?? "#5ee7f2"),
      capabilities,
      toolsets: splitValues(String(formData.get("toolsets") ?? "")),
      protocols: ["agent-lifecycle", "task-contract"],
      memory_scope: "agent",
    });
    agentForm.reset();
    agentDialog.close();
  } catch (error) {
    agentFormError.textContent = error.message;
  } finally {
    createButton.disabled = false;
  }
});

configureAgentButton.addEventListener("click", openAgentSettings);

agentSettingsDialog.querySelectorAll("[data-settings-close]").forEach((button) => {
  button.addEventListener("click", () => agentSettingsDialog.close());
});

agentSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncModelFieldFromPicker();
  const snapshot = runtimeSnapshots.get(selectedAgentId);
  if (!snapshot) {
    agentSettingsError.textContent = "Selected agent is not available.";
    return;
  }
  const saveButton = document.querySelector("#save-agent-settings");
  saveButton.disabled = true;
  agentSettingsError.textContent = "";
  const value = (name) => String(settingsField(name).value ?? "").trim();
  try {
    await runtimeClient.updateAgent(snapshot.id, {
      id: snapshot.id,
      name: value("name"),
      role: value("role"),
      color: value("color"),
      capabilities: splitValues(value("capabilities")),
      toolsets: splitValues(value("toolsets")),
      protocols: splitValues(value("protocols")),
      instructions: value("instructions"),
      model: {
        provider: value("provider"),
        model: value("model"),
        base_url: value("base_url"),
        api_key_env: value("api_key_env").toUpperCase(),
        api_key_scope: value("api_key_scope"),
        temperature: Number(value("temperature")),
      },
      memory_scope: snapshot.memory_scope,
      limits: {
        max_iterations: Number(value("max_iterations")),
        timeout_seconds: Number(value("timeout_seconds")),
        max_parallel_tasks: Number(value("max_parallel_tasks")),
      },
      approvals: {
        required_for: splitValues(value("approvals")),
      },
    });
    const apiKey = value("api_key");
    if (apiKey) {
      if (value("api_key_scope") === "agent") {
        await runtimeClient.setAgentSecret(snapshot.id, apiKey);
      } else {
        await runtimeClient.setProjectSecret(apiKey);
      }
      settingsField("api_key").value = "";
    }
    await runtimeClient.updateAgentMemory(snapshot.id, value("memory"));
    await runtimeClient.updateAgentWiki(snapshot.id, value("wiki"));
    agentSettingsDialog.close();
  } catch (error) {
    agentSettingsError.textContent = error.message;
  } finally {
    saveButton.disabled = false;
  }
});

settingsField("provider").addEventListener("change", () => {
  updateProviderControls(true);
});

modelPickerField().addEventListener("change", () => {
  syncModelFieldFromPicker();
});

document.querySelector("#delete-api-key").addEventListener("click", async () => {
  const snapshot = runtimeSnapshots.get(selectedAgentId);
  if (!snapshot) {
    return;
  }
  const scope = String(settingsField("api_key_scope").value);
  agentSettingsError.textContent = "";
  try {
    const status = scope === "agent"
      ? await runtimeClient.deleteAgentSecret(snapshot.id)
      : await runtimeClient.deleteProjectSecret();
    settingsField("api_key").value = "";
    renderSecretStatus(status);
  } catch (error) {
    agentSettingsError.textContent = error.message;
  }
});

window.addEventListener("resize", resize);
window.addEventListener("error", (event) => {
  runtimeClient.logClient("error", event.message || "Unhandled browser error", {
    source: event.filename,
    line: event.lineno,
    column: event.colno,
  });
});
window.addEventListener("unhandledrejection", (event) => {
  runtimeClient.logClient("error", event.reason?.message ?? String(event.reason), {
    operation: "unhandledrejection",
  });
});

applyTheme(currentTheme, { persist: false });
buildScene();
resize();
setSpeed(1);
setAutoAgents(true);
setBootMessage("");
window.__agentLabBooted = true;
connectRuntime();
requestAnimationFrame(animate);
