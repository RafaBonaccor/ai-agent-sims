import * as THREE from "three";
import { AgentNetwork } from "./src/agentProtocol.mjs";
import {
  AgentWorld,
  roomConfig,
  tileEquals,
  tileKey,
  tileToWorld,
  workstations,
} from "./src/agentWorld.mjs";
import { defaultScenario } from "./src/scenarios.mjs";

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

const network = new AgentNetwork(defaultScenario);
const agentWorld = new AgentWorld(network);

const PERFORMANCE = {
  maxFps: 30,
  maxPixelRatio: 1.25,
  shadows: false,
  hudRefreshMs: 500,
  relationRefreshMs: 120,
  messageLineSegments: 12,
  fog: false,
};

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: false,
  powerPreference: "low-power",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, PERFORMANCE.maxPixelRatio));
renderer.shadowMap.enabled = PERFORMANCE.shadows;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xcfd9d2);
scene.fog = PERFORMANCE.fog ? new THREE.Fog(0xcfd9d2, 18, 34) : null;

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
let nextUiRefresh = 0;
let nextRelationRefresh = 0;
let lastFrameAt = 0;

const selectableObjects = [];
const agentVisuals = new Map();
const stationVisuals = new Map();
const relationVisuals = new Map();
const messageVisuals = new Map();
const tileVisuals = new Map();

const sharedMaterials = {
  floor: new THREE.MeshStandardMaterial({ color: 0xe6e4d8, roughness: 0.94 }),
  wall: new THREE.MeshStandardMaterial({ color: 0xbec8c2, roughness: 0.9 }),
  trim: new THREE.MeshStandardMaterial({ color: 0x2c3531, roughness: 0.75 }),
  glass: new THREE.MeshStandardMaterial({
    color: 0x9ad7df,
    transparent: true,
    opacity: 0.32,
    roughness: 0.2,
    metalness: 0.05,
  }),
  shadow: new THREE.MeshBasicMaterial({
    color: 0x000000,
    transparent: true,
    opacity: 0.13,
    depthWrite: false,
  }),
};

const scratchStart = new THREE.Vector3();
const scratchMid = new THREE.Vector3();
const scratchEnd = new THREE.Vector3();
const scratchCurve = new THREE.QuadraticBezierCurve3(
  new THREE.Vector3(),
  new THREE.Vector3(),
  new THREE.Vector3()
);

const tilePalette = {
  even: new THREE.Color(0xe4e0d2),
  odd: new THREE.Color(0xd9d5c8),
  blocked: new THREE.Color(0xb8b4a6),
  current: new THREE.Color(0x65b88d),
  destination: new THREE.Color(0xe4b24d),
  occupied: new THREE.Color(0xc9d7d1),
};

function setBootMessage(message) {
  if (bootMessage) {
    bootMessage.textContent = message;
  }
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
    labelCtx.fillStyle = options.color ?? "#1b201f";
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
    labelCtx.fillStyle = options.background ?? "rgba(255, 255, 255, 0.9)";
    drawRoundedRect(labelCtx, 8, 8, width - 16, height - 16, options.radius ?? 26);
    labelCtx.fill();
    labelCtx.strokeStyle = options.border ?? "rgba(27, 32, 31, 0.14)";
    labelCtx.lineWidth = 4;
    labelCtx.stroke();
    labelCtx.font = `${options.weight ?? 800} ${options.size ?? 34}px Inter, Arial, sans-serif`;
    labelCtx.textAlign = "center";
    labelCtx.textBaseline = "middle";
    labelCtx.fillStyle = options.color ?? "#1b201f";
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

function buildRoom() {
  const base = new THREE.Mesh(
    new THREE.BoxGeometry(roomConfig.width + 0.18, 0.16, roomConfig.depth + 0.18),
    sharedMaterials.trim
  );
  base.position.y = -roomConfig.blockHeight - 0.06;
  base.receiveShadow = true;
  scene.add(base);

  const tileGeometry = new THREE.BoxGeometry(0.94, roomConfig.blockHeight, 0.94);
  for (let row = 0; row < roomConfig.rows; row += 1) {
    for (let col = 0; col < roomConfig.columns; col += 1) {
      const tile = { col, row };
      const world = tileToWorld(tile);
      const blocked = agentWorld.isBlockedTile(tile);
      const baseColor = blocked
        ? tilePalette.blocked
        : (row + col) % 2 === 0
          ? tilePalette.even
          : tilePalette.odd;
      const material = new THREE.MeshStandardMaterial({
        color: baseColor,
        roughness: 0.92,
      });
      const mesh = new THREE.Mesh(tileGeometry, material);
      mesh.position.set(world.x, -roomConfig.blockHeight / 2, world.z);
      mesh.receiveShadow = true;
      mesh.userData.tile = tile;
      mesh.userData.tileKey = tileKey(tile);
      mesh.userData.baseColor = baseColor.clone();
      scene.add(mesh);
      tileVisuals.set(tileKey(tile), mesh);
      selectableObjects.push(mesh);
    }
  }

  const backWall = new THREE.Mesh(
    new THREE.BoxGeometry(roomConfig.width, 1.55, 0.22),
    sharedMaterials.wall
  );
  backWall.position.set(0, 0.72, -roomConfig.depth / 2 - 0.08);
  backWall.castShadow = true;
  backWall.receiveShadow = true;
  scene.add(backWall);

  const leftWall = new THREE.Mesh(
    new THREE.BoxGeometry(0.22, 1.55, roomConfig.depth),
    sharedMaterials.wall
  );
  leftWall.position.set(-roomConfig.width / 2 - 0.08, 0.72, 0);
  leftWall.castShadow = true;
  leftWall.receiveShadow = true;
  scene.add(leftWall);

  const trimMaterial = sharedMaterials.trim;
  for (const z of [-roomConfig.depth / 2, roomConfig.depth / 2]) {
    const trim = new THREE.Mesh(new THREE.BoxGeometry(roomConfig.width, 0.08, 0.08), trimMaterial);
    trim.position.set(0, 0.05, z);
    scene.add(trim);
  }
  for (const x of [-roomConfig.width / 2, roomConfig.width / 2]) {
    const trim = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.08, roomConfig.depth), trimMaterial);
    trim.position.set(x, 0.05, 0);
    scene.add(trim);
  }

  const rug = new THREE.Mesh(
    new THREE.CylinderGeometry(2.15, 2.15, 0.035, 32),
    new THREE.MeshStandardMaterial({ color: 0xd8c89f, roughness: 0.86 })
  );
  rug.rotation.x = Math.PI / 2;
  rug.position.set(0, 0.03, -3.75);
  rug.receiveShadow = true;
  scene.add(rug);
}

