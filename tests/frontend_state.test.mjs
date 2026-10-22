import test from "node:test";
import assert from "node:assert/strict";
import { LayoutHistory } from "../src/layoutHistory.mjs";
import { JobNotificationState } from "../src/jobNotifications.mjs";
import { AgentWorld, doorLayout, pruneDisconnectedDoorPaths, roomLayout, setDoorAt, setDoorLayout, setRoomCell, setRoomLayout } from "../src/agentWorld.mjs";
import { AgentNetwork } from "../src/agentProtocol.mjs";
import { defaultScenario } from "../src/scenarios.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  };
}

test("layout history supports undo, redo, and drops redo after a new edit", () => {
  const history = new LayoutHistory(2);
  const a = { rooms: [{ id: "a" }] };
  const b = { rooms: [{ id: "b" }] };
  const c = { rooms: [{ id: "c" }] };

  assert.equal(history.record(a, b), true);
  assert.deepEqual(history.undo(b), a);
  assert.deepEqual(history.redo(a), b);
  assert.equal(history.record(b, c), true);
  assert.deepEqual(history.undo(c), b);
  history.record(b, a);
  assert.equal(history.canRedo, false);
});

test("job notifications persist unread state and acknowledge it", () => {
  const storage = memoryStorage();
  const first = new JobNotificationState(storage);
  first.observe([{ id: "old", state: "completed", updated_at: "2026-01-01T00:00:00Z" }]);
  assert.equal(first.unreadIds.size, 0);

  assert.equal(first.markUnread("new-job"), true);
  assert.equal(first.markUnread("new-job"), false);
  const reloaded = new JobNotificationState(storage);
  assert.deepEqual([...reloaded.unreadIds], ["new-job"]);

  reloaded.acknowledge(["new-job"]);
  assert.equal(new JobNotificationState(storage).unreadIds.size, 0);
});

test("jobs completed while the game is closed become unread on reconnect", () => {
  const storage = memoryStorage();
  const first = new JobNotificationState(storage);
  first.observe([{ id: "known", state: "completed", updated_at: "2026-06-01T12:00:00Z" }]);

  const reloaded = new JobNotificationState(storage);
  reloaded.observe([
    { id: "known", state: "completed", updated_at: "2026-06-01T12:00:00Z" },
    { id: "finished-offline", state: "failed", updated_at: new Date(Date.now() + 1000).toISOString() },
  ]);
  assert.deepEqual([...reloaded.unreadIds], ["finished-offline"]);
});

test("room sculpting keeps rooms connected and supports fixed add/erase strokes", () => {
  const priorRooms = structuredClone(roomLayout);
  const priorDoors = structuredClone(doorLayout);
  try {
    setRoomLayout([{ id: "editor-test", label: "Editor test", col: 0, row: 0, columns: 4, rows: 3 }]);
    assert.equal(setRoomCell("editor-test", { col: 4, row: 1 }, true).changed, true);
    assert.equal(setRoomCell("editor-test", { col: 4, row: 1 }, true).reason, "unchanged");
    assert.equal(setRoomCell("editor-test", { col: 0, row: 0 }, false).changed, true);

    setRoomLayout([{ id: "narrow", label: "Narrow", col: 0, row: 0, columns: 4, rows: 1,
      cells: [{ col: 0, row: 0 }, { col: 1, row: 0 }, { col: 2, row: 0 }, { col: 3, row: 0 }] }]);
    assert.equal(setRoomCell("narrow", { col: 1, row: 0 }, false).reason, "room-disconnected");
  } finally {
    setRoomLayout(priorRooms);
    setDoorLayout(priorDoors);
  }
});

test("door and path tiles must connect to a room and remain connected when erased", () => {
  const priorRooms = structuredClone(roomLayout);
  const priorDoors = structuredClone(doorLayout);
  try {
    setRoomLayout([{ id: "door-test", label: "Door test", col: 5, row: 5, columns: 3, rows: 3 }]);
    setDoorLayout([]);
    assert.equal(setDoorAt({ col: 15, row: 15 }, true).reason, "path-not-connected");
    assert.equal(setDoorAt({ col: 6, row: 6 }, true).reason, "inside-room");
    assert.equal(setDoorAt({ col: 8, row: 5 }, true).changed, true);
    assert.equal(setDoorAt({ col: 9, row: 5 }, true).changed, true);
    assert.equal(setDoorAt({ col: 8, row: 5 }, false).reason, "path-disconnected");
    assert.equal(setDoorAt({ col: 8, row: 5 }, false, { allowTemporaryDisconnect: true }).changed, true);
    assert.equal(pruneDisconnectedDoorPaths(), 1);
    assert.equal(doorLayout.length, 0);
  } finally {
    setRoomLayout(priorRooms);
    setDoorLayout(priorDoors);
  }
});

test("assigned agents go to their own desk and stay there until work finishes", () => {
  const network = new AgentNetwork(defaultScenario);
  const world = new AgentWorld(network);
  const agent = network.getAgent("researcher");
  assert.ok(agent);
  agent.runtime.status = "executing";

  assert.equal(world.assignAgentToWork(agent.id, "task-1", "Research task", network), true);
  const state = world.getAgentState(agent.id);
  assert.equal(state.stationId, "research");
  for (let step = 0; step < 120; step += 1) world.tick(0.12, network);
  assert.equal(state.stationId, "research");
  assert.equal(state.activeWorkIds.has("task-1"), true);

  assert.equal(world.releaseAgentFromWork(agent.id, "task-1", network), true);
  assert.equal(state.activeWorkIds.size, 0);
});
