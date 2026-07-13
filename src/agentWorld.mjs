export const roomConfig = {
  width: 24,
  depth: 18,
  columns: 24,
  rows: 18,
  cellSize: 1,
  blockHeight: 0.22,
};

const defaultRoomLayout = [
  {
    id: "main",
    label: "Main Room",
    col: 5,
    row: 4,
    columns: 14,
    rows: 10,
    color: "#1f8d6a",
  },
];

export const roomLayout = defaultRoomLayout.map((room) => ({ ...room }));
export const doorLayout = [];

export const workstationPresets = [
  {
    id: "desk",
    label: "Agent Desk",
    role: "specialist",
    color: "#5ee7f2",
    jobs: ["focused work", "tool call", "status update"],
  },
  {
    id: "planning",
    label: "Planning Board",
    role: "planner",
    color: "#3d6fd8",
    jobs: ["decomposition", "handoff map", "task estimate"],
  },
  {
    id: "research",
    label: "Research Desk",
    role: "researcher",
    color: "#1e9fb1",
    jobs: ["retrieval", "source check", "context scan"],
  },
  {
    id: "build",
    label: "Build Bench",
    role: "builder",
    color: "#d8891f",
    jobs: ["patching", "integration", "tool run"],
  },
  {
    id: "review",
    label: "Review Table",
    role: "reviewer",
    color: "#c65050",
    jobs: ["risk check", "test review", "finding triage"],
  },
  {
    id: "memory",
    label: "Memory Core",
    role: "memory",
    color: "#6f56c9",
    jobs: ["snapshot", "context sync", "decision log"],
  },
  {
    id: "schedule",
    label: "Schedule Desk",
    role: "scheduler",
    color: "#f4b647",
    jobs: ["cron plan", "follow-up", "briefing timer"],
  },
];

const defaultWorkstations = [
  {
    id: "hub",
    label: "Coordination Hub",
    role: "coordinator",
    color: "#1f8d6a",
    position: { x: 0.5, z: -0.5 },
    jobs: ["routing", "dispatch", "policy check"],
  },
  {
    id: "planning",
    label: "Planning Board",
    role: "planner",
    color: "#3d6fd8",
    position: { x: -4.5, z: -2.5 },
    jobs: ["decomposition", "handoff map", "task estimate"],
  },
  {
    id: "schedule",
    label: "Schedule Desk",
    role: "scheduler",
    color: "#f4b647",
    position: { x: 2.5, z: -3.5 },
    jobs: ["cron plan", "follow-up", "briefing timer"],
  },
  {
    id: "research",
    label: "Research Desk",
    role: "researcher",
    color: "#1e9fb1",
    position: { x: -4.5, z: 2.5 },
    jobs: ["retrieval", "source check", "context scan"],
  },
  {
    id: "build",
    label: "Build Bench",
    role: "builder",
    color: "#d8891f",
    position: { x: 4.5, z: -2.5 },
    jobs: ["patching", "integration", "tool run"],
  },
  {
    id: "review",
    label: "Review Table",
    role: "reviewer",
    color: "#c65050",
    position: { x: 4.5, z: 2.5 },
    jobs: ["risk check", "test review", "finding triage"],
  },
  {
    id: "memory",
    label: "Memory Core",
    role: "memory",
    color: "#6f56c9",
    position: { x: 0.5, z: 3.5 },
    jobs: ["snapshot", "context sync", "decision log"],
  },
  {
    id: "meeting",
    label: "Sync Circle",
    role: "shared",
    color: "#51605a",
    position: { x: -0.5, z: -3.5 },
    jobs: ["standup", "alignment", "handoff"],
  },
];

export const workstations = defaultWorkstations.map((station) => ({ ...station }));

const stationById = new Map(workstations.map((station) => [station.id, station]));

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeTile(value) {
  if (!value) {
    return null;
  }
  const col = Math.round(Number(value.col));
  const row = Math.round(Number(value.row));
  if (!Number.isFinite(col) || !Number.isFinite(row)) {
    return null;
  }
  if (col < 0 || col >= roomConfig.columns || row < 0 || row >= roomConfig.rows) {
    return null;
  }
  return { col, row };
}