function buildLights() {
  scene.add(new THREE.HemisphereLight(0xf5fff9, 0x899288, 1.5));

  const key = new THREE.DirectionalLight(0xfff6dd, 2.35);
  key.position.set(5, 9, 6);
  key.castShadow = PERFORMANCE.shadows;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -11;
  key.shadow.camera.right = 11;
  key.shadow.camera.top = 11;
  key.shadow.camera.bottom = -11;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xbcdfff, 0.85);
  fill.position.set(-7, 6, -3);
  scene.add(fill);
}

function createStationProp(station) {
  const group = new THREE.Group();
  const stationMaterial = colorMaterial(station.color);
  const darkMaterial = colorMaterial(0x25302d, { roughness: 0.8 });
  const lightMaterial = colorMaterial(station.color, {
    emissive: new THREE.Color(station.color).multiplyScalar(0.45),
    roughness: 0.38,
  });

  const base = new THREE.Mesh(
    new THREE.CylinderGeometry(0.88, 0.92, 0.08, 24),
    new THREE.MeshStandardMaterial({
      color: station.color,
      transparent: true,
      opacity: 0.24,
      roughness: 0.7,
    })
  );
  base.position.y = 0.04;
  base.receiveShadow = true;
  group.add(base);

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
    background: "rgba(255, 255, 255, 0.86)",
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
  const bodyMaterial = colorMaterial(agent.color);
  const headMaterial = colorMaterial(0xf2d1b6, { roughness: 0.68 });
  const darkMaterial = colorMaterial(0x26302d, { roughness: 0.86 });
  const glowMaterial = colorMaterial(agent.color, {
    emissive: new THREE.Color(agent.color).multiplyScalar(0.5),
    roughness: 0.36,
  });

  const shadow = new THREE.Mesh(new THREE.CircleGeometry(0.48, 16), sharedMaterials.shadow);
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = 0.018;
  shadow.userData.agentId = agent.id;
  group.add(shadow);

  const torso = addMesh(group, new THREE.CylinderGeometry(0.28, 0.34, 0.72, 12), bodyMaterial, {
    y: 0.72,
  });
  const head = addMesh(group, new THREE.SphereGeometry(0.25, 16, 12), headMaterial, { y: 1.22 });
  const visor = addMesh(group, new THREE.BoxGeometry(0.32, 0.08, 0.035), darkMaterial, { y: 1.24, z: 0.22 });
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
    background: "rgba(255, 255, 255, 0.86)",
    size: 36,
    scaleX: 1.7,
    scaleY: 0.42,
  });
  name.position.set(0, 2.2, 0);
  group.add(name);

  const bubble = createTextSprite("", {
    background: "rgba(255, 255, 255, 0.92)",
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
    bubble,
    name,
  });
}

