export class RuntimeClient {
  constructor() {
    this.connected = false;
    this.socket = null;
    this.listeners = new Set();
  }

  onEvent(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit(event) {
    for (const listener of this.listeners) {
      listener(event);
    }
  }

  async connect() {
    const response = await fetch("/api/health", { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`Runtime health check failed: ${response.status}`);
    }
    const health = await response.json();
    if (!health.features?.projectGateway) {
      throw new Error("Runtime non aggiornato: chiudi il vecchio server e riavvia run.bat.");
    }
    this.connected = true;
    this.openSocket();
    return health;
  }

  openSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.socket = new WebSocket(`${protocol}//${window.location.host}/ws/events`);
    this.socket.addEventListener("message", (event) => {
      this.emit(JSON.parse(event.data));
    });
    this.socket.addEventListener("close", () => {
      this.connected = false;
      this.emit({ type: "runtime.disconnected" });
    });
    this.socket.addEventListener("error", () => {
      this.socket?.close();
    });
  }

  async request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = body.detail ?? response.statusText ?? "Request failed";
      throw new Error(`${options.method ?? "GET"} ${path}: ${response.status} ${detail}`);
    }
    return response.json();
  }

  createAgent(agent) {
    return this.request("/api/agents", {
      method: "POST",
      body: JSON.stringify(agent),
    });
  }

  updateAgent(agentId, agent) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}`, {
      method: "PUT",
      body: JSON.stringify(agent),
    });
  }

  getAgentMemory(agentId) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/memory`);
  }

  updateAgentMemory(agentId, content) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/memory`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  }

  createTask(task) {
    return this.request("/api/tasks", {
      method: "POST",
      body: JSON.stringify(task),
    });
  }

  listProjects() {
    return this.request("/api/projects");
  }

  createProjectJob(job) {
    return this.request("/api/project-jobs", {
      method: "POST",
      body: JSON.stringify(job),
    });
  }

  logClient(level, message, context = {}) {
    return fetch("/api/diagnostics/client", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, message: String(message), context }),
      keepalive: true,
    }).catch(() => undefined);
  }
}
