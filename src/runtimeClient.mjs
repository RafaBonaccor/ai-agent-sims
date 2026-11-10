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
      const detail = formatErrorDetail(body.detail ?? response.statusText ?? "Request failed");
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

  listAgents() {
    return this.request("/api/agents");
  }

  updateAgent(agentId, agent) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}`, {
      method: "PUT",
      body: JSON.stringify(agent),
    });
  }

  getSystemSettings() {
    return this.request("/api/system-settings");
  }

  updateSystemSettings(settings) {
    return this.request("/api/system-settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    });
  }

  getAppiumStatus() {
    return this.request("/api/appium/status");
  }

  startAppium() {
    return this.request("/api/appium/start", { method: "POST", body: JSON.stringify({}) });
  }

  stopAppium() {
    return this.request("/api/appium/stop", { method: "POST", body: JSON.stringify({}) });
  }

  listAppiumApps(deviceId) {
    return this.request(`/api/appium/apps?device_id=${encodeURIComponent(deviceId)}`);
  }

  launchAppiumApp(deviceId, bundleId) {
    return this.request("/api/appium/launch", {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, bundle_id: bundleId }),
    });
  }

  endAppiumSession() {
    return this.request("/api/appium/end-session", { method: "POST", body: JSON.stringify({}) });
  }

  async getAppiumScreenshot() {
    const response = await fetch("/api/appium/screenshot", { headers: { Accept: "image/png" } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = formatErrorDetail(body.detail ?? response.statusText ?? "Screenshot failed");
      throw new Error(`GET /api/appium/screenshot: ${response.status} ${detail}`);
    }
    return response.blob();
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

  getAgentWiki(agentId) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/wiki`);
  }

  updateAgentWiki(agentId, content) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/wiki`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  }

  listWikiProposals(limit = 50) {
    return this.request(`/api/wiki/proposals?limit=${encodeURIComponent(limit)}`);
  }

  listWikiPages() {
    return this.request("/api/wiki/pages");
  }

  getWikiPage(name) {
    const safePath = String(name).split("/").map(encodeURIComponent).join("/");
    return this.request(`/api/wiki/pages/${safePath}`);
  }

  searchWiki(query, limit = 8) {
    return this.request(`/api/wiki/search?query=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`);
  }

  runWikiMaintenance() {
    return this.request("/api/wiki/maintenance/run", { method: "POST" });
  }

  resolveWikiProposal(name, status, reviewer = "user", reason = "") {
    return this.request(`/api/wiki/proposals/${encodeURIComponent(name)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ status, reviewer, reason }),
    });
  }

  createTask(task) {
    return this.request("/api/tasks", {
      method: "POST",
      body: JSON.stringify(task),
    });
  }

  listTasks() {
    return this.request("/api/tasks");
  }

  listBrowserSessions() {
    return this.request("/api/browser/sessions");
  }

  createBrowserSession(session) {
    return this.request("/api/browser/sessions", {
      method: "POST",
      body: JSON.stringify(session),
    });
  }

  runBrowserCommand(sessionId, command, parameters = {}) {
    return this.request(`/api/browser/sessions/${encodeURIComponent(sessionId)}/commands`, {
      method: "POST",
      body: JSON.stringify({ command, parameters }),
    });
  }

  closeBrowserSession(sessionId) {
    return this.request(`/api/browser/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
  }

  getAgentChat(agentId) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/chat`);
  }

  getSecretStatus(agentId) {
    return this.request(`/api/secrets/status?agent_id=${encodeURIComponent(agentId)}`);
  }

  setProjectSecret(apiKey) {
    return this.request("/api/secrets/project", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  setDiscordBotSecret(apiKey) {
    return this.request("/api/secrets/discord-bot", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  setAccordiAdminSecret(apiKey) {
    return this.request("/api/secrets/accordi-admin", {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  setRunPodSecret(apiKey) {
    return this.request("/api/secrets/runpod", { method: "PUT", body: JSON.stringify({ api_key: apiKey }) });
  }

  getRunPodStatus() {
    return this.request("/api/runpod/status");
  }

  listRunPodWorkflows() {
    return this.request("/api/runpod/workflows");
  }

  getRunPodWorkflow(presetId) {
    return this.request(`/api/runpod/workflows/${encodeURIComponent(presetId)}`);
  }
  getRunPodWorkflowAvailability(presetId) { return this.request(`/api/runpod/workflows/${encodeURIComponent(presetId)}/availability`); }

  listComfyUiPromptPresets() { return this.request("/api/comfyui/prompt-presets"); }
  generateComfyUiPrompt({ filename, imageBase64 }) { return this.request("/api/comfyui/generate-prompt", { method: "POST", body: JSON.stringify({ filename, image_base64: imageBase64 }) }); }

  listRunPodDataCenters() {
    return this.request("/api/runpod/datacenters");
  }

  listRunPodNetworkVolumes() {
    return this.request("/api/runpod/network-volumes");
  }

  getRunPodNetworkVolume(volumeId) {
    return this.request(`/api/runpod/network-volumes/${encodeURIComponent(volumeId)}`);
  }

  listRunPodGpus(dataCenterId = "") {
    const query = dataCenterId ? `?data_center_id=${encodeURIComponent(dataCenterId)}` : "";
    return this.request(`/api/runpod/gpus${query}`);
  }

  getRunPodGpuWatch() { return this.request("/api/runpod/gpu-watch"); }
  configureRunPodGpuWatch({ enabled, gpuIds, intervalSeconds }) {
    return this.request("/api/runpod/gpu-watch", { method: "PUT", body: JSON.stringify({ enabled, gpu_ids: gpuIds, interval_seconds: intervalSeconds }) });
  }
  checkRunPodGpuWatch() { return this.request("/api/runpod/gpu-watch/check", { method: "POST" }); }
  getRunPodGpuHistorySummary() { return this.request("/api/runpod/gpu-watch/history/summary"); }

  createRunPodPod({ name, gpuId }) {
    return this.request("/api/runpod/pods", {
      method: "POST",
      body: JSON.stringify({ name, gpu_id: gpuId }),
    });
  }

  startRunPodPod(podId) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}/start`, { method: "POST" });
  }

  stopRunPodPod(podId) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}/stop`, { method: "POST" });
  }

  terminateRunPodPod(podId) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}`, { method: "DELETE" });
  }

  getRunPodComfyUiHealth(podId) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}/comfyui/health`);
  }

  queueRunPodComfyUiPrompt(podId, workflow, { mediaName = "", mediaKind = "", mediaLoaderId = "" } = {}) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}/comfyui/prompt`, {
      method: "POST",
      body: JSON.stringify({ workflow, media_name: mediaName, media_kind: mediaKind, media_loader_id: mediaLoaderId }),
    });
  }

  uploadRunPodComfyUiImage(podId, { filename, dataBase64, overwrite = true }) {
    return this.uploadRunPodComfyUiMedia(podId, { filename, dataBase64, overwrite });
  }

  uploadRunPodComfyUiMedia(podId, { filename, dataBase64, overwrite = true }) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}/comfyui/upload-media`, {
      method: "POST",
      body: JSON.stringify({ filename, data_base64: dataBase64, overwrite }),
    });
  }

  getRunPodComfyUiHistory(podId, promptId) {
    return this.request(`/api/runpod/pods/${encodeURIComponent(podId)}/comfyui/history/${encodeURIComponent(promptId)}`);
  }

  listRunPodBatches() {
    return this.request("/api/runpod/batches");
  }

  createRunPodBatch({ workflow, mediaLoaderId = "", autoDeploy = true, autoShutdown = true, minVramGb = 0, workflowId = "", creativePrompt = "" }) {
    return this.request("/api/runpod/batches", {
      method: "POST",
      body: JSON.stringify({
        workflow,
        media_loader_id: mediaLoaderId,
        auto_deploy: autoDeploy,
        auto_shutdown: autoShutdown,
        min_vram_gb: minVramGb,
        workflow_id: workflowId,
        creative_prompt: creativePrompt,
      }),
    });
  }

  addRunPodBatchItem(batchId, { filename, dataBase64 }) {
    return this.request(`/api/runpod/batches/${encodeURIComponent(batchId)}/items`, {
      method: "POST",
      body: JSON.stringify({ filename, data_base64: dataBase64 }),
    });
  }

  startRunPodBatch(batchId) {
    return this.request(`/api/runpod/batches/${encodeURIComponent(batchId)}/start`, { method: "POST" });
  }

  cancelRunPodBatch(batchId) {
    return this.request(`/api/runpod/batches/${encodeURIComponent(batchId)}/cancel`, { method: "POST" });
  }

  deleteProjectSecret() {
    return this.request("/api/secrets/project", { method: "DELETE" });
  }

  deleteDiscordBotSecret() {
    return this.request("/api/secrets/discord-bot", { method: "DELETE" });
  }

  deleteAccordiAdminSecret() {
    return this.request("/api/secrets/accordi-admin", { method: "DELETE" });
  }

  setAgentSecret(agentId, apiKey) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/secret`, {
      method: "PUT",
      body: JSON.stringify({ api_key: apiKey }),
    });
  }

  deleteAgentSecret(agentId) {
    return this.request(`/api/agents/${encodeURIComponent(agentId)}/secret`, { method: "DELETE" });
  }

  listProjects() {
    return this.request("/api/projects");
  }

  getVintedReports(days = 30, limit = 200) {
    return this.request(`/api/vinted/reports?days=${encodeURIComponent(days)}&limit=${encodeURIComponent(limit)}`);
  }

  getLinkedInPosts(search = "", limit = 500) {
    return this.request(`/api/linkedin/posts?search=${encodeURIComponent(search)}&limit=${encodeURIComponent(limit)}`);
  }

  getLinkedInPost(postId) {
    return this.request(`/api/linkedin/posts/${encodeURIComponent(postId)}`);
  }

  archiveLinkedInMedia(postId, mediaIndex, poster = false) {
    return this.request(`/api/linkedin/posts/${encodeURIComponent(postId)}/media/${encodeURIComponent(mediaIndex)}/archive?poster=${poster}`, { method: "POST" });
  }

  rewriteLinkedInPost(postId, prompt = "") {
    return this.request(`/api/linkedin/posts/${encodeURIComponent(postId)}/rewrite`, {
      method: "POST", body: JSON.stringify({ prompt }),
    });
  }

  getLinkedInPublisherStatus() {
    return this.request("/api/linkedin/publisher/status");
  }

  getLinkedInDrafts() {
    return this.request("/api/linkedin/publisher/drafts");
  }

  attachLinkedInDraftSourceImage(draftId) {
    return this.request(`/api/linkedin/publisher/drafts/${encodeURIComponent(draftId)}/source-image`, { method: "POST" });
  }

  createLinkedInDraft(body, sourcePostId = "") {
    return this.request("/api/linkedin/publisher/drafts", {
      method: "POST", body: JSON.stringify({ body, source_post_id: sourcePostId }),
    });
  }

  updateLinkedInDraft(draftId, body) {
    return this.request(`/api/linkedin/publisher/drafts/${encodeURIComponent(draftId)}`, {
      method: "PUT", body: JSON.stringify({ body }),
    });
  }

  publishLinkedInDraft(draftId, expectedBody) {
    return this.request(`/api/linkedin/publisher/drafts/${encodeURIComponent(draftId)}/publish`, {
      method: "POST", headers: { "X-Agent-Lab-Confirm": "publish" },
      body: JSON.stringify({ expected_body: expectedBody }),
    });
  }

  getVintedCompetitorReport(memberId, limit = 5000) {
    return this.request(`/api/vinted/reports/competitors/${encodeURIComponent(memberId)}?limit=${encodeURIComponent(limit)}`);
  }

  checkVintedCompetitorSales(memberId, category = "") {
    const query = category ? `?category=${encodeURIComponent(category)}` : "";
    return this.request(`/api/vinted/reports/competitors/${encodeURIComponent(memberId)}/check-sales${query}`, {
      method: "POST",
    });
  }

  createVintedReportSourcingBatch(items, maxResults = 40) {
    return this.request("/api/vinted/reports/sourcing-batch", {
      method: "POST",
      body: JSON.stringify({ items, max_results: maxResults }),
    });
  }

  saveVintedOwnedProfile(profileUrl, displayName = "") {
    return this.request("/api/vinted/owned-profiles", {
      method: "POST",
      body: JSON.stringify({ profile_url: profileUrl, display_name: displayName }),
    });
  }

  removeVintedOwnedProfile(memberId) {
    return this.request(`/api/vinted/owned-profiles/${encodeURIComponent(memberId)}`, {
      method: "DELETE",
    });
  }

  ignoreVintedOwnedProfileItem(memberId, itemId) {
    return this.request(`/api/vinted/owned-profiles/${encodeURIComponent(memberId)}/items/${encodeURIComponent(itemId)}`, {
      method: "DELETE",
    });
  }

  createProjectJob(job) {
    return this.request("/api/project-jobs", {
      method: "POST",
      body: JSON.stringify(job),
    });
  }

  listProjectJobs() {
    return this.request("/api/project-jobs");
  }

  cancelProjectJob(jobId) {
    return this.request(`/api/project-jobs/${encodeURIComponent(jobId)}`, {
      method: "DELETE",
    });
  }

  listProjectPresets(projectId = "") {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return this.request(`/api/project-presets${query}`);
  }

  createProjectPreset(preset) {
    return this.request("/api/project-presets", {
      method: "POST",
      body: JSON.stringify(preset),
    });
  }

  deleteProjectPreset(presetId) {
    return this.request(`/api/project-presets/${encodeURIComponent(presetId)}`, {
      method: "DELETE",
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

  reportError(payload) {
    return fetch("/api/diagnostics/report-error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
      keepalive: true,
    })
      .then((response) => response.json().catch(() => ({ accepted: response.ok })))
      .catch(() => undefined);
  }
}

function formatErrorDetail(detail) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map(formatValidationItem).join("; ");
  }
  if (detail && typeof detail === "object") {
    return detail.message ?? detail.msg ?? JSON.stringify(detail);
  }
  return String(detail ?? "Request failed");
}

function formatValidationItem(item) {
  if (typeof item === "string") {
    return item;
  }
  if (!item || typeof item !== "object") {
    return String(item);
  }
  const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
  const message = item.msg ?? item.message ?? JSON.stringify(item);
  return location ? `${location}: ${message}` : String(message);
}
