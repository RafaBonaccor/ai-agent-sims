export const roomConfig = {
  width: 14,
  depth: 10,
  columns: 14,
  rows: 10,
  cellSize: 1,
  blockHeight: 0.22,
};

export const workstations = [
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

const stationById = new Map(workstations.map((station) => [station.id, station]));

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
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

export function isInsideTile(tile) {
  return (
    tile.col >= 0 &&
    tile.col < roomConfig.columns &&
    tile.row >= 0 &&
    tile.row < roomConfig.rows
  );
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
  return worldToTile({
    x: (position.x - 0.5) * (roomConfig.width - 2.4),
    z: (position.y - 0.5) * (roomConfig.depth - 2.2),
  });
}

function roleStationId(agent) {
  if (agent.role === "coordinator") {
    return "hub";
  }
  if (agent.role === "specialist" && agent.capabilities.includes("planning")) {
    return "planning";
  }
  if (agent.role === "specialist" && agent.capabilities.includes("research")) {
    return "research";
  }
  if (agent.role === "specialist" && agent.capabilities.includes("implementation")) {
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
      const seed = hashNumber(agent.id);
      const startTile = this.findNearestOpenTile(scenarioToTile(agent.position), agent.id);
      const world = tileToWorld(startTile);
      this.states.set(agent.id, {
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
      });
      this.assignStation(agent, roleStationId(agent), "starting");
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

  triggerIntent(intentId, network, options = {}) {
    if (options.autoEnabled === false) {
      return;
    }

    const assignments = {
      task: [
        ["orchestrator", "hub", "dispatching"],
        ["planner", "planning", "planning"],
        ["researcher", "research", "researching"],
        ["builder", "build", "building"],
      ],
      "memory-sync": [
        ["orchestrator", "meeting", "syncing"],
        ["memory", "memory", "publishing"],
        ["planner", "meeting", "receiving"],
        ["researcher", "meeting", "receiving"],
        ["builder", "meeting", "receiving"],
        ["critic", "meeting", "receiving"],
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
    return new Set(workstations.map((station) => tileKey(worldToTile(station.position))));
  }
}