function buildRelationVisuals() {
  for (const relation of network.relations) {
    const protocol = network.getProtocol(relation.protocolId);
    const material = new THREE.LineBasicMaterial({
      color: protocol.color,
      transparent: true,
      opacity: 0.18,
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(9), 3));
    const line = new THREE.Line(geometry, material);
    line.position.y = 0.06;
    scene.add(line);
    relationVisuals.set(relation.id, line);
  }
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
    opacity: 0.72,
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
    background: "rgba(255, 255, 255, 0.88)",
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

    const bubbleText = state.bubble || agent.runtime.status;
    visual.bubble.visible = Boolean(bubbleText) && selectedAgentId === agent.id;
    if (visual.bubble.visible) {
      replaceSpriteText(visual.bubble, bubbleText, {
        background: "rgba(255, 255, 255, 0.92)",
        border: selected ? agent.color : "rgba(27, 32, 31, 0.14)",
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
    if (selectedState && tileEquals(tile, selectedState.destinationTile)) {
      renderState = "destination";
    } else if (selectedState && tileEquals(tile, selectedState.tile)) {
      renderState = "current";
    } else if (occupiedKeys.has(key)) {
      renderState = "occupied";
    }

    if (mesh.userData.renderState === renderState) {
      continue;
    }

    mesh.userData.renderState = renderState;
    if (renderState === "destination") {
      mesh.material.color.copy(tilePalette.destination);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.035;
    } else if (renderState === "current") {
      mesh.material.color.copy(tilePalette.current);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.045;
    } else if (renderState === "occupied") {
      mesh.material.color.copy(tilePalette.occupied);
      mesh.position.y = -roomConfig.blockHeight / 2 + 0.015;
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

  selectedName.textContent = agent.label;
  selectedRole.textContent = agent.role;
  selectedJob.textContent = `${state?.jobLabel ?? "idle"} @ ${station?.label ?? "room"}`;
  selectedStatus.textContent = agent.runtime.status;
  selectedLoad.textContent = `${Math.round(agent.runtime.load * 100)}%`;
  selectedTile.textContent = state ? `${state.tile.col + 1}, ${state.tile.row + 1}` : "-";

  metrics.innerHTML = `
    <span>${network.agents.length} agenti</span>
    <span>${network.messages.length} messaggi</span>
    <span>${network.relations.length} canali</span>
    <span>${speed}x</span>
    <span>${autoAgents ? "auto" : "manuale"}</span>
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

function triggerIntent(intentId) {
  network.triggerIntent(intentId);
  agentWorld.triggerIntent(intentId, network, { autoEnabled: autoAgents });
  updateHud();
}

function setPointerNdc(event) {
  const rect = canvas.getBoundingClientRect();
  pointerNdc.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointerNdc.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
}

function selectFromPointer(event) {
  setPointerNdc(event);
  raycaster.setFromCamera(pointerNdc, camera);
  const hits = raycaster.intersectObjects(selectableObjects, true);
  const hit = hits.find(
    (item) => item.object.userData.agentId || item.object.userData.stationId || item.object.userData.tile
  );
  if (!hit) {
    selectedStationId = null;
    updateHud();
    return;
  }

  const agentId = hit.object.userData.agentId;
  const stationId = hit.object.userData.stationId;
  if (agentId) {
    selectedAgentId = agentId;
    selectedStationId = null;
  } else if (stationId) {
    selectedStationId = stationId;
  } else if (hit.object.userData.tile) {
    selectedStationId = null;
    const moved = agentWorld.commandMoveAgent(selectedAgentId, hit.object.userData.tile, "manual move");
    if (moved) {
      setAutoAgents(false);
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
  cameraTarget.x = Math.max(-2.5, Math.min(2.5, cameraTarget.x));
  cameraTarget.z = Math.max(-2.2, Math.min(2.2, cameraTarget.z));
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
  if (event.code === "Space") {
    event.preventDefault();
    setRunning(!running);
  } else if (event.code === "KeyQ") {
    cameraYaw -= Math.PI / 12;
    updateCamera();
  } else if (event.code === "KeyE") {
    cameraYaw += Math.PI / 12;
    updateCamera();
  } else if (event.code === "Digit1") {
    triggerIntent("task");
  } else if (event.code === "Digit2") {
    triggerIntent("memory-sync");
  } else if (event.code === "Digit3") {
    triggerIntent("review");
  }
});

runToggle.addEventListener("click", () => setRunning(!running));
autoToggle.addEventListener("click", () => setAutoAgents(!autoAgents));
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
    cameraTarget.set(station.position.x * 0.18, 0, station.position.z * 0.18);
    updateCamera();
  }
  updateHud();
});

window.addEventListener("resize", resize);

buildScene();
resize();
setSpeed(1);
setAutoAgents(true);
triggerIntent("task");
setBootMessage("");
window.__agentLabBooted = true;
requestAnimationFrame(animate);