function uniqueTiles(values) {
  const seen = new Set();
  const tiles = [];
  for (const value of values ?? []) {
    const tile = normalizeTile(value);
    if (!tile) {
      continue;
    }
    const key = `${tile.col},${tile.row}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    tiles.push(tile);
  }
  return tiles;
}

function rectangleTiles(room) {
  const columns = clamp(Math.round(Number(room.columns) || 6), 1, roomConfig.columns);
  const rows = clamp(Math.round(Number(room.rows) || 5), 1, roomConfig.rows);
  const col = clamp(Math.round(Number(room.col) || 0), 0, roomConfig.columns - columns);
  const row = clamp(Math.round(Number(room.row) || 0), 0, roomConfig.rows - rows);
  const tiles = [];
  for (let tileRow = row; tileRow < row + rows; tileRow += 1) {
    for (let tileCol = col; tileCol < col + columns; tileCol += 1) {
      tiles.push({ col: tileCol, row: tileRow });
    }
  }
  return tiles;
}

function updateRoomBounds(room) {
  const cells = uniqueTiles(room.cells?.length ? room.cells : rectangleTiles(room));
  if (!cells.length) {
    const fallback = rectangleTiles({ col: room.col, row: room.row, columns: 3, rows: 3 });
    room.cells = fallback;
    return updateRoomBounds(room);
  }
  const cols = cells.map((tile) => tile.col);
  const rows = cells.map((tile) => tile.row);
  const minCol = Math.min(...cols);
  const maxCol = Math.max(...cols);
  const minRow = Math.min(...rows);
  const maxRow = Math.max(...rows);
  room.col = minCol;
  room.row = minRow;
  room.columns = maxCol - minCol + 1;
  room.rows = maxRow - minRow + 1;
  room.cells = cells;
  return room;
}

function normalizeRoom(room, fallbackIndex = 0) {
  const columns = clamp(Math.round(Number(room.columns) || 6), 3, roomConfig.columns);
  const rows = clamp(Math.round(Number(room.rows) || 5), 3, roomConfig.rows);
  return updateRoomBounds({
    id: String(room.id || `room-${fallbackIndex + 1}`).slice(0, 60),
    label: String(room.label || `Room ${fallbackIndex + 1}`).slice(0, 80),
    col: clamp(Math.round(Number(room.col) || 0), 0, roomConfig.columns - columns),
    row: clamp(Math.round(Number(room.row) || 0), 0, roomConfig.rows - rows),
    columns,
    rows,
    cells: uniqueTiles(room.cells?.length ? room.cells : rectangleTiles({ ...room, columns, rows })),
    color: String(room.color || "#38bdf8"),
  });
}

export function roomCells(room) {
  return uniqueTiles(room?.cells?.length ? room.cells : rectangleTiles(room ?? {}));
}

function roomContainsTile(room, tile) {
  return roomCells(room).some((cell) => cell.col === tile.col && cell.row === tile.row);
}

function roomsOverlap(left, right) {
  const rightCells = new Set(roomCells(right).map((tile) => `${tile.col},${tile.row}`));
  return roomCells(left).some((tile) => rightCells.has(`${tile.col},${tile.row}`));
}

function areTilesConnected(cells) {
  if (cells.length <= 1) {
    return true;
  }
  const wanted = new Set(cells.map(tileKey));
  const queue = [cells[0]];
  const visited = new Set([tileKey(cells[0])]);
  while (queue.length > 0) {
    const current = queue.shift();
    const candidates = [
      { col: current.col + 1, row: current.row },
      { col: current.col - 1, row: current.row },
      { col: current.col, row: current.row + 1 },
      { col: current.col, row: current.row - 1 },
    ];
    for (const candidate of candidates) {
      const key = tileKey(candidate);
      if (!wanted.has(key) || visited.has(key)) {
        continue;
      }
      visited.add(key);
      queue.push(candidate);
    }
  }
  return visited.size === wanted.size;
}

export function resetRoomLayout() {
  roomLayout.splice(0, roomLayout.length, ...defaultRoomLayout.map((room) => ({ ...room })));
  doorLayout.splice(0, doorLayout.length);
}

export function setRoomLayout(rooms) {
  const normalized = Array.isArray(rooms)
    ? rooms.map((room, index) => normalizeRoom(room, index))
    : [];
  roomLayout.splice(0, roomLayout.length, ...(normalized.length ? normalized : defaultRoomLayout.map((room) => ({ ...room }))));
}

export function setDoorLayout(doors) {
  doorLayout.splice(0, doorLayout.length, ...uniqueTiles(doors));
}

export function addRoomToLayout(room) {
  const normalized = normalizeRoom(room, roomLayout.length);
  if (roomLayout.some((existing) => existing.id === normalized.id)) {
    normalized.id = `${normalized.id}-${Date.now().toString(36)}`;
  }
  roomLayout.push(normalized);
  return normalized;
}

function normalizeWorkstation(station, fallbackIndex = 0) {
  const preset = workstationPresets.find((item) => item.id === station?.presetId)
    ?? workstationPresets.find((item) => item.role === station?.role)
    ?? workstationPresets[0];
  const tile = normalizeTile(station?.tile) ?? (
    station?.position ? worldToTile(station.position) : { col: roomLayout[0]?.col ?? 0, row: roomLayout[0]?.row ?? 0 }
  );
  const position = tileToWorld(tile);
  const agentId = String(station?.agentId ?? "").slice(0, 80);
  const id = String(station?.id || `workstation-${fallbackIndex + 1}`).toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-|-$/g, "").slice(0, 80)
    || `workstation-${fallbackIndex + 1}`;
  return {
    id,
    label: String(station?.label || preset.label || `Workstation ${fallbackIndex + 1}`).slice(0, 80),
    role: String(station?.role || preset.role || "specialist").slice(0, 48),
    color: String(station?.color || preset.color || "#5ee7f2"),
    position,
    jobs: Array.isArray(station?.jobs) && station.jobs.length ? station.jobs.map((job) => String(job).slice(0, 80)) : [...preset.jobs],
    agentId,
    presetId: String(station?.presetId || preset.id),
    custom: true,
  };
}

function registerWorkstation(station) {
  const existingIndex = workstations.findIndex((item) => item.id === station.id);
  if (existingIndex >= 0) {
    workstations.splice(existingIndex, 1, station);
  } else {
    workstations.push(station);
  }
  stationById.set(station.id, station);
  return station;
}

export function setWorkstationLayout(stations) {
  for (let index = workstations.length - 1; index >= 0; index -= 1) {
    if (workstations[index].custom) {
      stationById.delete(workstations[index].id);
      workstations.splice(index, 1);
    }
  }
  for (const [index, station] of (stations ?? []).entries()) {
    const normalized = normalizeWorkstation(station, index);
    if (stationById.has(normalized.id)) {
      normalized.id = `${normalized.id}-${Date.now().toString(36)}-${index}`;
    }
    registerWorkstation(normalized);
  }
}

export function addWorkstationToLayout(station) {
  const normalized = normalizeWorkstation(station, workstations.length);
  if (stationById.has(normalized.id)) {
    normalized.id = `${normalized.id}-${Date.now().toString(36)}`;
  }
  return registerWorkstation(normalized);
}

export function removeRoomFromLayout(roomId) {
  const index = roomLayout.findIndex((room) => room.id === roomId);
  if (index < 0) {
    return { changed: false, reason: "missing" };
  }
  if (roomLayout.length <= 1) {
    return { changed: false, reason: "last-room" };
  }
  const [room] = roomLayout.splice(index, 1);
  return { changed: true, room };
}

export function toggleRoomCell(roomId, tile) {
  const room = roomLayout.find((item) => item.id === roomId);
  const normalizedTile = normalizeTile(tile);
  if (!room || !normalizedTile) {
    return { changed: false, reason: "invalid" };
  }
  const owner = roomLayout.find((item) => item.id !== roomId && roomContainsTile(item, normalizedTile));
  if (owner) {
    return { changed: false, reason: "occupied-by-room", room: owner };
  }
  const key = tileKey(normalizedTile);
  const cells = roomCells(room);
  const exists = cells.some((cell) => tileKey(cell) === key);
  if (exists && cells.length <= 3) {
    return { changed: false, reason: "room-too-small" };
  }
  const nextCells = exists ? cells.filter((cell) => tileKey(cell) !== key) : [...cells, normalizedTile];
  if (!exists) {
    const adjacent = cells.some((cell) => Math.abs(cell.col - normalizedTile.col) + Math.abs(cell.row - normalizedTile.row) === 1);
    if (!adjacent) {
      return { changed: false, reason: "room-not-contiguous" };
    }
  }
  if (!areTilesConnected(nextCells)) {
    return { changed: false, reason: "room-disconnected" };
  }
  room.cells = nextCells;
  updateRoomBounds(room);
  return { changed: true, added: !exists, room };
}

export function isDoorTile(tile) {
  return doorLayout.some((door) => tileEquals(door, tile));
}

export function toggleDoorAt(tile) {
  const normalizedTile = normalizeTile(tile);
  if (!normalizedTile) {
    return { changed: false, reason: "invalid" };
  }
  const key = tileKey(normalizedTile);
  const index = doorLayout.findIndex((door) => tileKey(door) === key);
  if (index >= 0) {
    doorLayout.splice(index, 1);
    return { changed: true, added: false, tile: normalizedTile };
  }
  doorLayout.push(normalizedTile);
  return { changed: true, added: true, tile: normalizedTile };
}

export function findAvailableRoomRect(columns = 6, rows = 5) {
  const wanted = {
    columns: clamp(Math.round(columns), 3, roomConfig.columns),
    rows: clamp(Math.round(rows), 3, roomConfig.rows),
  };
  const candidates = [
    { col: 0, row: 0 },
    { col: roomConfig.columns - wanted.columns, row: 0 },
    { col: 0, row: roomConfig.rows - wanted.rows },
    { col: roomConfig.columns - wanted.columns, row: roomConfig.rows - wanted.rows },
    { col: 0, row: Math.floor((roomConfig.rows - wanted.rows) / 2) },
    { col: roomConfig.columns - wanted.columns, row: Math.floor((roomConfig.rows - wanted.rows) / 2) },
    { col: Math.floor((roomConfig.columns - wanted.columns) / 2), row: 0 },
    { col: Math.floor((roomConfig.columns - wanted.columns) / 2), row: roomConfig.rows - wanted.rows },
  ];
  for (let row = 0; row <= roomConfig.rows - wanted.rows; row += 1) {
    for (let col = 0; col <= roomConfig.columns - wanted.columns; col += 1) {
      candidates.push({ col, row });
    }
  }
  for (const candidate of candidates) {
    const room = { ...candidate, ...wanted };
    if (!roomLayout.some((existing) => roomsOverlap(existing, room))) {
      return room;
    }
  }
  return null;
}

function hashNumber(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function pick(items, seed) {
  return items[Math.abs(seed) % items.length];
}

export function tileKey(tile) {
  return `${tile.col},${tile.row}`;
}

export function tileEquals(a, b) {
  return Boolean(a && b && a.col === b.col && a.row === b.row);
}

export function isWithinWorldBounds(tile) {
  return (
    tile.col >= 0 &&
    tile.col < roomConfig.columns &&
    tile.row >= 0 &&
    tile.row < roomConfig.rows
  );
}

export function isInsideTile(tile) {
  return isWithinWorldBounds(tile) && (roomLayout.some((room) => roomContainsTile(room, tile)) || isDoorTile(tile));
}

export function tileToWorld(tile) {
  return {
    x: (tile.col + 0.5) * roomConfig.cellSize - roomConfig.width / 2,
    z: (tile.row + 0.5) * roomConfig.cellSize - roomConfig.depth / 2,
  };
}

export function worldToTile(position) {
  return {
    col: clamp(Math.floor((position.x + roomConfig.width / 2) / roomConfig.cellSize), 0, roomConfig.columns - 1),
    row: clamp(Math.floor((position.z + roomConfig.depth / 2) / roomConfig.cellSize), 0, roomConfig.rows - 1),
  };
}

function scenarioToTile(position) {
  const room = roomLayout[0] ?? defaultRoomLayout[0];
  return {
    col: clamp(Math.round(room.col + position.x * (room.columns - 1)), room.col, room.col + room.columns - 1),
    row: clamp(Math.round(room.row + position.y * (room.rows - 1)), room.row, room.row + room.rows - 1),
  };
}

function roleStationId(agent) {
  const dedicated = workstations.find((station) => station.agentId === agent.id);
  if (dedicated) {
    return dedicated.id;
  }
  if (agent.role === "coordinator") {
    return "hub";
  }
  if (agent.role === "supervisor") {
    return "hub";
  }
  if ((agent.role === "specialist" || agent.role === "planner") && agent.capabilities.includes("planning")) {
    return "planning";
  }
  if (agent.role === "scheduler" || agent.capabilities.includes("scheduling")) {
    return "schedule";
  }
  if ((agent.role === "specialist" || agent.role === "researcher") && agent.capabilities.includes("research")) {
    return "research";
  }
  if ((agent.role === "specialist" || agent.role === "builder") && agent.capabilities.includes("implementation")) {
    return "build";
  }
  if (agent.role === "reviewer") {
    return "review";
  }
  if (agent.role === "memory") {
    return "memory";
  }
  return "meeting";
}

function stationForStatus(agent) {
  const dedicated = workstations.find((station) => station.agentId === agent.id);
  if (dedicated) {
    return dedicated.id;
  }
  const status = agent.runtime.status.toLowerCase();
  if (status.includes("memory") || status.includes("snapshot")) {
    return agent.role === "memory" ? "memory" : "meeting";
  }
  if (status.includes("review") || status.includes("finding")) {
    return agent.role === "reviewer" ? "review" : "build";
  }
  if (status.includes("award") || status.includes("status")) {
    return agent.capabilities.includes("implementation") ? "build" : roleStationId(agent);
  }
  if (status.includes("proposal")) {
    return roleStationId(agent);
  }
  if (status.includes("announce")) {
    return agent.role === "coordinator" ? "hub" : roleStationId(agent);
  }
  return roleStationId(agent);
}

function neighbors(tile) {
  return [
    { col: tile.col + 1, row: tile.row },
    { col: tile.col - 1, row: tile.row },
    { col: tile.col, row: tile.row + 1 },
    { col: tile.col, row: tile.row - 1 },
  ].filter(isInsideTile);
}

export class AgentWorld {
  constructor(network) {
    this.clock = 0;
    this.states = new Map();
    this.stationMap = stationById;
    this.blockedTiles = this.buildBlockedTiles();

    for (const agent of network.agents) {
      this.registerAgent(agent);
    }
  }

  get stations() {
    return workstations;
  }

  getStation(id) {
    return this.stationMap.get(id);
  }

  getAgentState(id) {
    return this.states.get(id);
  }

  getAgentPosition(id) {
    const state = this.getAgentState(id);
    return state ? { x: state.x, y: 1.2, z: state.z } : { x: 0, y: 1.2, z: 0 };
  }

  registerAgent(agent) {
    if (this.states.has(agent.id)) {
      return this.states.get(agent.id);
    }
    const seed = hashNumber(agent.id);
    const startTile = this.findNearestOpenTile(scenarioToTile(agent.position), agent.id);
    const world = tileToWorld(startTile);
    const state = {
      id: agent.id,
      x: world.x,
      z: world.z,
      y: 0,
      tile: startTile,
      targetTile: startTile,
      destinationTile: startTile,
      targetX: world.x,
      targetZ: world.z,
      path: [],
      facing: seed % 2 === 0 ? Math.PI * 0.25 : -Math.PI * 0.25,
      speed: 2.65 + (seed % 5) * 0.1,
      stationId: roleStationId(agent),
      jobLabel: "starting",
      mode: "idle",
      workProgress: 0,
      walkPhase: (seed % 100) / 100,
      bubble: "",
      lastRuntimeStatus: "",
      nextDecisionAt: 0,
      manualUntil: 0,
      seed,
    };
    this.states.set(agent.id, state);
    this.assignStation(agent, roleStationId(agent), "starting");
    return state;
  }

  isBlockedTile(tile) {
    return this.blockedTiles.has(tileKey(tile));
  }

  isOccupiedTile(tile, exceptAgentId = null) {
    for (const state of this.states.values()) {
      if (state.id === exceptAgentId) {
        continue;
      }
      if (tileEquals(state.tile, tile) || tileEquals(state.targetTile, tile) || tileEquals(state.destinationTile, tile)) {
        return true;
      }
    }
    return false;
  }

  isOpenTile(tile, exceptAgentId = null) {
    return isInsideTile(tile) && !this.isBlockedTile(tile) && !this.isOccupiedTile(tile, exceptAgentId);
  }

  isStationTileOccupied(tile, exceptStationId = null) {
    for (const station of this.stations) {
      if (station.id === exceptStationId) {
        continue;
      }
      if (tileEquals(worldToTile(station.position), tile)) {
        return true;
      }
    }
    return false;
  }

  isOpenStationTile(tile, exceptStationId = null) {
    return isInsideTile(tile) && !this.isOccupiedTile(tile) && !this.isStationTileOccupied(tile, exceptStationId);
  }

  commandMoveAgent(agentId, tile, jobLabel = "manual move") {
    const agentState = this.getAgentState(agentId);
    if (!agentState || !isInsideTile(tile)) {
      return false;
    }

    const destination = this.findNearestOpenTile(tile, agentId);
    const agentLike = { id: agentId };
    const ok = this.setDestination(agentLike, destination, {
      stationId: "manual",
      jobLabel,
      bubble: "manual move",
    });
    if (ok) {
      agentState.manualUntil = this.clock + 14;
      agentState.nextDecisionAt = this.clock + 14;
    }
    return ok;
  }

  commandPlaceAgent(agentId, tile, jobLabel = "layout move") {
    const agentState = this.getAgentState(agentId);
    if (!agentState || !isInsideTile(tile)) {
      return false;
    }
    const destination = this.findNearestOpenTile(tile, agentId);
    const world = tileToWorld(destination);
    agentState.x = world.x;
    agentState.z = world.z;
    agentState.tile = destination;
    agentState.targetTile = destination;
    agentState.destinationTile = destination;
    agentState.targetX = world.x;
    agentState.targetZ = world.z;
    agentState.path = [];
    agentState.mode = "idle";
    agentState.stationId = "manual";
    agentState.jobLabel = jobLabel;
    agentState.bubble = jobLabel;
    agentState.manualUntil = this.clock + 30;
    agentState.nextDecisionAt = this.clock + 30;
    return true;
  }

  commandMoveStation(stationId, tile) {
    const station = this.getStation(stationId);
    if (!station || !isWithinWorldBounds(tile)) {
      return false;
    }
    const destination = this.findNearestOpenStationTile(tile, stationId);
    if (!destination) {
      return false;
    }
    station.position = tileToWorld(destination);
    this.refreshBlockedTiles();
    return true;
  }

  restoreAgentTiles(agentTiles) {
    for (const [agentId, tile] of Object.entries(agentTiles ?? {})) {
      if (tile && Number.isFinite(tile.col) && Number.isFinite(tile.row)) {
        this.commandPlaceAgent(agentId, tile, "restored layout");
      }
    }
  }

  refreshBlockedTiles() {
    this.blockedTiles = this.buildBlockedTiles();
  }

  triggerIntent(intentId, network, options = {}) {
    if (options.autoEnabled === false) {
      return;
    }

    const assignments = {
      task: [
        ["orchestrator", "hub", "dispatching"],
        ["scheduler", "schedule", "checking time"],
        ["planner", "planning", "planning"],
        ["researcher", "research", "researching"],
        ["builder", "build", "building"],
      ],
      "memory-sync": [
        ["orchestrator", "meeting", "syncing"],
        ["memory", "memory", "publishing"],
        ["scheduler", "schedule", "syncing"],
        ["planner", "meeting", "receiving"],
        ["researcher", "meeting", "receiving"],
        ["builder", "meeting", "receiving"],
        ["critic", "meeting", "receiving"],
      ],
      schedule: [
        ["orchestrator", "hub", "requesting"],
        ["scheduler", "schedule", "scheduling"],
        ["memory", "memory", "checking context"],
      ],
      review: [
        ["builder", "build", "submitting"],
        ["critic", "review", "reviewing"],
        ["orchestrator", "hub", "tracking"],
      ],
    };

    for (const [agentId, stationId, jobLabel] of assignments[intentId] ?? []) {
      const agent = network.getAgent(agentId);
      if (agent) {
        this.assignStation(agent, stationId, jobLabel, true);
      }
    }
  }

  tick(deltaSeconds, network, options = {}) {
    const delta = Math.min(deltaSeconds, 0.12);
    const autoEnabled = options.autoEnabled !== false;
    this.clock += delta;

    for (const agent of network.agents) {
      const state = this.getAgentState(agent.id);
      if (!state) {
        continue;
      }

      const manualActive = state.manualUntil > this.clock;
      if (state.lastRuntimeStatus !== agent.runtime.status) {
        state.lastRuntimeStatus = agent.runtime.status;
        state.bubble = agent.runtime.status;
        if (autoEnabled && !manualActive) {
          this.assignStation(agent, stationForStatus(agent), agent.runtime.status);
        }
      } else if (autoEnabled && !manualActive && this.clock >= state.nextDecisionAt && state.mode === "working") {
        const idleStation = this.getStation(roleStationId(agent));
        const shouldMeet = (Math.floor(this.clock + state.seed) % 9) === 0;
        this.assignStation(agent, shouldMeet ? "meeting" : idleStation.id);
      }

      this.moveAgent(state, delta);
      this.updateWorkState(agent, state, delta);
    }
  }

  assignStation(agent, stationId, jobLabel = null, urgent = false) {
    const state = this.getAgentState(agent.id);
    const station = this.getStation(stationId) ?? this.getStation(roleStationId(agent));
    if (!state || !station) {
      return false;
    }

    const targetTile = this.pickStationTile(station, agent.id, state.seed + Math.floor(this.clock * 2));
    const ok = this.setDestination(agent, targetTile, {
      stationId: station.id,
      jobLabel: jobLabel ?? pick(station.jobs, state.seed + Math.floor(this.clock)),
      bubble: jobLabel ?? pick(station.jobs, state.seed + Math.floor(this.clock)),
    });
    if (ok) {
      state.nextDecisionAt = this.clock + (urgent ? 8 : 5.5 + (state.seed % 5));
    }
    return ok;
  }

  setDestination(agent, tile, options = {}) {
    const state = this.getAgentState(agent.id);
    if (!state) {
      return false;
    }

    const destination = this.findNearestOpenTile(tile, agent.id);
    const path = this.findPath(state.tile, destination, agent.id);
    if (path.length === 0 && !tileEquals(state.tile, destination)) {
      return false;
    }

    state.stationId = options.stationId ?? state.stationId;
    state.destinationTile = destination;
    state.path = path;
    state.jobLabel = options.jobLabel ?? state.jobLabel;
    state.bubble = options.bubble ?? state.jobLabel;
    state.workProgress = 0;

    if (tileEquals(state.tile, destination)) {
      state.mode = "working";
      state.targetTile = state.tile;
      const world = tileToWorld(state.tile);
      state.targetX = world.x;
      state.targetZ = world.z;
      return true;
    }

    this.startNextStep(state);
    return true;
  }

  startNextStep(state) {
    const nextTile = state.path.shift();
    if (!nextTile) {
      state.mode = "working";
      state.targetTile = state.tile;
      return;
    }

    const world = tileToWorld(nextTile);
    state.targetTile = nextTile;
    state.targetX = world.x;
    state.targetZ = world.z;
    state.mode = "walking";
  }

  moveAgent(state, delta) {
    const dx = state.targetX - state.x;
    const dz = state.targetZ - state.z;
    const distance = Math.hypot(dx, dz);
    state.walkPhase += delta * (distance > 0.02 ? 9.5 : 2);

    if (distance < 0.025) {
      state.x = state.targetX;
      state.z = state.targetZ;
      state.tile = state.targetTile;

      if (state.path.length > 0) {
        this.startNextStep(state);
        return;
      }

      state.mode = "working";
      const station = this.getStation(state.stationId);
      if (station) {
        state.facing = Math.atan2(station.position.x - state.x, station.position.z - state.z);
      }
      return;
    }

    const step = Math.min(distance, state.speed * delta);
    state.x += (dx / distance) * step;
    state.z += (dz / distance) * step;
    state.facing = Math.atan2(dx, dz);
  }

  updateWorkState(agent, state, delta) {
    if (state.mode !== "working") {
      state.workProgress = Math.max(0, state.workProgress - delta * 0.3);
      return;
    }

    const effort = 0.14 + agent.runtime.load * 0.18;
    state.workProgress += delta * effort;
    if (state.workProgress >= 1) {
      state.workProgress = 0;
      if (state.stationId === "manual") {
        state.jobLabel = "waiting";
        state.bubble = "waiting";
      } else {
        const station = this.getStation(state.stationId);
        state.jobLabel = pick(station?.jobs ?? ["idle"], state.seed + Math.floor(this.clock * 3));
        state.bubble = state.jobLabel;
      }
    }
  }

  pickStationTile(station, agentId, seed) {
    const stationTile = worldToTile(station.position);
    const ring = station.id === "meeting" ? 2 : 1;
    const candidates = [];
    for (let row = stationTile.row - ring; row <= stationTile.row + ring; row += 1) {
      for (let col = stationTile.col - ring; col <= stationTile.col + ring; col += 1) {
        const tile = { col, row };
        if (!isInsideTile(tile) || tileEquals(tile, stationTile)) {
          continue;
        }
        const distance = Math.abs(col - stationTile.col) + Math.abs(row - stationTile.row);
        if (distance > 0 && distance <= ring + 1 && this.isOpenTile(tile, agentId)) {
          candidates.push(tile);
        }
      }
    }

    if (candidates.length > 0) {
      return candidates[Math.abs(seed) % candidates.length];
    }
    return this.findNearestOpenTile(stationTile, agentId);
  }

  findNearestOpenTile(preferred, agentId = null) {
    const start = {
      col: clamp(preferred.col, 0, roomConfig.columns - 1),
      row: clamp(preferred.row, 0, roomConfig.rows - 1),
    };
    if (this.isOpenTile(start, agentId) || tileEquals(this.getAgentState(agentId)?.tile, start)) {
      return start;
    }

    const queue = [start];
    const visited = new Set([tileKey(start)]);
    while (queue.length > 0) {
      const current = queue.shift();
      for (const next of neighbors(current)) {
        const key = tileKey(next);
        if (visited.has(key)) {
          continue;
        }
        if (this.isOpenTile(next, agentId)) {
          return next;
        }
        visited.add(key);
        queue.push(next);
      }
    }
    return this.getAgentState(agentId)?.tile ?? start;
  }

  findNearestOpenStationTile(preferred, stationId = null) {
    const start = {
      col: clamp(preferred.col, 0, roomConfig.columns - 1),
      row: clamp(preferred.row, 0, roomConfig.rows - 1),
    };
    if (this.isOpenStationTile(start, stationId)) {
      return start;
    }

    const queue = [start];
    const visited = new Set([tileKey(start)]);
    while (queue.length > 0) {
      const current = queue.shift();
      for (const next of neighbors(current)) {
        const key = tileKey(next);
        if (visited.has(key)) {
          continue;
        }
        if (this.isOpenStationTile(next, stationId)) {
          return next;
        }
        visited.add(key);
        queue.push(next);
      }
    }
    return null;
  }

  findPath(start, goal, agentId = null) {
    if (tileEquals(start, goal)) {
      return [];
    }

    const queue = [start];
    const visited = new Set([tileKey(start)]);
    const parent = new Map();

    while (queue.length > 0) {
      const current = queue.shift();
      if (tileEquals(current, goal)) {
        break;
      }

      const orderedNeighbors = neighbors(current).sort(
        (a, b) =>
          Math.abs(a.col - goal.col) +
          Math.abs(a.row - goal.row) -
          (Math.abs(b.col - goal.col) + Math.abs(b.row - goal.row))
      );

      for (const next of orderedNeighbors) {
        const key = tileKey(next);
        if (visited.has(key)) {
          continue;
        }
        if (!tileEquals(next, goal) && !this.isOpenTile(next, agentId)) {
          continue;
        }
        if (this.isBlockedTile(next)) {
          continue;
        }
        visited.add(key);
        parent.set(key, current);
        queue.push(next);
      }
    }

    if (!visited.has(tileKey(goal))) {
      return [];
    }

    const reversed = [];
    let current = goal;
    while (!tileEquals(current, start)) {
      reversed.push(current);
      current = parent.get(tileKey(current));
      if (!current) {
        return [];
      }
    }
    return reversed.reverse();
  }

  buildBlockedTiles() {
    return new Set(
      workstations
        .map((station) => worldToTile(station.position))
        .filter(isInsideTile)
        .map(tileKey)
    );
  }
}
