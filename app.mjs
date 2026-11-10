import * as THREE from "three";
import { AgentNetwork } from "./src/agentProtocol.mjs";
import {
  AgentWorld,
  addRoomToLayout,
  addWorkstationToLayout,
  doorLayout,
  findAvailableRoomRect,
  isDoorTile,
  isInsideTile,
  pruneDisconnectedDoorPaths,
  removeRoomFromLayout,
  roomConfig,
  roomCells,
  roomLayout,
  resetRoomLayout,
  setDoorAt,
  setDoorLayout,
  setRoomCell,
  setRoomLayout,
  setWorkstationLayout,
  tileEquals,
  tileKey,
  tileToWorld,
  workstationPresets,
  workstations,
  worldToTile,
} from "./src/agentWorld.mjs";
import { defaultScenario } from "./src/scenarios.mjs";
import { RuntimeClient } from "./src/runtimeClient.mjs?v=owned-item-ignore-1";
import { LayoutHistory } from "./src/layoutHistory.mjs";
import { JobNotificationState } from "./src/jobNotifications.mjs";

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
const roomDetails = document.querySelector("#room-details");
const selectedRoomName = document.querySelector("#selected-room-name");
const selectedRoomMetrics = document.querySelector("#selected-room-metrics");
const selectedRoomStations = document.querySelector("#selected-room-stations");
const selectedRoomAgents = document.querySelector("#selected-room-agents");
const activeWorkCount = document.querySelector("#active-work-count");
const activeWorkList = document.querySelector("#active-work-list");
const activeWorkAllButton = document.querySelector("#active-work-all");
const runtimeStatus = document.querySelector("#runtime-status");
const addAgentButton = document.querySelector("#add-agent");
const layoutToggle = document.querySelector("#layout-toggle");
const layoutEditor = document.querySelector("#layout-editor");
const layoutEditorStatus = document.querySelector("#layout-editor-status");
const layoutEditorHint = document.querySelector("#layout-editor-hint");
const editorCloseButton = document.querySelector("#editor-close");
const undoLayoutButton = document.querySelector("#undo-layout");
const redoLayoutButton = document.querySelector("#redo-layout");
const roomDrawToggle = document.querySelector("#room-draw-toggle");
const rotateStationButton = document.querySelector("#rotate-station");
const doorToggle = document.querySelector("#door-toggle");
const addRoomButton = document.querySelector("#add-room");
const deleteRoomButton = document.querySelector("#delete-room");
const workstationPresetSelect = document.querySelector("#workstation-preset");
const workstationAgentSelect = document.querySelector("#workstation-agent");
const workstationAgentTable = document.querySelector("#workstation-agent-table");
const workstationAgentCount = document.querySelector("#workstation-agent-count");
const addWorkstationButton = document.querySelector("#add-workstation");
const resetLayoutButton = document.querySelector("#reset-layout");
const themeToggle = document.querySelector("#theme-toggle");
const atmosphereToggle = document.querySelector("#atmosphere-toggle");
const worldClock = document.querySelector("#world-clock");
const worldClockTime = document.querySelector("#world-clock-time");
const worldClockDate = document.querySelector("#world-clock-date");
const systemSettingsButton = document.querySelector("#system-settings");
const reportsDashboardButton = document.querySelector("#reports-dashboard");
const monitoringDashboardButton = document.querySelector("#monitoring-dashboard");
const reportDialog = document.querySelector("#report-dialog");
const reportPeriod = document.querySelector("#report-period");
const reportRefreshButton = document.querySelector("#report-refresh");
const reportStatus = document.querySelector("#report-status");
const reportMetrics = document.querySelector("#report-metrics");
const reportSalesChart = document.querySelector("#report-sales-chart");
const reportSalesCaption = document.querySelector("#report-sales-caption");
const reportStatusChart = document.querySelector("#report-status-chart");
const reportSearchRanking = document.querySelector("#report-search-ranking");
const reportArticles = document.querySelector("#report-articles");
const reportSourcingSelectedButton = document.querySelector("#report-sourcing-selected");
const reportClearSelectionButton = document.querySelector("#report-clear-selection");
const reportSelectedCount = document.querySelector("#report-selected-count");
const reportSaleTime = document.querySelector("#report-sale-time");
const reportFilterButtons = Array.from(document.querySelectorAll("[data-report-filter]"));
const reportTabButtons = Array.from(document.querySelectorAll("[data-report-tab]"));
const reportPanels = Array.from(document.querySelectorAll("[data-report-panel]"));
const monitoringStatus = document.querySelector("#monitoring-status");
const monitoringJobs = document.querySelector("#monitoring-jobs");
const monitoringCount = document.querySelector("#report-monitoring-count");
const monitoringRefreshButton = document.querySelector("#monitoring-refresh");
const reportAiNewsCount = document.querySelector("#report-ai-news-count");
const reportAiNewsMetrics = document.querySelector("#report-ai-news-metrics");
const reportAiNewsArchive = document.querySelector("#report-ai-news-archive");
const reportAiNewsDetail = document.querySelector("#report-ai-news-detail");
const reportAiNewsRefresh = document.querySelector("#report-ai-news-refresh");
const reportLinkedInCount = document.querySelector("#report-linkedin-count");
const reportLinkedInRefresh = document.querySelector("#report-linkedin-refresh");
const reportLinkedInSearch = document.querySelector("#report-linkedin-search");
const reportLinkedInFilter = document.querySelector("#report-linkedin-filter");
const reportLinkedInStatus = document.querySelector("#report-linkedin-status");
const reportLinkedInList = document.querySelector("#report-linkedin-list");
const reportLinkedInDetail = document.querySelector("#report-linkedin-detail");
const linkedinPublisherRefresh = document.querySelector("#linkedin-publisher-refresh");
const linkedinPublisherStatus = document.querySelector("#linkedin-publisher-status");
const linkedinPublisherAccount = document.querySelector("#linkedin-publisher-account");
const linkedinPublisherNewBody = document.querySelector("#linkedin-publisher-new-body");
const linkedinPublisherCreateDraft = document.querySelector("#linkedin-publisher-create-draft");
const linkedinPublisherDrafts = document.querySelector("#linkedin-publisher-drafts");
let aiNewsBriefings = [];
let selectedAiNewsId = "";
const reportCompetitors = document.querySelector("#report-competitors");
const reportCompetitorDetail = document.querySelector("#report-competitor-detail");
const reportCompetitorCount = document.querySelector("#report-competitor-count");
const reportCompetitorStatus = document.querySelector("#report-competitor-status");
const reportProcacciatoreCount = document.querySelector("#report-procacciatore-count");
const reportProcacciatoreSummary = document.querySelector("#report-procacciatore-summary");
const reportProcacciatoreChecked = document.querySelector("#report-procacciatore-checked");
const reportProcacciatoreTop = document.querySelector("#report-procacciatore-top");
const reportProcacciatoreBrands = document.querySelector("#report-procacciatore-brands");
const reportProcacciatoreBrandNote = document.querySelector("#report-procacciatore-brand-note");
const reportProcacciatoreArticles = document.querySelector("#report-procacciatore-articles");
const reportProcacciatoreStatus = document.querySelector("#report-procacciatore-status");
const reportKeywords = document.querySelector("#report-keywords");
const reportKeywordCount = document.querySelector("#report-keyword-count");
const reportKeywordSearch = document.querySelector("#report-keyword-search");
const reportKeywordSummary = document.querySelector("#report-keyword-summary");
const reportOwnedProfiles = document.querySelector("#report-owned-profiles");
const reportOwnedCount = document.querySelector("#report-owned-count");
const reportOwnedForm = document.querySelector("#report-owned-form");
const reportOwnedName = document.querySelector("#report-owned-name");
const reportOwnedUrl = document.querySelector("#report-owned-url");
const reportOwnedError = document.querySelector("#report-owned-error");
const reportOwnedSummary = document.querySelector("#report-owned-summary");
const reportOwnedInventoryChart = document.querySelector("#report-owned-inventory-chart");
const reportOwnedSpeedChart = document.querySelector("#report-owned-speed-chart");
const reportOwnedStatus = document.querySelector("#report-owned-status");
const reportOwnedSearch = document.querySelector("#report-owned-search");
const agentDialog = document.querySelector("#agent-dialog");
const agentForm = document.querySelector("#agent-form");
const agentFormError = document.querySelector("#agent-form-error");
const agentWorkstationPreset = document.querySelector("#agent-workstation-preset");
const configureAgentButton = document.querySelector("#configure-agent");
const systemSettingsDialog = document.querySelector("#system-settings-dialog");
const systemSettingsForm = document.querySelector("#system-settings-form");
const systemSettingsError = document.querySelector("#system-settings-error");
const systemProjectKeyStatus = document.querySelector("#system-project-key-status");
const systemDiscordBotStatus = document.querySelector("#system-discord-bot-status");
const systemAccordiAdminStatus = document.querySelector("#system-accordi-admin-status");
const systemRunPodStatus = document.querySelector("#system-runpod-status");
const runPodActionStatus = document.querySelector("#runpod-action-status");
const runPodRefreshPodsButton = document.querySelector("#runpod-refresh-pods");
const runPodListVolumesButton = document.querySelector("#runpod-list-volumes");
const runPodListDataCentersButton = document.querySelector("#runpod-list-datacenters");
const runPodListGpusButton = document.querySelector("#runpod-list-gpus");
const runPodCreatePodButton = document.querySelector("#runpod-create-pod");
const runPodStartPodButton = document.querySelector("#runpod-start-pod");
const runPodStopPodButton = document.querySelector("#runpod-stop-pod");
const runPodTerminatePodButton = document.querySelector("#runpod-terminate-pod");
const runPodComfyUiHealthButton = document.querySelector("#runpod-comfyui-health");
const runPodQueueWorkflowButton = document.querySelector("#runpod-queue-workflow");
const agentSettingsDialog = document.querySelector("#agent-settings-dialog");
const agentSettingsForm = document.querySelector("#agent-settings-form");
const agentSettingsError = document.querySelector("#agent-settings-error");
const quickChat = document.querySelector("#agent-quick-chat");
const quickChatAgent = document.querySelector("#quick-chat-agent");
const quickChatInput = document.querySelector("#quick-chat-input");
const quickChatStatus = document.querySelector("#quick-chat-status");
const quickChatHistory = document.querySelector("#quick-chat-history");
const quickChatDiscussion = document.querySelector("#quick-chat-discussion");
const quickChatTabs = Array.from(document.querySelectorAll("[data-quick-chat-tab]"));
const projectKeyStatus = document.querySelector("#project-key-status");
const agentKeyStatus = document.querySelector("#agent-key-status");
const agentActionDialog = document.querySelector("#agent-action-dialog");
const agentActionTitle = document.querySelector("#agent-action-title");
const agentActionRole = document.querySelector("#agent-action-role");
const agentActionStatus = document.querySelector("#agent-action-status");
const workOptions = document.querySelector("#work-options");
const runPodOptions = document.querySelector("#runpod-options");
const appiumOptions = document.querySelector("#appium-options");
const appiumEnabledSelect = document.querySelector("#appium-enabled");
const appiumServerUrlInput = document.querySelector("#appium-server-url");
const appiumAdbPathInput = document.querySelector("#appium-adb-path");
const appiumIosToolInput = document.querySelector("#appium-ios-tool");
const appiumSaveButton = document.querySelector("#appium-save-settings");
const appiumStartButton = document.querySelector("#appium-start-server");
const appiumStopButton = document.querySelector("#appium-stop-server");
const appiumRefreshButton = document.querySelector("#appium-refresh-status");
const appiumServerCard = document.querySelector("#appium-server-card");
const appiumServerState = document.querySelector("#appium-server-state");
const appiumServerDetail = document.querySelector("#appium-server-detail");
const appiumAdbCard = document.querySelector("#appium-adb-card");
const appiumDeviceCount = document.querySelector("#appium-device-count");
const appiumAdbDetail = document.querySelector("#appium-adb-detail");
const appiumDeviceList = document.querySelector("#appium-device-list");
const appiumActionStatus = document.querySelector("#appium-action-status");
const appiumTargetDevice = document.querySelector("#appium-target-device");
const appiumInstalledApps = document.querySelector("#appium-installed-app");
const appiumListAppsButton = document.querySelector("#appium-list-apps");
const appiumLaunchAppButton = document.querySelector("#appium-launch-app");
const appiumEndSessionButton = document.querySelector("#appium-end-session");
const appiumSessionState = document.querySelector("#appium-session-state");
const appiumScreenPreview = document.querySelector("#appium-screen-preview");
const appiumScreenPlaceholder = document.querySelector("#appium-screen-placeholder");
const appiumScreenState = document.querySelector("#appium-screen-state");
let appiumScreenTimer = null;
let appiumScreenRequestPending = false;
let appiumScreenObjectUrl = "";
const runPodNetworkVolumeInput = document.querySelector("#runpod-network-volume-id");
const runPodDataCenterInput = document.querySelector("#runpod-data-center-id");
const runPodTemplateInput = document.querySelector("#runpod-template-id");
const runPodContainerImageInput = document.querySelector("#runpod-container-image");
const runPodGpuSelect = document.querySelector("#runpod-preferred-gpu");
const runPodMaxHourlyCostInput = document.querySelector("#runpod-max-hourly-cost");
const runPodVolumeMountInput = document.querySelector("#runpod-volume-mount-path");
const runPodComfyUiPortInput = document.querySelector("#runpod-comfyui-port");
const runPodIdleActionSelect = document.querySelector("#runpod-idle-action");
const runPodSaveDeploymentButton = document.querySelector("#runpod-save-deployment");
const runPodNameInput = document.querySelector("#runpod-pod-name");
const runPodIdInput = document.querySelector("#runpod-pod-id");
const runPodPicker = document.querySelector("#runpod-pod-picker");
const runPodWorkflowInput = document.querySelector("#runpod-workflow-json");
const runPodWorkflowFileInput = document.querySelector("#runpod-workflow-file");
const runPodLoadWorkflowButton = document.querySelector("#runpod-load-workflow");
const runPodWorkflowStatus = document.querySelector("#runpod-workflow-status");
const runPodWorkflowPresetSelect = document.querySelector("#runpod-workflow-preset");
const runPodLoadWorkflowPresetButton = document.querySelector("#runpod-load-workflow-preset");
const runPodMediaLoaderSelect = document.querySelector("#runpod-media-loader");
const runPodMediaFileInput = document.querySelector("#runpod-media-file");
const runPodUploadMediaButton = document.querySelector("#runpod-upload-media");
const runPodUploadStatus = document.querySelector("#runpod-upload-status");
const runPodJobResults = document.querySelector("#runpod-job-results");
const runPodBatchFilesInput = document.querySelector("#runpod-batch-files");
const runPodStartBatchButton = document.querySelector("#runpod-start-batch");
const runPodRefreshBatchesButton = document.querySelector("#runpod-refresh-batches");
const runPodBatchResults = document.querySelector("#runpod-batch-results");
const runPodGpuWatchInterval = document.querySelector("#runpod-gpu-watch-interval");
const runPodGpuWatchGpus = document.querySelector("#runpod-gpu-watch-gpus");
const runPodGpuWatchEnable = document.querySelector("#runpod-gpu-watch-enable");
const runPodGpuWatchCheck = document.querySelector("#runpod-gpu-watch-check");
const runPodGpuWatchStatus = document.querySelector("#runpod-gpu-watch-status");
const creativePromptPreset = document.querySelector("#creative-prompt-preset");
const creativePromptImage = document.querySelector("#creative-prompt-image");
const creativeGeneratePrompt = document.querySelector("#creative-generate-prompt");
const creativePromptText = document.querySelector("#creative-prompt-text");
const creativePromptStatus = document.querySelector("#creative-prompt-status");
const runPodCardManager = document.querySelector("#runpod-card-manager");
const runPodCardManagerDetail = document.querySelector("#runpod-card-manager-detail");
const runPodCardVolume = document.querySelector("#runpod-card-volume");
const runPodCardVolumeDetail = document.querySelector("#runpod-card-volume-detail");
const runPodCardGpus = document.querySelector("#runpod-card-gpus");
const runPodCardGpusDetail = document.querySelector("#runpod-card-gpus-detail");
const runPodCardPods = document.querySelector("#runpod-card-pods");
const runPodCardPodsDetail = document.querySelector("#runpod-card-pods-detail");
const runPodVolumeDataCenters = new Map();
let runPodStatusRefreshTimer = null;
let runPodBatchPollTimer = null;
let creativePromptPresets = [];
let runPodDashboardSnapshot = { settings: null, volume: null, gpus: [] };
let runPodUploadedMedia = { name: "", kind: "" };
let runPodWorkflowLoaders = [];
const runPodJobsStorageKey = "agent-lab.runpod-jobs.v1";
let runPodJobs = [];
let runPodJobPollTimer = null;
const browserOptions = document.querySelector("#browser-options");
const browserSessionSelect = document.querySelector("#browser-session");
const browserUrlInput = document.querySelector("#browser-url");
const browserSelectorInput = document.querySelector("#browser-selector");
const browserTextInput = document.querySelector("#browser-text");
const browserValueInput = document.querySelector("#browser-value");
const browserModeSelect = document.querySelector("#browser-mode");
const browserBackendSelect = document.querySelector("#browser-backend");
const browserStatus = document.querySelector("#browser-status");
const browserRefreshSessionsButton = document.querySelector("#browser-refresh-sessions");
const browserOpenSessionButton = document.querySelector("#browser-open-session");
const browserCurrentUrlButton = document.querySelector("#browser-current-url");
const browserSnapshotButton = document.querySelector("#browser-snapshot");
const browserGotoButton = document.querySelector("#browser-goto");
const browserClickTextButton = document.querySelector("#browser-click-text");
const browserClickSelectorButton = document.querySelector("#browser-click-selector");
const browserTypeButton = document.querySelector("#browser-type");
const browserExtractButton = document.querySelector("#browser-extract");
const browserCloseButton = document.querySelector("#browser-close");
const projectDialog = document.querySelector("#project-dialog");
const projectForm = document.querySelector("#project-form");
const projectDialogKicker = projectDialog?.querySelector(".section-label");
const projectDialogTitle = document.querySelector("#project-dialog-title");
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
const projectJobFilters = document.querySelector("#project-job-filters");
const projectJobFilterButtons = Array.from(document.querySelectorAll("[data-job-filter]"));
const wikiProposalList = document.querySelector("#wiki-proposal-list");
const wikiProposalCount = document.querySelector("#wiki-proposal-count");
const memoryCoreChatButton = document.querySelector("#memory-core-chat");
const memoryCoreSettingsButton = document.querySelector("#memory-core-settings");
const refreshWikiProposalsButton = document.querySelector("#refresh-wiki-proposals");
const wikiSearchQuery = document.querySelector("#wiki-search-query");
const searchWikiPagesButton = document.querySelector("#search-wiki-pages");
const refreshWikiPagesButton = document.querySelector("#refresh-wiki-pages");
const runWikiMaintenanceButton = document.querySelector("#run-wiki-maintenance");
const wikiPageList = document.querySelector("#wiki-page-list");
const wikiPageContent = document.querySelector("#wiki-page-content");
const taskThreadCount = document.querySelector("#task-thread-count");
const refreshTaskThreadsButton = document.querySelector("#refresh-task-threads");
const taskThreadList = document.querySelector("#task-thread-list");
const taskThreadContent = document.querySelector("#task-thread-content");
const projectPanelTabs = Array.from(document.querySelectorAll("[data-panel-tab]"));
const projectPanels = Array.from(document.querySelectorAll("[data-project-panel]"));
const projectOutputSummary = document.querySelector("#project-output-summary");
const projectOutputView = document.querySelector("#project-output-view");
const projectOutputMeta = document.querySelector("#project-output-meta");
const projectOutputHead = document.querySelector("#project-output-head");
const projectOutputRows = document.querySelector("#project-output-rows");
const projectGatewayHeaderGrid = projectDialog?.querySelector(".form-grid");
const projectPresetsSection = projectDialog?.querySelector(".project-presets");
const projectParametersSection = projectParameters?.closest(".settings-section");
const projectDialogActions = projectDialog?.querySelector(".dialog-actions");
const runProjectActionButton = document.querySelector("#run-project-action");

const LAYOUT_STORAGE_KEY = "agent-protocol-lab-layout-v1";
const PROJECT_LIST_PARAMETERS_STORAGE_PREFIX = "agent-protocol-lab-project-list-parameters-v1";

function loadStoredLayout() {
  try {
    const raw = window.localStorage?.getItem(LAYOUT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_error) {
    return {};
  }
}

function migrateStoredDefaultMainRoom(layout) {
  const rooms = Array.isArray(layout?.rooms) ? layout.rooms : [];
  const main = rooms.find((room) => room?.id === "main");
  if (!main) return layout;
  const isPreviousDefault = Number(main.col) === 5 && Number(main.row) === 4
    && Number(main.columns) === 14 && Number(main.rows) === 10;
  if (!isPreviousDefault) return layout;

  const previousDefault = new Set();
  for (let row = 4; row < 14; row += 1) {
    for (let col = 5; col < 19; col += 1) previousDefault.add(`${col},${row}`);
  }
  const cells = roomCells(main);
  if (cells.length !== previousDefault.size || cells.some((tile) => !previousDefault.has(`${tile.col},${tile.row}`))) {
    return layout;
  }
  const expandedCells = [...cells];
  const occupied = new Set();
  for (const room of rooms) {
    if (room.id === "main") continue;
    for (const tile of roomCells(room)) occupied.add(`${tile.col},${tile.row}`);
  }
  for (const tile of layout.doors ?? []) occupied.add(`${Number(tile.col)},${Number(tile.row)}`);
  const included = new Set(expandedCells.map((tile) => `${tile.col},${tile.row}`));
  let changed = true;
  while (changed) {
    changed = false;
    for (let row = 2; row < 16; row += 1) {
      for (let col = 3; col < 21; col += 1) {
        const key = `${col},${row}`;
        if (included.has(key) || occupied.has(key)) continue;
        const touchesRoom = [
          `${col - 1},${row}`, `${col + 1},${row}`,
          `${col},${row - 1}`, `${col},${row + 1}`,
        ].some((neighbor) => included.has(neighbor));
        if (!touchesRoom) continue;
        included.add(key);
        expandedCells.push({ col, row });
        changed = true;
      }
    }
  }
  if (expandedCells.length === cells.length) return layout;
  return {
    ...layout,
    rooms: rooms.map((room) => room.id === "main" ? { ...main, cells: expandedCells } : room),
  };
}

function ensureInfrastructureRoom(layout) {
  const sourceRooms = Array.isArray(layout?.rooms) && layout.rooms.length
    ? layout.rooms.map((room) => ({ ...room, cells: Array.isArray(room.cells) ? room.cells.map((cell) => ({ ...cell })) : room.cells }))
    : roomLayout.map((room) => ({ ...room, cells: roomCells(room).map((cell) => ({ ...cell })) }));
  if (sourceRooms.some((room) => room.id === "media-infrastructure")) {
    return layout;
  }

  const mainRoom = sourceRooms.find((room) => room.id === "main") ?? sourceRooms[0];
  const mainCells = roomCells(mainRoom);
  if (!mainRoom || mainCells.length < 32) {
    return layout;
  }
  const maxCol = Math.max(...mainCells.map((cell) => cell.col));
  const maxRow = Math.max(...mainCells.map((cell) => cell.row));
  const doorTile = { col: maxCol - 3, row: maxRow - 2 };
  const infrastructureCells = [];
  for (let row = maxRow - 3; row <= maxRow; row += 1) {
    for (let col = maxCol - 3; col <= maxCol; col += 1) {
      if (tileEquals({ col, row }, doorTile)) continue;
      infrastructureCells.push({ col, row });
    }
  }
  const infrastructureKeys = new Set(infrastructureCells.map((cell) => tileKey(cell)));
  if (!infrastructureCells.every((cell) => mainCells.some((candidate) => tileEquals(candidate, cell)))) {
    return layout;
  }

  const remainingMainCells = mainCells.filter((cell) => !infrastructureKeys.has(tileKey(cell)));
  const stationTile = { col: maxCol - 2, row: maxRow - 2 };
  const nextLayout = {
    ...(layout ?? {}),
    rooms: sourceRooms.map((room) => room.id === mainRoom.id
      ? { ...room, cells: remainingMainCells }
      : room
    ).concat({
      id: "media-infrastructure",
      label: "Media Infrastructure",
      col: maxCol - 3,
      row: maxRow - 3,
      columns: 4,
      rows: 4,
      cells: infrastructureCells,
      color: "#8b5cf6",
    }),
    doors: [...(layout?.doors ?? []), doorTile].filter((tile, index, doors) =>
      doors.findIndex((candidate) => tileEquals(candidate, tile)) === index
    ),
    stations: {
      ...(layout?.stations ?? {}),
      "runpod-infrastructure": stationTile,
    },
    agents: {
      ...(layout?.agents ?? {}),
      "runpod-manager": stationTile,
    },
  };
  return nextLayout;
}

function expandMainRoomForAgentCapacity(layout) {
  const rooms = Array.isArray(layout?.rooms) ? layout.rooms : [];
  const main = rooms.find((room) => room?.id === "main");
  if (!main) return layout;
  const current = roomCells(main);
  if (current.length >= 300) return layout;
  const occupied = new Set(rooms.filter((room) => room.id !== "main").flatMap((room) => roomCells(room)).map(tileKey));
  const cells = [];
  for (let row = 1; row <= 16; row += 1) for (let col = 1; col <= 22; col += 1) {
    const tile = { col, row };
    if (!occupied.has(tileKey(tile))) cells.push(tile);
  }
  return { ...layout, rooms: rooms.map((room) => room.id === "main" ? { ...room, col: 1, row: 1, columns: 22, rows: 16, cells } : room) };
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
  if (Array.isArray(layout.customWorkstations)) {
    setWorkstationLayout(layout.customWorkstations);
  }
  for (const [stationId, storedTile] of Object.entries(layout.stations ?? {})) {
    const tile = tileFromStored(storedTile);
    const station = workstations.find((item) => item.id === stationId);
    if (station) station.rotation = normalizeYaw(storedTile?.rotation);
    if (station && tile && isInsideTile(tile)) {
      station.position = tileToWorld(tile);
    }
  }
}

const rawStoredLayout = loadStoredLayout();
const storedLayout = ensureInfrastructureRoom(expandMainRoomForAgentCapacity(migrateStoredDefaultMainRoom(rawStoredLayout)));
if (storedLayout !== rawStoredLayout) {
  try {
    window.localStorage?.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(storedLayout));
  } catch (_error) {
    // The expanded in-memory layout still applies when storage is unavailable.
  }
}
applyStoredLayoutBeforeWorld(storedLayout);

const network = new AgentNetwork(defaultScenario);
const agentWorld = new AgentWorld(network);
agentWorld.restoreAgentTiles(storedLayout.agents ?? {});
const runtimeClient = new RuntimeClient();
const runtimeSnapshots = new Map();
const runtimeTaskCache = new Map();
const runtimeDiscussionThreads = new Map();
const agentReplies = new Map();
const chatMessageIds = new Set();
const projectJobToasts = new Map();
const projectJobsCache = new Map();
const monitoringJobDefinitions = [
  {
    action: "vinted.continuous_monitoring",
    agent_id: "vinted-analyst",
    label: "Monitoraggio continuo · profili e competitor",
    parameters: {
      "profile-urls": "https://www.vinted.it/member/306388399\nhttps://www.vinted.it/member/167398536",
      "owned-profile-urls": "https://www.vinted.it/member/225753959\nhttps://www.vinted.it/member/3178210259\nhttps://www.vinted.it/member/3206490867",
      "profile-categories": "",
      "competitor-keywords": "charm, pandora",
      "competitor-category": "Gioielli donna",
      "article-interval-seconds": 5,
      "profile-interval-seconds": 3600,
      "max-items": 0,
      "max-results": 100,
      "competitor-min-likes": 18,
      "competitor-max-age-hours": 720,
      "competitor-min-price": "10",
      "discord-deal-notifications": true,
      "discord-profile-report": true,
      "daily-report-hour": 10,
      "db-path": "data/scraper.db",
      "browser-mode": "chrome_normale",
      "browser-user-data-dir": "/Users/rafael/Library/Application Support/Google/Chrome",
      "browser-profile-directory": "Default",
      "refresh-browser-profile": false,
      "max-price": "",
    },
  },
  {
    action: "vinted.deal_hunter",
    agent_id: "vinted-procacciatore",
    label: "Procacciatore · gioielli",
    parameters: {
      "deal-hunter-terms": "charm, bracciali, pandora, collane, gioielli, ciondoli, orecchini, anelli",
      "deal-hunter-category": "Gioielli donna",
      "max-results": 500,
      "deal-hunter-min-price": "15",
      "max-price": "",
      "deal-hunter-min-favorites": 20,
      "deal-hunter-max-age-hours": 24,
      "deal-hunter-loop-seconds": 5,
      "deal-hunter-url-only-discord": false,
      "skip-login-required": true,
      "auto-submit-offers": false,
      "discord-deal-notifications": true,
      "browser-mode": "chrome_normale",
      "browser-user-data-dir": "/Users/rafael/Library/Application Support/Google/Chrome",
      "browser-profile-directory": "Default",
    },
  },
];
const activeProjectJobs = new Map();
const activityJobCache = new Map();
const layoutHistory = new LayoutHistory(50);
const jobNotificationState = new JobNotificationState();
const gameNotificationKeys = new Set();
const taskUiNotices = new Set();
const threadUiNotices = new Set();
const projectJobAgentMessages = new Map();
const projectJobUiNotices = new Set();
const wikiProposalsCache = new Map();
const wikiPagesCache = new Map();
let availableProjects = [];
let availableProjectPresets = [];
let monitoringAutoStartTriggered = false;
let monitoringDashboardRefreshTimer = 0;
let projectPanel = "output";
let projectDialogMode = "gateway";
let projectJobFilter = "all";
let selectedTaskThreadId = "";
let unreadCompletedProjectJobs = jobNotificationState.unreadIds.size;
let reportSnapshot = null;
let reportArticleFilter = "all";
let reportSaleTimeFilter = "all";
let reportSelectedArticleKeys = new Set();
let reportCompetitorStatusFilter = "all";
let reportSelectedCompetitorId = "";
let reportCompetitorItemFilter = "all";
const reportCompetitorDetails = new Map();
const reportCompetitorSaleChecks = new Set();
const reportCompetitorSaleCheckJobs = new Map();
let reportOwnedStatusFilter = "all";
let reportOwnedSearchFilter = "";
let reportProcacciatoreStatusFilter = "all";
let projectCompetitorProfiles = [];

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
const ATMOSPHERE_STORAGE_KEY = "agent-protocol-lab-atmosphere-v1";
const ATMOSPHERES = {
  daylight: {
    label: "Daylight",
    sky: 0xdaf3ff,
    ground: 0x514d57,
    hemisphereIntensity: 1.65,
    key: 0xfff1d2,
    keyIntensity: 3.2,
    fill: 0x9bc9ff,
    fillIntensity: 0.72,
    cyan: 0x86edff,
    cyanIntensity: 5.5,
    violet: 0xc4adff,
    violetIntensity: 4.0,
  },
  sunset: {
    label: "Sunset",
    sky: 0xffc59d,
    ground: 0x433044,
    hemisphereIntensity: 1.35,
    key: 0xff9a62,
    keyIntensity: 3.4,
    fill: 0xb28cff,
    fillIntensity: 0.95,
    cyan: 0xffbd82,
    cyanIntensity: 5.2,
    violet: 0xe879b6,
    violetIntensity: 6.0,
  },
  night: {
    label: "Night",
    sky: 0x657bbd,
    ground: 0x080d20,
    hemisphereIntensity: 0.82,
    key: 0x9bb8ff,
    keyIntensity: 2.05,
    fill: 0x7566dc,
    fillIntensity: 1.5,
    cyan: 0x47e5ff,
    cyanIntensity: 8.5,
    violet: 0x9674ff,
    violetIntensity: 8.0,
  },
};
const ATMOSPHERE_ORDER = Object.keys(ATMOSPHERES);
const ATMOSPHERE_MODES = ["auto", ...ATMOSPHERE_ORDER];
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

function loadStoredAtmosphere() {
  try {
    const stored = window.localStorage?.getItem(ATMOSPHERE_STORAGE_KEY);
    return stored === "auto" || Object.hasOwn(ATMOSPHERES, stored) ? stored : "auto";
  } catch (_error) {
    return "auto";
  }
}

let currentTheme = loadStoredTheme();
let currentAtmosphereMode = loadStoredAtmosphere();
let currentAtmosphere = currentAtmosphereMode === "auto"
  ? atmosphereForLocalTime(new Date())
  : currentAtmosphereMode;
let worldLights = null;

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
let layoutStroke = null;

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
let quickChatDetached = false;
let quickChatView = "chat";
let layoutMode = false;
let pendingStationPlacementId = null;
let selectedBrowserSessionId = "";
const memoryCouncilState = {
  userSignals: 0,
  memorySignals: 0,
  lastStartedAt: 0,
  lastTaskAt: 0,
  cooldownMs: 90_000,
};

function isAutoCouncilTask(task) {
  return String(task?.title || "").trim() === "Context council";
}

function queueMemoryCouncilSignal(kind = "memory", weight = 1) {
  if (!runtimeClient.connected) {
    return;
  }
  if (kind === "user") {
    memoryCouncilState.userSignals += weight;
  } else {
    memoryCouncilState.memorySignals += weight;
  }
  void maybeStartMemoryCouncil();
}

async function maybeStartMemoryCouncil() {
  if (!runtimeClient.connected) {
    return;
  }
  const now = Date.now();
  if (now - memoryCouncilState.lastStartedAt < memoryCouncilState.cooldownMs) {
    return;
  }
  const totalSignals = memoryCouncilState.userSignals + memoryCouncilState.memorySignals;
  const enoughUserContext = memoryCouncilState.userSignals >= 2 && memoryCouncilState.memorySignals >= 1;
  const enoughMemoryChurn = memoryCouncilState.memorySignals >= 3;
  if (!enoughUserContext && !enoughMemoryChurn && totalSignals < 4) {
    return;
  }

  memoryCouncilState.lastStartedAt = now;
  memoryCouncilState.userSignals = 0;
  memoryCouncilState.memorySignals = 0;

  network.triggerIntent("memory-sync");
  agentWorld.triggerIntent("memory-sync", network, { autoEnabled: autoAgents });
  network.log("Memory Core started a context council at the sync table.");
  showGameNotification({
    title: "Memory Core",
    subtitle: "Context council",
    summary: "Agents are gathering at the desk to align on recent user context and memory updates.",
    tone: "active",
    key: `memory-council-${now}`,
  });

  if (now - memoryCouncilState.lastTaskAt < 5 * 60_000) {
    updateHud();
    return;
  }

  memoryCouncilState.lastTaskAt = now;
  try {
    await runtimeClient.createTask({
      title: "Context council",
      description: [
        "Review recent user context, memory changes, notifications, and open wiki knowledge.",
        "Coordinate a short internal council between Memory Core, Orchestrator, Planner, Researcher, Builder, Critic, and Scheduler.",
        "Summarize the most useful improvements, risks, and next actions for the user.",
      ].join(" "),
      capability: "memory",
      priority: 2,
      requested_agent_id: "memory",
    });
  } catch (error) {
    setBootMessage(error.message);
  } finally {
    updateHud();
  }
}
let pendingAgentQuickChat = null;

const selectableObjects = [];
const agentVisuals = new Map();
const stationVisuals = new Map();
const ambientVisuals = [];
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

function atmosphereForLocalTime(date) {
  const hour = date.getHours();
  if (hour >= 7 && hour < 17) return "daylight";
  if ((hour >= 6 && hour < 7) || (hour >= 17 && hour < 20)) return "sunset";
  return "night";
}

function applyAtmosphere(mode, options = {}) {
  currentAtmosphereMode = mode === "auto" || Object.hasOwn(ATMOSPHERES, mode) ? mode : "auto";
  currentAtmosphere = currentAtmosphereMode === "auto"
    ? atmosphereForLocalTime(new Date())
    : currentAtmosphereMode;
  const preset = ATMOSPHERES[currentAtmosphere];
  if (worldLights) {
    worldLights.hemisphere.color.setHex(preset.sky);
    worldLights.hemisphere.groundColor.setHex(preset.ground);
    worldLights.hemisphere.intensity = preset.hemisphereIntensity;
    worldLights.key.color.setHex(preset.key);
    worldLights.key.intensity = preset.keyIntensity;
    worldLights.fill.color.setHex(preset.fill);
    worldLights.fill.intensity = preset.fillIntensity;
    worldLights.cyanGlow.color.setHex(preset.cyan);
    worldLights.cyanGlow.intensity = preset.cyanIntensity;
    worldLights.violetGlow.color.setHex(preset.violet);
    worldLights.violetGlow.intensity = preset.violetIntensity;
  }
  if (atmosphereToggle) {
    atmosphereToggle.textContent = currentAtmosphereMode === "auto" ? "Auto" : preset.label;
    atmosphereToggle.setAttribute("aria-label", `Ambient lighting: ${currentAtmosphereMode === "auto" ? `automatic, ${preset.label}` : preset.label}. Click to change`);
    atmosphereToggle.title = currentAtmosphereMode === "auto"
      ? `Automatic lighting follows this computer's local time · currently ${preset.label}`
      : `Manual ambient lighting: ${preset.label} · click to cycle`;
    atmosphereToggle.dataset.atmosphere = currentAtmosphereMode;
  }
  if (options.persist !== false) {
    try {
      window.localStorage?.setItem(ATMOSPHERE_STORAGE_KEY, currentAtmosphereMode);
    } catch (_error) {
      // Ignore storage failures; the selected lighting remains active for this session.
    }
  }
}

function cycleAtmosphere() {
  const index = ATMOSPHERE_MODES.indexOf(currentAtmosphereMode);
  applyAtmosphere(ATMOSPHERE_MODES[(index + 1) % ATMOSPHERE_MODES.length]);
}

function updateWorldClock() {
  const now = new Date();
  if (worldClockTime) {
    worldClockTime.textContent = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).format(now);
  }
  if (worldClockDate) {
    worldClockDate.textContent = new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      day: "2-digit",
      month: "short",
    }).format(now);
  }
  if (worldClock) {
    worldClock.dateTime = now.toISOString();
    worldClock.title = `Ora locale del computer · ${Intl.DateTimeFormat().resolvedOptions().timeZone || "timezone locale"}`;
    worldClock.setAttribute("aria-label", `Ora locale del computer: ${worldClockTime?.textContent ?? ""} ${worldClockDate?.textContent ?? ""}`);
  }
  if (currentAtmosphereMode === "auto" && atmosphereForLocalTime(now) !== currentAtmosphere) {
    applyAtmosphere("auto", { persist: false });
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
    customWorkstations: workstations
      .filter((station) => station.custom)
      .map((station) => ({
        id: station.id,
        label: station.label,
        role: station.role,
        color: station.color,
        position: { ...station.position },
        rotation: Number(station.rotation) || 0,
        jobs: [...(station.jobs ?? [])],
        agentId: station.agentId ?? "",
        presetId: station.presetId ?? "desk",
        custom: true,
      })),
    stations: Object.fromEntries(workstations.map((station) => [station.id, {
      ...worldToTile(station.position),
      rotation: Number(station.rotation) || 0,
    }])),
    agents,
  };
}

function saveLayoutState(beforeState = null) {
  if (beforeState && !layoutStroke) {
    layoutHistory.record(beforeState, currentLayoutState());
  }
  try {
    window.localStorage?.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(currentLayoutState()));
  } catch (error) {
    runtimeClient.logClient?.("warning", error.message, { operation: "saveLayoutState" });
  }
  updateLayoutHistoryControls();
}

function updateLayoutHistoryControls() {
  if (undoLayoutButton) {
    undoLayoutButton.disabled = !layoutHistory.canUndo;
    undoLayoutButton.title = layoutHistory.canUndo ? "Undo last layout change (⌘Z / Ctrl+Z)" : "No layout changes to undo";
  }
  if (redoLayoutButton) {
    redoLayoutButton.disabled = !layoutHistory.canRedo;
    redoLayoutButton.title = layoutHistory.canRedo ? "Redo layout change (⌘⇧Z / Ctrl+Y)" : "No layout changes to redo";
  }
}

function rebuildStationVisuals() {
  for (const [stationId, group] of stationVisuals) {
    discardAmbientVisuals(group);
    scene.remove(group);
    stationVisuals.delete(stationId);
  }
  for (let index = selectableObjects.length - 1; index >= 0; index -= 1) {
    if (selectableObjects[index].userData.stationId) selectableObjects.splice(index, 1);
  }
  for (const station of workstations) createStationProp(station);
}

function applyLayoutHistorySnapshot(snapshot) {
  if (!snapshot || !Array.isArray(snapshot.rooms) || !snapshot.rooms.length) return false;
  setRoomLayout(snapshot.rooms);
  setDoorLayout(snapshot.doors ?? []);
  setWorkstationLayout(snapshot.customWorkstations ?? []);
  for (const [stationId, tileValue] of Object.entries(snapshot.stations ?? {})) {
    const station = agentWorld.getStation(stationId);
    const tile = tileFromStored(tileValue);
    if (station) station.rotation = normalizeYaw(tileValue?.rotation);
    if (station && tile && isInsideTile(tile)) station.position = tileToWorld(tile);
  }
  agentWorld.refreshBlockedTiles();
  agentWorld.restoreAgentTiles(snapshot.agents ?? {});
  if (!roomLayout.some((room) => room.id === selectedRoomId)) selectedRoomId = roomLayout[0]?.id ?? null;
  if (selectedStationId && !agentWorld.getStation(selectedStationId)) selectedStationId = null;
  if (pendingStationPlacementId && !agentWorld.getStation(pendingStationPlacementId)) pendingStationPlacementId = null;
  rebuildLayoutVisuals();
  rebuildStationVisuals();
  saveLayoutState();
  updateLayoutEditor();
  updateHud();
  return true;
}

function undoLayoutEdit() {
  const snapshot = layoutHistory.undo(currentLayoutState());
  if (snapshot) applyLayoutHistorySnapshot(snapshot);
}

function redoLayoutEdit() {
  const snapshot = layoutHistory.redo(currentLayoutState());
  if (snapshot) applyLayoutHistorySnapshot(snapshot);
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
  if (rotateStationButton) {
    const station = selectedStationId ? agentWorld.getStation(selectedStationId) : null;
    rotateStationButton.disabled = !layoutMode || !station;
    rotateStationButton.title = station ? `Rotate ${station.label} by 90°` : "Select a workstation to rotate it";
  }

  const hasAgents = room ? agentsInRoom(room).length > 0 : false;
  const hasStations = room ? stationsInRoom(room).length > 0 : false;
  if (deleteRoomButton) {
    deleteRoomButton.disabled = !room || roomLayout.length <= 1 || hasAgents || hasStations;
  }
  updateLayoutHistoryControls();
  if (layoutEditorStatus) {
    const mode = roomDrawMode ? "shape room" : doorMode ? "doors / paths" : "move objects";
    const roomText = room ? `${room.label} · ${roomCells(room).length} tiles` : "no room selected";
    layoutEditorStatus.textContent = `${roomText} · ${mode}`;
  }
  if (layoutEditorHint) {
    if (!room) {
      layoutEditorHint.textContent = "Choose a room from the Rooms panel, then select an editing tool.";
    } else if (pendingStationPlacementId) {
      const station = agentWorld.getStation(pendingStationPlacementId);
      layoutEditorHint.textContent = `Click a tile to place ${station?.label ?? "the selected workstation"}.`;
    } else if (roomDrawMode) {
      layoutEditorHint.textContent = "Click or drag to paint the room shape. Drag from an existing tile to erase; the room must stay connected.";
    } else if (doorMode) {
      layoutEditorHint.textContent = "Click or drag to draw a connected path from a room. Erasing cannot leave disconnected path tiles.";
    } else {
      layoutEditorHint.textContent = "Select a workstation and rotate it 90° with the button above. Select an agent or workstation, then click a tile to move it. Undo/Redo: Ctrl+Z / Ctrl+Y.";
    }
  }
  renderWorkstationControls();
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
  } else {
    roomDrawMode = false;
    doorMode = false;
    pendingStationPlacementId = null;
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

function workstationPresetForRole(role) {
  return workstationPresets.find((preset) => preset.role === role)
    ?? workstationPresets.find((preset) => preset.id === "desk")
    ?? workstationPresets[0];
}

function renderWorkstationPresetOptions(select, preferredRole = "") {
  if (!select) {
    return;
  }
  const previous = select.value;
  const preferred = workstationPresetForRole(preferredRole);
  select.innerHTML = workstationPresets
    .map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`)
    .join("");
  select.value = workstationPresets.some((preset) => preset.id === previous) ? previous : preferred?.id ?? workstationPresets[0]?.id ?? "";
}

function renderWorkstationAgentOptions() {
  if (!workstationAgentSelect) {
    return;
  }
  const previous = workstationAgentSelect.value;
  const agents = [...network.agents].sort((left, right) => {
    const leftTime = Date.parse(left.created_at ?? "") || 0;
    const rightTime = Date.parse(right.created_at ?? "") || 0;
    if (leftTime !== rightTime) {
      return rightTime - leftTime;
    }
    return left.label.localeCompare(right.label);
  });
  workstationAgentSelect.innerHTML = agents
    .map((agent) => `<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.label)}</option>`)
    .join("");
  workstationAgentSelect.value = network.getAgent(previous)
    ? previous
    : network.getAgent(selectedAgentId)
      ? selectedAgentId
      : agents[0]?.id ?? "";
  if (addWorkstationButton) {
    addWorkstationButton.disabled = !workstationAgentSelect.value;
  }
}

function renderWorkstationAgentTable() {
  if (!workstationAgentTable) {
    return;
  }
  const agents = [...network.agents].sort((left, right) => {
    const leftTime = Date.parse(left.created_at ?? "") || 0;
    const rightTime = Date.parse(right.created_at ?? "") || 0;
    if (leftTime !== rightTime) {
      return rightTime - leftTime;
    }
    return left.label.localeCompare(right.label);
  });
  if (workstationAgentCount) {
    workstationAgentCount.textContent = `${agents.length} agenti`;
  }
  workstationAgentTable.innerHTML = agents
    .map((agent) => {
      const state = agentWorld.getAgentState(agent.id);
      const station = state?.stationId ? agentWorld.getStation(state.stationId) : null;
      const linkedStation = workstations.find((item) => item.agentId === agent.id);
      const stationLabel = linkedStation?.label ?? station?.label ?? "nessuna workstation";
      const statusText = [agent.role, agent.runtime.status, stationLabel]
        .filter(Boolean)
        .join(" · ");
      return `
        <button class="layout-editor__agent-row ${agent.id === workstationAgentSelect?.value ? "layout-editor__agent-row--active" : ""}" type="button" data-agent="${escapeHtml(agent.id)}">
          <span class="layout-editor__agent-row-color" style="--agent-color: ${escapeHtml(agent.color)}"></span>
          <span class="layout-editor__agent-row-text">
            <strong>${escapeHtml(agent.label)}</strong>
            <small>${escapeHtml(statusText)}</small>
          </span>
        </button>
      `;
    })
    .join("");
  workstationAgentTable.querySelectorAll("[data-agent]").forEach((button) => {
    button.addEventListener("click", () => {
      workstationAgentSelect.value = button.dataset.agent ?? "";
      renderWorkstationControls();
    });
  });
}

function renderWorkstationControls() {
  renderWorkstationAgentOptions();
  const selectedAgent = network.getAgent(workstationAgentSelect?.value) ?? network.getAgent(selectedAgentId);
  renderWorkstationPresetOptions(workstationPresetSelect, selectedAgent?.role ?? "");
  renderWorkstationAgentTable();
}

function moveStationVisual(stationId) {
  const station = agentWorld.getStation(stationId);
  const visual = stationVisuals.get(stationId);
  if (station && visual) {
    visual.position.set(station.position.x, 0, station.position.z);
  }
}

function normalizeYaw(value) {
  const yaw = Number(value);
  if (!Number.isFinite(yaw)) return 0;
  return ((yaw % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
}

function rotateSelectedStation() {
  const station = selectedStationId ? agentWorld.getStation(selectedStationId) : null;
  const visual = selectedStationId ? stationVisuals.get(selectedStationId) : null;
  if (!layoutMode || !station || !visual) return;
  const beforeLayout = currentLayoutState();
  station.rotation = normalizeYaw((Number(station.rotation) || 0) + Math.PI / 2);
  visual.rotation.y = station.rotation;
  saveLayoutState(beforeLayout);
  setBootMessage(`${station.label} ruotata di 90°.`);
  updateLayoutEditor();
}

function uniqueWorkstationId(agentId, presetId) {
  const base = `workstation-${agentId || presetId || "station"}`
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 64) || "workstation";
  if (!workstations.some((station) => station.id === base)) {
    return base;
  }
  let index = 2;
  while (workstations.some((station) => station.id === `${base}-${index}`)) {
    index += 1;
  }
  return `${base}-${index}`;
}

function initialWorkstationTile(agent) {
  const state = agentWorld.getAgentState(agent?.id);
  if (state?.tile) {
    return state.tile;
  }
  const selectedRoom = selectedRoomId ? roomLayout.find((room) => room.id === selectedRoomId) : null;
  return selectedRoom ? tileForRoomCenter(selectedRoom) : tileForRoomCenter(roomLayout[0]);
}

function assignLinkedAgentToStation(stationId) {
  const station = agentWorld.getStation(stationId);
  const agent = station?.agentId ? network.getAgent(station.agentId) : null;
  if (agent) {
    agentWorld.assignStation(agent, station.id, "assigned workstation", true);
  }
}

function createLinkedWorkstation(agent, presetId, options = {}) {
  if (!agent) {
    setBootMessage("Seleziona prima un agente a cui collegare la workstation.");
    return null;
  }
  const existing = workstations.find((station) => station.agentId === agent.id);
  if (existing && options.allowDuplicate !== true) {
    selectedAgentId = agent.id;
    selectedStationId = existing.id;
    selectedRoomId = roomForTile(worldToTile(existing.position))?.id ?? selectedRoomId;
    pendingStationPlacementId = existing.id;
    setLayoutMode(true);
    updateHud();
    setBootMessage(`${existing.label} esiste gia: clicca un tile per ripiazzarla.`);
    return existing;
  }
  const preset = workstationPresets.find((item) => item.id === presetId) ?? workstationPresetForRole(agent.role);
  const beforeLayout = currentLayoutState();
  const station = addWorkstationToLayout({
    id: uniqueWorkstationId(agent.id, preset.id),
    label: `${agent.label} · ${preset.label}`.slice(0, 80),
    role: agent.role,
    color: agent.color || preset.color,
    jobs: preset.jobs,
    agentId: agent.id,
    presetId: preset.id,
    tile: initialWorkstationTile(agent),
  });
  createStationProp(station);
  agentWorld.refreshBlockedTiles();
  renderWorkstationControls();
  selectedAgentId = agent.id;
  selectedStationId = station.id;
  selectedRoomId = roomForTile(worldToTile(station.position))?.id ?? selectedRoomId;
  pendingStationPlacementId = station.id;
  setLayoutMode(true);
  saveLayoutState(beforeLayout);
  updateHud();
  const reason = options.reason ?? "Workstation creata";
  setBootMessage(`${reason}: clicca un tile per piazzare "${station.label}".`);
  return station;
}

function addEditorWorkstation() {
  const agent = network.getAgent(workstationAgentSelect?.value);
  const presetId = workstationPresetSelect?.value || workstationPresetForRole(agent?.role ?? "")?.id;
  createLinkedWorkstation(agent, presetId, { reason: "Preset workstation inserito" });
}

function addLayoutRoom() {
  const rect = findAvailableRoomRect(5, 4);
  if (!rect) {
    setBootMessage("Non c'e spazio libero per un'altra stanza nel layout attuale.");
    return;
  }
  const beforeLayout = currentLayoutState();
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
  saveLayoutState(beforeLayout);
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

const workstationUiTexture = makeCanvasTexture((context, width, height) => {
  context.fillStyle = "#071521";
  context.fillRect(0, 0, width, height);
  context.fillStyle = "#142c3b";
  context.fillRect(0, 0, width, 22);
  context.fillStyle = "#67e8f9";
  context.fillRect(12, 9, 24, 4);
  context.fillStyle = "#254354";
  context.fillRect(45, 9, 62, 4);
  context.strokeStyle = "rgba(103, 232, 249, 0.18)";
  context.lineWidth = 1;
  for (let x = 20; x < width; x += 32) {
    context.beginPath(); context.moveTo(x, 34); context.lineTo(x, height - 12); context.stroke();
  }
  for (let y = 40; y < height; y += 24) {
    context.beginPath(); context.moveTo(10, y); context.lineTo(width - 10, y); context.stroke();
  }
  const bars = [0.3, 0.55, 0.42, 0.78, 0.62, 0.92, 0.68];
  bars.forEach((level, index) => {
    context.fillStyle = index === 5 ? "#a78bfa" : "#38bdf8";
    context.globalAlpha = 0.64;
    context.fillRect(28 + index * 29, height - 18 - level * 58, 13, level * 58);
  });
  context.globalAlpha = 1;
  context.fillStyle = "#8da8bb";
  context.fillRect(width - 72, 34, 56, 5);
  context.fillRect(width - 72, 44, 38, 4);
}, 256, 128);
workstationUiTexture.colorSpace = THREE.SRGBColorSpace;
const workstationUiMaterial = new THREE.MeshBasicMaterial({
  map: workstationUiTexture,
  side: THREE.DoubleSide,
  toneMapped: false,
});
const workstationScanMaterial = new THREE.MeshBasicMaterial({
  color: 0x8bf5ff,
  transparent: true,
  opacity: 0.58,
  side: THREE.DoubleSide,
  depthWrite: false,
  toneMapped: false,
});

function addWorkstationScreen(parent, width, height, position, options = {}) {
  const display = new THREE.Group();
  display.position.set(position.x ?? 0, position.y ?? 0, position.z ?? 0);
  display.rotation.y = options.rotationY ?? 0;
  display.rotation.x = options.rotationX ?? 0;
  const face = new THREE.Mesh(new THREE.PlaneGeometry(width, height), workstationUiMaterial);
  face.position.z = 0.002;
  display.add(face);
  const scan = new THREE.Mesh(new THREE.PlaneGeometry(width * 0.92, Math.max(0.012, height * 0.025)), workstationScanMaterial);
  scan.position.z = 0.006;
  scan.userData.screenSweep = {
    minY: -height * 0.43,
    maxY: height * 0.43,
    speed: options.speed ?? 0.37,
    phase: options.phase ?? ((position.x ?? 0) * 0.31 + (position.y ?? 0) * 0.17),
  };
  display.add(scan);
  parent.add(display);
  return display;
}

function addWorkstationKeyboard(parent, x, y, z, width = 0.62) {
  const keyboard = new THREE.Group();
  keyboard.position.set(x, y, z);
  const base = new THREE.Mesh(new THREE.BoxGeometry(width, 0.035, 0.22), colorMaterial(0x152331, { roughness: 0.5, metalness: 0.22 }));
  keyboard.add(base);
  const keyMaterial = colorMaterial(0x5ecfe4, { emissive: 0x16475b, roughness: 0.38, metalness: 0.18 });
  for (let row = 0; row < 2; row += 1) {
    for (let column = 0; column < 7; column += 1) {
      const key = new THREE.Mesh(new THREE.BoxGeometry(width * 0.085, 0.012, 0.055), keyMaterial);
      key.position.set(-width * 0.39 + column * width * 0.13, 0.024, -0.05 + row * 0.075);
      keyboard.add(key);
    }
  }
  parent.add(keyboard);
  return keyboard;
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
  const styleKey = JSON.stringify(options);
  if (sprite.userData.text === text && sprite.userData.styleKey === styleKey) {
    return;
  }
  sprite.userData.text = text;
  sprite.userData.styleKey = styleKey;
  const oldTexture = sprite.material.map;
  const texture = makeCanvasTexture((labelCtx, width, height) => {
    labelCtx.clearRect(0, 0, width, height);
    labelCtx.fillStyle = options.background ?? "rgba(8, 14, 25, 0.92)";
    drawRoundedRect(labelCtx, 8, 8, width - 16, height - 16, options.radius ?? 26);
    labelCtx.fill();
    labelCtx.strokeStyle = options.border ?? "rgba(167, 196, 226, 0.24)";
    labelCtx.lineWidth = 4;
    labelCtx.stroke();
    const accent = options.accent ?? options.border ?? "#94a3b8";
    labelCtx.save();
    labelCtx.shadowColor = accent;
    labelCtx.shadowBlur = 18;
    labelCtx.fillStyle = accent;
    labelCtx.beginPath();
    labelCtx.arc(54, height / 2, 25, 0, Math.PI * 2);
    labelCtx.fill();
    labelCtx.restore();
    labelCtx.fillStyle = options.iconColor ?? "#071521";
    labelCtx.font = `900 ${options.iconSize ?? 34}px Inter, Arial, sans-serif`;
    labelCtx.textAlign = "center";
    labelCtx.textBaseline = "middle";
    labelCtx.fillText(options.icon ?? "•", 54, height / 2 + 1);
    labelCtx.font = `${options.weight ?? 900} ${options.size ?? 34}px Inter, Arial, sans-serif`;
    labelCtx.textAlign = "left";
    labelCtx.fillStyle = options.color ?? "#eef6ff";
    labelCtx.fillText(text.slice(0, 24), 96, height / 2 + 1);
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

function roomAgentStatus(agent, state) {
  const status = String(agent?.runtime?.status || "").toLowerCase();
  if (/failed|error|blocked|unauthor|missing/.test(status)) return "Needs help";
  if (/waiting|queued|pending|login|authenticat/.test(status)) return "Waiting";
  if (state?.mode === "walking") return "Moving";
  if (state?.activeWorkIds?.size || /executing|working|running/.test(status)) return "Working";
  if (/completed|succeeded|success/.test(status)) return "Done";
  return "Idle";
}

function placeSelectionInRoom(roomId) {
  const room = roomLayout.find((item) => item.id === roomId);
  if (!room) {
    return;
  }
  const target = tileForRoomCenter(room);
  const beforeLayout = currentLayoutState();
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
      setBootMessage(`${network.getAgent(selectedAgentId)?.label ?? "Agente"} spostato in ${room.label}.`);
    }
  }
  if (moved) {
    selectedRoomId = room.id;
    focusRoom(room);
    saveLayoutState(beforeLayout);
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
    ambientVisuals.push({ mesh: rugRing, speed: 1.7, phase: 0.4, amplitude: 0.035, opacity: 0.6 });
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

function discardAmbientVisuals(group) {
  const discarded = new Set();
  group.traverse((child) => discarded.add(child));
  for (let index = ambientVisuals.length - 1; index >= 0; index -= 1) {
    if (discarded.has(ambientVisuals[index].mesh)) ambientVisuals.splice(index, 1);
  }
}

function clearLayoutVisuals() {
  for (const group of roomVisuals.values()) {
    discardAmbientVisuals(group);
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

function toggleSelectedRoomCell(tile, shouldExist = null) {
  if (!selectedRoomId) {
    selectedRoomId = roomLayout[0]?.id ?? null;
  }
  const room = roomLayout.find((item) => item.id === selectedRoomId);
  if (!room) {
    setBootMessage("Seleziona prima una stanza dal pannello Stanze.");
    return;
  }
  const removing = roomContainsTile(room, tile);
  const add = shouldExist === null ? !removing : Boolean(shouldExist);
  if (removing === add) return false;
  if (removing && agentWorld.isOccupiedTile(tile)) {
    setBootMessage("Non posso rimuovere una cella occupata da un agente.");
    return;
  }
  if (removing && agentWorld.isStationTileOccupied(tile)) {
    setBootMessage("Non posso rimuovere una cella occupata da un tavolo.");
    return;
  }
  const beforeLayout = currentLayoutState();
  const result = setRoomCell(room.id, tile, add);
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
    if (result.reason !== "unchanged") setBootMessage(reason);
    return false;
  }
  selectedRoomId = room.id;
  rebuildLayoutVisuals();
  saveLayoutState(beforeLayout);
  setBootMessage(`${room.label}: cella ${result.added ? "aggiunta" : "rimossa"}.`);
  return true;
}

function toggleDoorCell(tile, shouldExist = null) {
  const exists = isDoorTile(tile);
  const add = shouldExist === null ? !exists : Boolean(shouldExist);
  if (exists === add) return false;
  const removingOnlyPassage = !add && exists && !roomForTile(tile);
  if (removingOnlyPassage && agentWorld.isOccupiedTile(tile)) {
    setBootMessage("Non posso rimuovere una porta/corridoio occupata da un agente.");
    return;
  }
  if (removingOnlyPassage && agentWorld.isStationTileOccupied(tile)) {
    setBootMessage("Non posso rimuovere una porta/corridoio occupata da un tavolo.");
    return;
  }
  const beforeLayout = currentLayoutState();
  const result = setDoorAt(tile, add, { allowTemporaryDisconnect: Boolean(layoutStroke && !add) });
  if (!result.changed) {
    const reason = result.reason === "inside-room"
      ? "Le porte e i corridoi devono stare fuori dalle celle della stanza."
      : result.reason === "path-not-connected"
        ? "Inizia il percorso da una cella adiacente a una stanza o a un corridoio esistente."
        : result.reason === "path-disconnected"
          ? "Non posso rimuovere questa cella: lascerebbe un tratto di corridoio scollegato."
          : "Cella porta non valida.";
    if (result.reason !== "unchanged") setBootMessage(reason);
    return false;
  }
  selectedRoomId = roomForTile(tile)?.id ?? selectedRoomId;
  rebuildLayoutVisuals();
  saveLayoutState(beforeLayout);
  setBootMessage(`Porta/corridoio ${result.added ? "aggiunto" : "rimosso"}.`);
  return true;
}

function applyLayoutStrokeTile(tile) {
  if (!layoutStroke || !tile) return;
  const key = tileKey(tile);
  if (layoutStroke.visited.has(key)) return;
  layoutStroke.visited.add(key);
  const changed = layoutStroke.tool === "room"
    ? toggleSelectedRoomCell(tile, layoutStroke.shouldExist)
    : toggleDoorCell(tile, layoutStroke.shouldExist);
  layoutStroke.changed ||= Boolean(changed);
}

function beginLayoutStroke(event) {
  if (!layoutMode || (!roomDrawMode && !doorMode)) return false;
  const hit = objectFromPointer(event);
  const tile = hit?.object?.userData?.tile;
  if (!tile) return false;
  const tool = roomDrawMode ? "room" : "door";
  const exists = tool === "room"
    ? Boolean(selectedRoomId && roomContainsTile(roomLayout.find((room) => room.id === selectedRoomId), tile))
    : isDoorTile(tile);
  layoutStroke = {
    tool,
    shouldExist: !exists,
    before: currentLayoutState(),
    visited: new Set(),
    changed: false,
  };
  applyLayoutStrokeTile(tile);
  return true;
}

function finishLayoutStroke() {
  if (!layoutStroke) return;
  const stroke = layoutStroke;
  layoutStroke = null;
  let changed = stroke.changed;
  if (stroke.tool === "door" && !stroke.shouldExist) {
    const removedDisconnected = pruneDisconnectedDoorPaths();
    if (removedDisconnected) {
      rebuildLayoutVisuals();
      setBootMessage(`Rimossi ${removedDisconnected} tile di corridoio rimasti scollegati.`);
      changed = true;
    }
  }
  if (changed) {
    layoutHistory.record(stroke.before, currentLayoutState());
    saveLayoutState();
  }
  updateLayoutHistoryControls();
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
  const beforeLayout = currentLayoutState();
  const result = removeRoomFromLayout(room.id);
  if (!result.changed) {
    setBootMessage(result.reason === "last-room" ? "Non posso rimuovere l'ultima stanza." : "Stanza non trovata.");
    return;
  }
  setDoorLayout(doorLayout.filter((door) => !deletedKeys.has(tileKey(door))));
  selectedRoomId = roomLayout[Math.min(roomIndex, roomLayout.length - 1)]?.id ?? null;
  rebuildLayoutVisuals();
  saveLayoutState(beforeLayout);
  setBootMessage(`${room.label} rimossa.`);
}

function buildLights() {
  const hemisphere = new THREE.HemisphereLight(0xbfe9ff, 0x070b14, 1.25);
  scene.add(hemisphere);

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
  worldLights = { hemisphere, key, fill, cyanGlow, violetGlow };
  applyAtmosphere(currentAtmosphereMode, { persist: false });
}

function createStationProp(station) {
  const group = new THREE.Group();
  const theme = WORLD_THEMES[currentTheme];
  const stationKind = station.presetId || station.id;
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
  baseRing.userData.phase = station.position.x * 0.8 + station.position.z * 0.6;
  ambientVisuals.push({ mesh: baseRing, speed: 2.2, phase: baseRing.userData.phase, amplitude: 0.028, opacity: 0.72 });
  group.add(baseRing);

  const statusLed = addMesh(group, new THREE.SphereGeometry(0.07, 12, 10), new THREE.MeshStandardMaterial({
    color: 0x64748b,
    emissive: 0x64748b,
    emissiveIntensity: 0.45,
    roughness: 0.28,
    metalness: 0.08,
  }), { x: 0.62, y: 0.14, z: 0.48 }, null, false);
  group.userData.stationStatusLed = statusLed;

  if (stationKind === "hub") {
    addMesh(group, new THREE.CylinderGeometry(0.76, 0.9, 0.42, 8), darkMaterial, { y: 0.26 });
    for (let i = 0; i < 4; i += 1) {
      const monitor = addMesh(
        group,
        new THREE.BoxGeometry(0.55, 0.36, 0.06),
        lightMaterial,
        { x: Math.cos(i * Math.PI * 0.5) * 0.72, y: 0.72, z: Math.sin(i * Math.PI * 0.5) * 0.72 }
      );
      monitor.lookAt(0, 0.72, 0);
      addWorkstationScreen(monitor, 0.44, 0.26, { x: 0, y: 0, z: 0.034 }, { phase: i * 0.19 });
    }
  } else if (stationKind === "planning") {
    addMesh(group, new THREE.BoxGeometry(1.7, 0.12, 0.55), darkMaterial, { y: 0.38 });
    const board = addMesh(group, new THREE.BoxGeometry(1.9, 1.12, 0.1), stationMaterial, {
      y: 1.08,
      z: -0.35,
    });
    board.rotation.x = -0.08;
    addWorkstationScreen(group, 1.62, 0.82, { y: 1.08, z: -0.295 }, { rotationX: -0.08, phase: 0.12 });
    for (let i = 0; i < 5; i += 1) {
      addMesh(group, new THREE.BoxGeometry(0.18, 0.1, 0.035), lightMaterial, {
        x: -0.68 + i * 0.34,
        y: 1.16 + (i % 2) * 0.18,
        z: -0.41,
      });
    }
  } else if (stationKind === "research") {
    addMesh(group, new THREE.BoxGeometry(1.6, 0.16, 0.72), darkMaterial, { y: 0.46 });
    addMesh(group, new THREE.BoxGeometry(0.9, 0.62, 0.1), darkMaterial, { y: 0.94, z: -0.22 });
    addWorkstationScreen(group, 0.76, 0.46, { y: 0.94, z: -0.164 }, { phase: 0.31 });
    addMesh(group, new THREE.BoxGeometry(0.9, 0.06, 0.34), stationMaterial, { y: 0.58, z: 0.24 });
    addWorkstationKeyboard(group, 0, 0.565, 0.18, 0.64);
  } else if (stationKind === "build") {
    addMesh(group, new THREE.BoxGeometry(1.76, 0.32, 0.82), darkMaterial, { y: 0.34 });
    for (let i = 0; i < 4; i += 1) {
      addMesh(group, new THREE.BoxGeometry(0.28, 0.22 + i * 0.03, 0.28), stationMaterial, {
        x: -0.58 + i * 0.38,
        y: 0.68 + i * 0.025,
        z: -0.12 + (i % 2) * 0.3,
      });
    }
  } else if (stationKind === "review") {
    addMesh(group, new THREE.BoxGeometry(1.55, 0.2, 0.95), darkMaterial, { y: 0.42 });
    addMesh(group, new THREE.ConeGeometry(0.3, 0.55, 16), stationMaterial, { y: 0.88, z: -0.2 });
    addMesh(group, new THREE.BoxGeometry(1.1, 0.035, 0.54), lightMaterial, { y: 0.58, z: 0.16 });
  } else if (stationKind === "memory") {
    addMesh(group, new THREE.CylinderGeometry(0.48, 0.58, 1.35, 20), sharedMaterials.glass, { y: 0.78 });
    const core = addMesh(group, new THREE.IcosahedronGeometry(0.42, 1), lightMaterial, { y: 0.84 });
    core.userData.spin = 1.2;
    core.userData.baseY = 0.84;
    core.userData.phase = station.position.x;
  } else if (stationKind === "marketplace") {
    addMesh(group, new THREE.BoxGeometry(1.75, 0.18, 0.78), darkMaterial, { y: 0.43 });
    for (let index = 0; index < 3; index += 1) {
      const screen = addMesh(group, new THREE.BoxGeometry(0.52, 0.42, 0.06), lightMaterial, {
        x: -0.58 + index * 0.58,
        y: 0.9,
        z: -0.2,
      });
      screen.rotation.x = -0.06;
      addWorkstationScreen(group, 0.43, 0.32, {
        x: -0.58 + index * 0.58,
        y: 0.9,
        z: -0.165,
      }, { rotationX: -0.06, phase: index * 0.23 });
    }
    addWorkstationKeyboard(group, 0.28, 0.535, 0.25, 0.58);
    addMesh(group, new THREE.BoxGeometry(0.42, 0.28, 0.42), stationMaterial, { x: -0.55, y: 0.24, z: 0.58 });
    addMesh(group, new THREE.BoxGeometry(0.34, 0.22, 0.34), stationMaterial, { x: -0.08, y: 0.2, z: 0.62 });
  } else if (stationKind === "infrastructure") {
    addMesh(group, new THREE.BoxGeometry(1.72, 0.18, 0.78), darkMaterial, { y: 0.43 });
    for (let index = 0; index < 3; index += 1) {
      const rack = addMesh(group, new THREE.BoxGeometry(0.36, 0.7, 0.3), darkMaterial, {
        x: -0.52 + index * 0.52,
        y: 0.82,
        z: -0.08,
      });
      addWorkstationScreen(rack, 0.22, 0.12, { y: 0.12, z: 0.156 }, { phase: index * 0.28 + 0.15 });
      for (let ledIndex = 0; ledIndex < 3; ledIndex += 1) {
        addMesh(rack, new THREE.SphereGeometry(0.018, 8, 6), lightMaterial, {
          x: -0.1 + ledIndex * 0.1,
          y: -0.17,
          z: 0.158,
        });
      }
    }
    addWorkstationKeyboard(group, 0.3, 0.535, 0.25, 0.56);
    addMesh(group, new THREE.CylinderGeometry(0.13, 0.18, 0.42, 12), stationMaterial, { x: -0.65, y: 0.29, z: 0.45 });
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
  group.rotation.y = normalizeYaw(station.rotation);
  group.userData.stationId = station.id;
  group.traverse((child) => {
    child.userData.stationId = station.id;
  });
  scene.add(group);
  stationVisuals.set(station.id, group);
  group.traverse((child) => {
    if (child.isMesh) selectableObjects.push(child);
  });
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
  const neck = addMesh(group, new THREE.CylinderGeometry(0.095, 0.12, 0.16, 12), darkMaterial, { y: 1.11 });
  const head = addMesh(group, new THREE.SphereGeometry(0.25, 16, 12), headMaterial, { y: 1.22 });
  const visor = addMesh(group, new THREE.BoxGeometry(0.32, 0.08, 0.035), glowMaterial, { y: 1.24, z: 0.22 });
  const eyeMaterial = colorMaterial(0xe8fbff, { emissive: 0x71e9ff, roughness: 0.18 });
  const leftEye = addMesh(group, new THREE.SphereGeometry(0.022, 8, 6), eyeMaterial, { x: -0.075, y: 1.24, z: 0.25 });
  const rightEye = addMesh(group, new THREE.SphereGeometry(0.022, 8, 6), eyeMaterial, { x: 0.075, y: 1.24, z: 0.25 });
  const shoulderLeft = addMesh(group, new THREE.SphereGeometry(0.14, 12, 10), bodyMaterial, { x: -0.34, y: 0.98 });
  const shoulderRight = addMesh(group, new THREE.SphereGeometry(0.14, 12, 10), bodyMaterial, { x: 0.34, y: 0.98 });
  const chestPanel = addMesh(group, new THREE.BoxGeometry(0.37, 0.28, 0.075), darkMaterial, { y: 0.78, z: 0.29 });
  const chestLight = addMesh(group, new THREE.SphereGeometry(0.045, 10, 8), glowMaterial, { y: 0.8, z: 0.34 });
  const backpack = addMesh(group, new THREE.BoxGeometry(0.36, 0.4, 0.16), darkMaterial, { y: 0.8, z: -0.28 });
  shoulderLeft.position.y = 0.26;
  shoulderRight.position.y = 0.26;
  chestPanel.position.set(0, 0.06, 0.29);
  chestLight.position.set(0, 0.08, 0.34);
  backpack.position.set(0, 0.08, -0.28);
  torso.add(shoulderLeft, shoulderRight, chestPanel, chestLight, backpack);

  const createLimbPivot = (x, y) => {
    const pivot = new THREE.Group();
    pivot.position.set(x, y, 0);
    group.add(pivot);
    return pivot;
  };
  const leftArm = createLimbPivot(-0.36, 0.98);
  const rightArm = createLimbPivot(0.36, 0.98);
  const leftArmMesh = addMesh(leftArm, new THREE.BoxGeometry(0.13, 0.42, 0.14), bodyMaterial, { y: -0.23 });
  const rightArmMesh = addMesh(rightArm, new THREE.BoxGeometry(0.13, 0.42, 0.14), bodyMaterial, { y: -0.23 });
  const leftHand = addMesh(leftArm, new THREE.SphereGeometry(0.09, 10, 8), headMaterial, { y: -0.47 });
  const rightHand = addMesh(rightArm, new THREE.SphereGeometry(0.09, 10, 8), headMaterial, { y: -0.47 });
  const leftLeg = createLimbPivot(-0.12, 0.46);
  const rightLeg = createLimbPivot(0.12, 0.46);
  const leftLegMesh = addMesh(leftLeg, new THREE.BoxGeometry(0.15, 0.3, 0.16), darkMaterial, { y: -0.14 });
  const rightLegMesh = addMesh(rightLeg, new THREE.BoxGeometry(0.15, 0.3, 0.16), darkMaterial, { y: -0.14 });
  const leftBoot = addMesh(leftLeg, new THREE.BoxGeometry(0.17, 0.12, 0.24), darkMaterial, { y: -0.31, z: 0.045 });
  const rightBoot = addMesh(rightLeg, new THREE.BoxGeometry(0.17, 0.12, 0.24), darkMaterial, { y: -0.31, z: 0.045 });

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

  const statusBadge = createTextSprite("IDLE", {
    background: "rgba(8, 14, 25, 0.92)",
    color: "#cbd5e1",
    size: 28,
    scaleX: 1.52,
    scaleY: 0.42,
  });
  statusBadge.position.set(0, 2.58, 0);
  group.add(statusBadge);

  const bubble = createTextSprite("", {
    background: "rgba(8, 14, 25, 0.94)",
    color: "#f3f8ff",
    size: 32,
    scaleX: 1.75,
    scaleY: 0.44,
  });
  bubble.position.set(0, 2.96, 0);
  bubble.visible = false;
  group.add(bubble);

  group.traverse((child) => {
    child.userData.agentId = agent.id;
  });

  scene.add(group);
  selectableObjects.push(
    torso, neck, head, visor, leftEye, rightEye, shoulderLeft, shoulderRight, chestPanel, chestLight, backpack,
    leftArmMesh, rightArmMesh, leftHand, rightHand, leftLegMesh, rightLegMesh, leftBoot, rightBoot, diamondTop, diamondBottom,
  );
  agentVisuals.set(agent.id, {
    group,
    torso,
    head,
    leftLeg,
    rightLeg,
    leftArm,
    rightArm,
    chestLight,
    selectionScale: 1,
    diamondTop,
    diamondBottom,
    selectionRing,
    bubble,
    statusBadge,
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

  const packetHalo = new THREE.Mesh(
    new THREE.TorusGeometry(0.18 + message.priority * 0.018, 0.012, 8, 28),
    new THREE.MeshBasicMaterial({ color: message.color, transparent: true, opacity: 0.68, depthWrite: false })
  );
  scene.add(packetHalo);

  const label = createTextSprite(protocol.messageTypes[message.type]?.shortLabel ?? message.type, {
    background: "rgba(8, 14, 25, 0.94)",
    color: "#f3f8ff",
    size: 30,
    scaleX: 1.4,
    scaleY: 0.34,
  });
  label.visible = message.priority >= 3;
  scene.add(label);

  messageVisuals.set(message.id, { line, packet, packetHalo, label });
}

function updateMessageVisuals(elapsed = clock.elapsedTime) {
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
    visual.packet.scale.setScalar(1 + Math.sin(elapsed * 9 + message.progress * 12) * 0.12);
    visual.packetHalo.position.copy(packetPosition);
    visual.packetHalo.rotation.z = elapsed * 1.6;
    visual.packetHalo.scale.setScalar(0.9 + Math.sin(elapsed * 7 + message.progress * 8) * 0.12);
    visual.packetHalo.material.opacity = 0.5 + Math.sin(elapsed * 8 + message.progress * 10) * 0.18;
    visual.line.material.opacity = 0.66 + Math.sin(elapsed * 5 + message.progress * 6) * 0.12;
    visual.label.position.copy(packetPosition).add(new THREE.Vector3(0, 0.34, 0));
  }

  for (const [id, visual] of messageVisuals) {
    if (liveIds.has(id)) {
      continue;
    }
    scene.remove(visual.line, visual.packet, visual.packetHalo, visual.label);
    visual.line.geometry.dispose();
    visual.line.material.dispose();
    visual.packet.geometry.dispose();
    visual.packet.material.dispose();
    visual.packetHalo.geometry.dispose();
    visual.packetHalo.material.dispose();
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
  clampOpenPopups();
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
    const runtimeStatus = String(agent.runtime.status || "").toLowerCase();
    const alertStatus = /failed|error|blocked|unauthor|not found|missing/.test(runtimeStatus);
    const waitingStatus = /waiting|queued|pending|login|authenticat/.test(runtimeStatus);
    const completedStatus = /completed|succeeded|success/.test(runtimeStatus);
    const workingStatus = state.activeWorkIds.size > 0 || /executing|working|running/.test(runtimeStatus);
    const badge = alertStatus
      ? { label: "NEEDS HELP", color: "#fff1f2", background: "rgba(76, 20, 35, 0.96)", border: "#fb7185", accent: "#fb7185", icon: "!" }
      : waitingStatus
        ? { label: "WAITING", color: "#fffbeb", background: "rgba(75, 48, 9, 0.96)", border: "#f59e0b", accent: "#fbbf24", icon: "…" }
        : completedStatus
          ? { label: "DONE", color: "#ecfdf5", background: "rgba(13, 65, 47, 0.96)", border: "#4ade80", accent: "#4ade80", icon: "✓" }
          : walking
            ? { label: "MOVING", color: "#effaff", background: "rgba(10, 54, 81, 0.96)", border: "#38bdf8", accent: "#38bdf8", icon: "↗" }
            : workingStatus
              ? { label: "WORKING", color: "#ecfeff", background: "rgba(8, 64, 74, 0.96)", border: "#22d3ee", accent: "#67e8f9", icon: "⚙" }
              : { label: "IDLE", color: "#e2e8f0", background: "rgba(25, 37, 54, 0.96)", border: "#64748b", accent: "#94a3b8", icon: "·" };
    replaceSpriteText(visual.statusBadge, badge.label, {
      background: badge.background,
      color: badge.color,
      border: badge.border,
      accent: badge.accent,
      icon: badge.icon,
      size: 29,
      width: 420,
      height: 128,
      radius: 54,
    });
    const phase = elapsed + state.seed;
    const breath = Math.sin(phase * 2.2) * 0.012;
    const stride = Math.sin(state.walkPhase) * (walking ? 0.46 : 0.035);
    const workMotion = workingStatus && !walking ? Math.sin(phase * 10) : 0;
    visual.leftLeg.rotation.x = stride;
    visual.rightLeg.rotation.x = -stride;
    visual.leftArm.rotation.x = -stride * 0.82 + workMotion * 0.08;
    visual.rightArm.rotation.x = stride * 0.82 - workMotion * 0.08;
    visual.leftArm.rotation.z = Math.sin(phase * (workingStatus ? 8 : 1.5)) * (workingStatus ? 0.11 : 0.025);
    visual.rightArm.rotation.z = -Math.sin(phase * (workingStatus ? 8 : 1.5) + 0.5) * (workingStatus ? 0.11 : 0.025);
    visual.torso.position.y = 0.72 + breath + Math.abs(Math.sin(state.walkPhase * 2)) * (walking ? 0.035 : 0);
    visual.head.position.y = 1.22 + Math.sin(phase * 2.5) * 0.018;
    visual.head.rotation.z = Math.sin(phase * 0.8) * (workingStatus ? 0.045 : 0.025);
    visual.diamondTop.rotation.y = Math.PI * 0.25 + elapsed * 0.85 + state.seed;
    visual.diamondBottom.rotation.y = Math.PI * 0.25 - elapsed * 0.7 - state.seed;
    visual.diamondTop.position.y = 1.85 + Math.sin(phase * 2.4) * 0.035;
    visual.diamondBottom.position.y = 1.52 + Math.sin(phase * 2.4 + 0.4) * 0.025;
    const selected = selectedAgentId === agent.id;
    const workPulse = workingStatus ? 1 + Math.sin(elapsed * 5 + state.seed) * 0.045 : 1;
    visual.selectionScale += ((selected ? 1.1 : 1) - visual.selectionScale) * 0.16;
    const scale = visual.selectionScale * workPulse;
    visual.diamondTop.scale.setScalar(scale);
    visual.diamondBottom.scale.setScalar(scale);
    visual.selectionRing.visible = selected;
    visual.selectionRing.material.opacity = 0.64 + Math.sin(elapsed * 3) * 0.14;
    visual.selectionRing.scale.setScalar(selected ? 1 + Math.sin(phase * 3.2) * 0.045 : 1);
    visual.chestLight.scale.setScalar(1 + Math.sin(phase * (workingStatus ? 8 : 2)) * (workingStatus ? 0.18 : 0.07));

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
    const owner = station.agentId
      ? network.getAgent(station.agentId)
      : network.agents.find((agent) => agentWorld.getAgentState(agent.id)?.stationId === station.id);
    const ownerState = owner ? agentWorld.getAgentState(owner.id) : null;
    const ownerStatus = String(owner?.runtime?.status ?? "").toLowerCase();
    const stationState = /failed|error|blocked|unauthor|not found|missing/.test(ownerStatus)
      ? { color: 0xfb7185, pulse: 0.05, scanSpeed: 0.12 }
      : ownerState?.activeWorkIds?.size || /executing|working|running/.test(ownerStatus)
        ? { color: 0x22d3ee, pulse: 0.16, scanSpeed: 0.78 }
        : /waiting|queued|pending|login|authenticat/.test(ownerStatus)
          ? { color: 0xfbbf24, pulse: 0.08, scanSpeed: 0.22 }
          : /completed|succeeded|success/.test(ownerStatus)
            ? { color: 0x4ade80, pulse: 0.04, scanSpeed: 0.18 }
            : { color: 0x64748b, pulse: 0.025, scanSpeed: 0.32 };
    const led = group.userData.stationStatusLed;
    if (led) {
      led.material.color.setHex(stationState.color);
      led.material.emissive.setHex(stationState.color);
      led.scale.setScalar(1 + Math.sin(elapsed * (stationState.pulse > 0.1 ? 8 : 2) + station.position.x) * stationState.pulse);
    }
    group.traverse((child) => {
      if (child.userData.spin) {
        child.rotation.y = elapsed * child.userData.spin;
        child.position.y = (child.userData.baseY ?? 0.84) + Math.sin(elapsed * 2 + (child.userData.phase ?? 0)) * 0.05;
      }
      if (child.userData.screenSweep) {
        const sweep = child.userData.screenSweep;
        const progress = ((elapsed * stationState.scanSpeed + sweep.phase) % 1 + 1) % 1;
        child.position.y = THREE.MathUtils.lerp(sweep.minY, sweep.maxY, progress);
      }
    });
    const selected = selectedStationId === station.id;
    const targetScale = selected ? 1.045 : 1;
    group.userData.displayScale = (group.userData.displayScale ?? 1) + (targetScale - (group.userData.displayScale ?? 1)) * 0.14;
    group.scale.setScalar(group.userData.displayScale);
  }
}

function updateAmbientVisuals(elapsed) {
  for (const item of ambientVisuals) {
    const wave = Math.sin(elapsed * item.speed + item.phase);
    item.mesh.material.opacity = item.opacity + wave * 0.12;
    item.mesh.scale.setScalar(1 + wave * item.amplitude);
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
    <span>${agentWorld.isAgentManual(agent.id) ? "selezionato: manuale (10s)" : "selezionato: auto"}</span>
  `;

  eventLog.innerHTML = network.events
    .slice(0, 8)
    .map((event) => {
      const activityState = String(event.activityState || "").toLowerCase();
      const stateBadge = activityState
        ? `<small class="event-log__state" data-state="${escapeHtml(activityState)}">${escapeHtml(jobToastStatus({ state: activityState }) || activityState)}</small>`
        : "";
      const content = `<time>${escapeHtml(event.timeLabel)}</time><span>${escapeHtml(event.text)}</span>${stateBadge}`;
      return event.jobId
        ? `<li><button class="event-log__open" type="button" data-activity-job="${escapeHtml(event.jobId)}" aria-label="Open job details">${content}</button></li>`
        : `<li>${content}</li>`;
    })
    .join("");

  stationList.innerHTML = workstations
    .map((station) => {
      const workers = network.agents.filter((agentItem) => {
        const stateItem = agentWorld.getAgentState(agentItem.id);
        return stateItem?.stationId === station.id;
      });
      const owner = station.agentId ? network.getAgent(station.agentId) : null;
      const detail = [
        owner ? `collegata a ${owner.label}` : "",
        workers.map((worker) => worker.label).join(", ") || "libera",
      ].filter(Boolean).join(" · ");
      return `
        <button class="station-row ${station.id === selectedStationId ? "station-row--active" : ""}" data-station="${station.id}" type="button">
          <span class="station-row__dot" style="--station-color: ${station.color}"></span>
          <span>
            <strong>${station.label}</strong>
            <small>${escapeHtml(detail)}</small>
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

  const room = roomLayout.find((item) => item.id === selectedRoomId);
  if (roomDetails && selectedRoomName && selectedRoomMetrics && selectedRoomStations && selectedRoomAgents) {
    if (!room) {
      roomDetails.hidden = true;
    } else {
      roomDetails.hidden = false;
      selectedRoomName.textContent = room.label;
      const roomStations = workstations.filter((item) => roomContainsTile(room, worldToTile(item.position)));
      const roomAgentList = network.agents.filter((agentItem) => {
        const stateItem = agentWorld.getAgentState(agentItem.id);
        const stationItem = agentWorld.getStation(stateItem?.stationId);
        return roomContainsTile(room, stateItem?.tile)
          || Boolean(stationItem && roomContainsTile(room, worldToTile(stationItem.position)));
      });
      const roomAgentIds = new Set(roomAgentList.map((agentItem) => agentItem.id));
      const roomJobs = [...activityJobCache.values()].filter((job) => (
        roomAgentIds.has(job.agent_id) && ["queued", "running", "scheduled"].includes(String(job.state || ""))
      )).sort((left, right) => String(right.updated_at || right.created_at || "").localeCompare(String(left.updated_at || left.created_at || "")));
      const projectJobIds = new Set(roomJobs.map((job) => job.id));
      const activeTaskCount = roomAgentList.reduce((count, agentItem) => {
        const stateItem = agentWorld.getAgentState(agentItem.id);
        return count + [...(stateItem?.activeWorkIds ?? [])].filter((id) => !projectJobIds.has(id)).length;
      }, 0);
      selectedRoomMetrics.innerHTML = [
        [roomAgentList.length, "agents"], [roomStations.length, "stations"], [roomJobs.length + activeTaskCount, "active work"],
      ].map(([value, label]) => `<span><strong>${value}</strong><small>${label}</small></span>`).join("");
      selectedRoomStations.innerHTML = roomStations.length
        ? roomStations.map((item) => `<span class="room-details__station"><i style="--station-color:${escapeHtml(item.color)}"></i>${escapeHtml(item.label)}</span>`).join("")
        : '<span class="room-details__empty">No workstations in this room.</span>';
      selectedRoomAgents.innerHTML = roomAgentList.length
        ? roomAgentList.map((agentItem) => {
          const stateItem = agentWorld.getAgentState(agentItem.id);
          const statusLabel = roomAgentStatus(agentItem, stateItem);
          const activeJob = roomJobs.find((job) => job.agent_id === agentItem.id);
          const jobText = activeJob
            ? `${projectActionLabelFor(activeJob)} · ${projectNameFor(activeJob)}`
            : stateItem?.activeWorkIds?.size
              ? stateItem.jobLabel
              : stateItem?.jobLabel || agentItem.runtime.status;
          return `<div class="room-details__agent-row">
            <button class="room-details__agent" type="button" data-room-agent="${escapeHtml(agentItem.id)}">
              <i style="--agent-color:${escapeHtml(agentItem.color)}"></i><span><strong>${escapeHtml(agentItem.label)}</strong><small>${escapeHtml(statusLabel)} · ${escapeHtml(jobText)}</small></span>
            </button>
            ${activeJob ? `<button class="room-details__job" type="button" data-room-job="${escapeHtml(activeJob.id)}" aria-label="Open job details">↗</button>` : ""}
          </div>`;
        }).join("")
        : '<span class="room-details__empty">No agents assigned to this room yet.</span>';
    }
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

function appendDiscussionMessage(message) {
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
  quickChatDiscussion.append(item);
  quickChatDiscussion.scrollTop = quickChatDiscussion.scrollHeight;
}

function renderChatHistory(messages) {
  quickChatHistory.replaceChildren();
  chatMessageIds.clear();
  for (const message of messages) {
    appendChatMessage(message);
  }
}

function renderDiscussionHistory(messages) {
  quickChatDiscussion.replaceChildren();
  for (const message of messages) {
    appendDiscussionMessage(message);
  }
}

function mergeAgentChatHistory(agentId, messages = []) {
  const persistent = Array.isArray(messages) ? messages : [];
  const local = projectJobAgentMessages.get(agentId) ?? [];
  const merged = [...persistent, ...local];
  const seenIds = new Set();
  return merged
    .filter((message) => {
      if (!message?.id) {
        return true;
      }
      if (seenIds.has(message.id)) {
        return false;
      }
      seenIds.add(message.id);
      return true;
    })
    .sort((left, right) => String(left?.created_at ?? "").localeCompare(String(right?.created_at ?? "")));
}

function cacheRuntimeTask(task) {
  if (!task?.id) {
    return;
  }
  runtimeTaskCache.set(task.id, task);
  if (Array.isArray(task.discussion_log) && task.discussion_log.length) {
    runtimeDiscussionThreads.set(task.id, task.discussion_log);
  }
}

function upsertDiscussionEntry(taskId, entry) {
  if (!taskId || !entry) {
    return;
  }
  const current = runtimeDiscussionThreads.get(taskId) ?? [];
  if (entry.id && current.some((item) => item?.id === entry.id)) {
    return;
  }
  const next = [...current, entry].sort((left, right) => String(left?.created_at ?? "").localeCompare(String(right?.created_at ?? "")));
  runtimeDiscussionThreads.set(taskId, next);
}

function taskInvolvesAgent(task, agentId) {
  if (!task || !agentId) {
    return false;
  }
  const consultIds = Array.isArray(task.consult_agent_ids) ? task.consult_agent_ids : [];
  return [
    task.requested_agent_id,
    task.source_agent_id,
    task.assigned_agent_id,
    task.consult_agent_id,
    ...consultIds,
  ].includes(agentId);
}

function discussionEntryToChatMessage(entry, selectedAgentId) {
  const senderId = String(entry?.sender || "").trim();
  const recipientId = String(entry?.recipient || "").trim();
  const senderLabel = network.getAgent(senderId)?.label || senderId || "Agent";
  const recipientLabel = network.getAgent(recipientId)?.label || recipientId || "Agent";
  const content = String(entry?.content || "").trim();
  const kind = String(entry?.kind || "thread").trim();
  const role = senderId && senderId === selectedAgentId ? "assistant" : "system";
  const prefix = `[${kind}] ${senderLabel}${recipientId ? ` → ${recipientLabel}` : ""}`;
  const extra = entry?.extra && typeof entry.extra === "object" ? entry.extra : null;
  const routeMode = String(extra?.route_mode || "").trim();
  const decisionMode = String(extra?.decision_mode || "").trim();
  const phase = String(extra?.phase || "").trim();
  const steps = Array.isArray(extra?.steps) ? extra.steps.filter((step) => String(step || "").trim()) : [];
  const details = [];
  if (kind === "strategy" || kind === "strategy-update") {
    if (routeMode) {
      details.push(`Mode: ${routeMode}`);
    }
    if (decisionMode) {
      details.push(`Decision: ${decisionMode}`);
    }
    if (phase) {
      details.push(`Phase: ${phase}`);
    }
    for (const step of steps) {
      details.push(`- ${String(step).trim()}`);
    }
  }
  return {
    id: entry?.id || "",
    task_id: entry?.task_id || "",
    role,
    content: [content ? `${prefix}\n${content}` : prefix, ...details].filter(Boolean).join("\n"),
    sources: Array.isArray(entry?.sources) ? entry.sources : [],
    created_at: entry?.created_at || new Date().toISOString(),
  };
}

function discussionMessagesForAgent(agentId) {
  const messages = [];
  for (const [taskId, task] of runtimeTaskCache.entries()) {
    if (!taskInvolvesAgent(task, agentId)) {
      continue;
    }
    const entries = runtimeDiscussionThreads.get(taskId) ?? [];
    for (const entry of entries) {
      messages.push(discussionEntryToChatMessage(entry, agentId));
    }
  }
  return messages;
}

function taskThreadItems() {
  return [...runtimeTaskCache.values()]
    .filter((task) => task?.channel === "chat" && Array.isArray(task?.discussion_log) && task.discussion_log.length)
    .sort((left, right) => String(right?.updated_at ?? "").localeCompare(String(left?.updated_at ?? "")));
}

function taskThreadLabel(task) {
  const title = String(task?.title || task?.id || "Task").trim();
  const state = String(task?.state || "").trim();
  const source = network.getAgent(task?.source_agent_id || task?.requested_agent_id || "")?.label
    || task?.source_agent_id
    || task?.requested_agent_id
    || "";
  const consulted = Array.isArray(task?.consult_agent_ids) ? task.consult_agent_ids.length : 0;
  const detail = [state, source ? `from ${source}` : "", consulted ? `${consulted} consult${consulted === 1 ? "" : "s"}` : ""]
    .filter(Boolean)
    .join(" · ");
  return { title, detail };
}

function renderTaskThreadList() {
  if (!taskThreadList || !taskThreadCount) {
    return;
  }
  const tasks = taskThreadItems();
  taskThreadCount.textContent = tasks.length
    ? `${tasks.length} task discussion${tasks.length === 1 ? "" : "s"}`
    : "No task discussions";
  taskThreadList.innerHTML = tasks.map((task) => {
    const { title, detail } = taskThreadLabel(task);
    const active = task.id === selectedTaskThreadId;
    return `
      <button class="wiki-page-item${active ? " wiki-page-item--active" : ""}" type="button" data-task-thread="${escapeHtml(task.id)}">
        <strong>${escapeHtml(title)}</strong>
        <small>${escapeHtml(detail || "discussion thread")}</small>
      </button>
    `;
  }).join("");
  if (!selectedTaskThreadId && tasks[0]?.id) {
    selectedTaskThreadId = tasks[0].id;
  }
}

function formatTaskDiscussionThread(task) {
  const lines = [];
  const { title, detail } = taskThreadLabel(task);
  lines.push(`# ${title}`);
  if (detail) {
    lines.push(detail);
  }
  lines.push("");
  for (const entry of task.discussion_log ?? []) {
    const sender = network.getAgent(entry?.sender || "")?.label || entry?.sender || "Agent";
    const recipient = network.getAgent(entry?.recipient || "")?.label || entry?.recipient || "Agent";
    const kind = String(entry?.kind || "thread").trim();
    const createdAt = String(entry?.created_at || "").trim();
    const timestamp = createdAt ? createdAt.replace("T", " ").replace(/\.\d+.*$/, "") : "";
    lines.push(`## ${kind}${timestamp ? ` · ${timestamp}` : ""}`);
    lines.push(`${sender} -> ${recipient}`);
    lines.push(String(entry?.content || "").trim() || "(empty)");
    const extra = entry?.extra && typeof entry.extra === "object" ? entry.extra : null;
    if (extra) {
      if (kind === "strategy" || kind === "strategy-update") {
        const routeMode = String(extra.route_mode || "").trim();
        const decisionMode = String(extra.decision_mode || "").trim();
        const phase = String(extra.phase || "").trim();
        const userFacing = String(extra.user_facing_agent_id || "").trim();
        const execution = String(extra.execution_agent_id || "").trim();
        const consulted = Array.isArray(extra.consult_agent_ids) ? extra.consult_agent_ids.join(", ") : "";
        const clarification = String(extra.clarification_question || "").trim();
        const steps = Array.isArray(extra.steps) ? extra.steps.filter((step) => String(step || "").trim()) : [];
        if (routeMode) {
          lines.push(`Route mode: ${routeMode}`);
        }
        if (decisionMode) {
          lines.push(`Decision mode: ${decisionMode}`);
        }
        if (phase) {
          lines.push(`Phase: ${phase}`);
        }
        if (userFacing) {
          lines.push(`User-facing agent: ${userFacing}`);
        }
        if (execution) {
          lines.push(`Execution agent: ${execution}`);
        }
        if (consulted) {
          lines.push(`Consulted agents: ${consulted}`);
        }
        if (clarification) {
          lines.push(`Clarification: ${clarification}`);
        }
        if (steps.length) {
          lines.push("Steps:");
          for (const step of steps) {
            lines.push(`- ${String(step).trim()}`);
          }
        }
      } else if (kind === "council-policy") {
        const enabled = extra.enabled === true ? "enabled" : "skipped";
        const participants = Array.isArray(extra.participants) ? extra.participants.join(", ") : "";
        const maxTurns = Number.isFinite(Number(extra.max_turns)) ? Number(extra.max_turns) : 0;
        const decisionMode = String(extra.decision_mode || "heuristic").trim();
        lines.push(`Policy: ${enabled}`);
        lines.push(`Decision mode: ${decisionMode}`);
        if (participants) {
          lines.push(`Participants: ${participants}`);
        }
        lines.push(`Turn budget: ${maxTurns}`);
      } else if (kind === "plan" && extra.specialist_question) {
        lines.push(`Question: ${String(extra.specialist_question).trim()}`);
      } else if (kind === "reasoning") {
        const reasoningType = String(extra.reasoning_type || "").trim();
        const focus = String(extra.focus || "").trim();
        const reactingTo = String(extra.reacting_to || "").trim();
        const concern = String(extra.concern || "").trim();
        const nextStep = String(extra.next_step || "").trim();
        if (reasoningType) {
          lines.push(`Reasoning type: ${reasoningType}`);
        }
        if (focus) {
          lines.push(`Focus: ${focus}`);
        }
        if (reactingTo) {
          lines.push(`Reacting to: ${reactingTo}`);
        }
        if (concern) {
          lines.push(`Concern: ${concern}`);
        }
        if (nextStep) {
          lines.push(`Next step: ${nextStep}`);
        }
      } else if (kind === "revise" && extra.previous_summary) {
        lines.push(`Previous summary: ${String(extra.previous_summary).trim()}`);
      }
    }
    const sources = Array.isArray(entry?.sources) ? entry.sources : [];
    if (sources.length) {
      lines.push("");
      lines.push("Sources:");
      for (const source of sources) {
        const url = safeWebUrl(source?.url);
        if (url) {
          lines.push(`- ${source?.title || url}: ${url}`);
        }
      }
    }
    lines.push("");
  }
  return lines.join("\n").trim();
}

function renderSelectedTaskThread() {
  if (!taskThreadContent) {
    return;
  }
  const task = runtimeTaskCache.get(selectedTaskThreadId);
  if (!task || !Array.isArray(task.discussion_log) || !task.discussion_log.length) {
    taskThreadContent.textContent = "Select a task discussion thread.";
    return;
  }
  taskThreadContent.textContent = formatTaskDiscussionThread(task);
}

async function refreshTaskThreads() {
  try {
    const tasks = await runtimeClient.listTasks();
    for (const task of tasks) {
      cacheRuntimeTask(task);
    }
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "refreshTaskThreads" });
  }
  renderTaskThreadList();
  renderSelectedTaskThread();
}

function setQuickChatView(view = "chat") {
  quickChatView = view === "discussion" ? "discussion" : "chat";
  if (quickChatHistory) {
    quickChatHistory.hidden = quickChatView !== "chat";
  }
  if (quickChatDiscussion) {
    quickChatDiscussion.hidden = quickChatView !== "discussion";
  }
  for (const button of quickChatTabs) {
    const active = button.dataset.quickChatTab === quickChatView;
    button.classList.toggle("agent-quick-chat__tab--active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
}

function openQuickChat(agentId) {
  const agent = network.getAgent(agentId);
  if (!agent) {
    return;
  }
  quickChatDetached = false;
  quickChat.classList.remove("agent-quick-chat--detached");
  quickChat.style.transform = "";
  quickChat.style.visibility = "visible";
  quickChatAgentId = agentId;
  quickChatAgent.textContent = agent.label;
  quickChatStatus.textContent = "";
  quickChatStatus.classList.remove("agent-quick-chat__status--error");
  quickChat.hidden = false;
  setQuickChatView(quickChatView);
  quickChatHistory.innerHTML = '<li class="agent-quick-chat__message">Caricamento...</li>';
  quickChatDiscussion.innerHTML = '<li class="agent-quick-chat__message agent-quick-chat__message--system">Loading discussion...</li>';
  chatMessageIds.clear();
  updateQuickChatPosition();
  window.clearTimeout(quickChatFocusTimer);
  quickChatFocusTimer = window.setTimeout(() => quickChatInput.focus(), 220);
  runtimeClient.getAgentChat(agentId)
    .then((messages) => {
      if (quickChatAgentId === agentId) {
        renderChatHistory(mergeAgentChatHistory(agentId, messages));
        renderDiscussionHistory(discussionMessagesForAgent(agentId));
      }
    })
    .catch((error) => {
      if (quickChatAgentId === agentId) {
        renderChatHistory(mergeAgentChatHistory(agentId, [{ role: "system", content: error.message }]));
        renderDiscussionHistory(discussionMessagesForAgent(agentId));
      }
    });
}

async function createAgentChatTask(agentId, message, options = {}) {
  const trimmed = String(message ?? "").trim();
  if (!trimmed || !agentId) {
    return null;
  }
  const task = await runtimeClient.createTask({
    title: String(options.title ?? trimmed.slice(0, 160)),
    description: trimmed,
    priority: Number(options.priority ?? 3),
    requested_agent_id: agentId,
    channel: "chat",
  });
  return task;
}

async function askMemoryCore(message, options = {}) {
  const task = await createAgentChatTask("memory", message, {
    title: options.title ?? "Memory Core request",
    priority: options.priority ?? 2,
  });
  if (options.openChat !== false) {
    openQuickChat("memory");
  }
  return task;
}

function cancelPendingAgentQuickChat() {
  if (pendingAgentQuickChat?.timer) {
    window.clearTimeout(pendingAgentQuickChat.timer);
  }
  pendingAgentQuickChat = null;
}

function scheduleAgentQuickChat(agentId) {
  cancelPendingAgentQuickChat();
  pendingAgentQuickChat = {
    agentId,
    timer: window.setTimeout(() => {
      if (pendingAgentQuickChat?.agentId !== agentId || selectedAgentId !== agentId || layoutMode) {
        return;
      }
      pendingAgentQuickChat = null;
      openQuickChat(agentId);
    }, 240),
  };
}

function closeQuickChat() {
  cancelPendingAgentQuickChat();
  quickChatAgentId = null;
  quickChat.hidden = true;
  quickChat.style.visibility = "hidden";
  quickChat.style.transform = "";
  quickChat.classList.remove("agent-quick-chat--detached");
  quickChatDetached = false;
  window.clearTimeout(quickChatFocusTimer);
  quickChatFocusTimer = null;
  quickChatInput.value = "";
  quickChatHistory.replaceChildren();
  quickChatDiscussion.replaceChildren();
  chatMessageIds.clear();
  quickChatStatus.textContent = "";
  quickChatStatus.classList.remove("agent-quick-chat__status--error");
}

function updateQuickChatPosition() {
  if (!quickChatAgentId || quickChat.hidden) {
    return;
  }
  if (quickChatDetached) {
    quickChat.style.visibility = "visible";
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

function clampPopupPosition(element, left, top) {
  const margin = 8;
  const width = Math.min(element.offsetWidth || 320, Math.max(120, window.innerWidth - margin * 2));
  const height = Math.min(element.offsetHeight || 180, Math.max(120, window.innerHeight - margin * 2));
  const maxLeft = Math.max(margin, window.innerWidth - width - margin);
  const maxTop = Math.max(margin, window.innerHeight - height - margin);
  return {
    left: Math.max(margin, Math.min(maxLeft, left)),
    top: Math.max(margin, Math.min(maxTop, top)),
  };
}

function positionPopup(element, left, top) {
  const next = clampPopupPosition(element, left, top);
  element.style.position = "fixed";
  element.style.margin = "0";
  element.style.right = "auto";
  element.style.bottom = "auto";
  element.style.transform = "none";
  element.style.left = `${next.left}px`;
  element.style.top = `${next.top}px`;
}

function isDragBlockedTarget(target) {
  return Boolean(target.closest("button, input, textarea, select, option, a, label, [role='button']"));
}

function makePopupDraggable(element, handle, options = {}) {
  if (!element || !handle) {
    return;
  }
  element.classList.add("draggable-popup");
  handle.classList.add("draggable-popup__handle");

  let drag = null;
  const dragThreshold = 4;
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || isDragBlockedTarget(event.target)) {
      return;
    }
    if (element.hidden || (element instanceof HTMLDialogElement && !element.open)) {
      return;
    }
    event.preventDefault();
    const rect = element.getBoundingClientRect();
    drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      rectLeft: rect.left,
      rectTop: rect.top,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
      active: false,
    };
    handle.setPointerCapture(event.pointerId);
  });

  handle.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    if (!drag.active) {
      const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
      if (distance < dragThreshold) {
        return;
      }
      drag.active = true;
      options.onDetach?.();
      positionPopup(element, drag.rectLeft, drag.rectTop);
      element.classList.add("draggable-popup--moving");
    }
    positionPopup(element, event.clientX - drag.offsetX, event.clientY - drag.offsetY);
  });

  const endDrag = (event) => {
    if (!drag || event.pointerId !== drag.pointerId) {
      return;
    }
    drag = null;
    element.classList.remove("draggable-popup--moving");
    if (handle.hasPointerCapture(event.pointerId)) {
      handle.releasePointerCapture(event.pointerId);
    }
  };
  handle.addEventListener("pointerup", endDrag);
  handle.addEventListener("pointercancel", endDrag);
}

function setupDraggablePopups() {
  makePopupDraggable(quickChat, quickChat?.querySelector(".agent-quick-chat__heading"), {
    onDetach: () => {
      quickChatDetached = true;
      quickChat.classList.add("agent-quick-chat--detached");
    },
  });
  makePopupDraggable(layoutEditor, layoutEditor?.querySelector(".layout-editor__heading"));
  for (const dialog of document.querySelectorAll(".agent-dialog")) {
    makePopupDraggable(dialog, dialog.querySelector(".dialog-heading"));
  }
}

function clampOpenPopups() {
  const popups = [quickChat, layoutEditor, ...document.querySelectorAll(".agent-dialog")];
  for (const popup of popups) {
    if (!popup || popup.hidden || (popup instanceof HTMLDialogElement && !popup.open)) {
      continue;
    }
    const left = Number.parseFloat(popup.style.left);
    const top = Number.parseFloat(popup.style.top);
    if (Number.isFinite(left) && Number.isFinite(top)) {
      positionPopup(popup, left, top);
    }
  }
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
  updateAmbientVisuals(elapsed);
  updateTiles();
  if (now >= nextRelationRefresh) {
    updateRelationVisuals();
    nextRelationRefresh = now + PERFORMANCE.relationRefreshMs;
  }
  updateMessageVisuals(elapsed);
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
  if (intentId === "memory-sync" && runtimeClient.connected) {
    await openProjectGateway({ panel: "memory", mode: "memory" });
    return;
  }
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
        title: "Memory Core review",
        description: "Review shared context, notifications, wiki proposals, and memory updates through Memory Core.",
        capability: "memory",
        priority: 2,
        requested_agent_id: "memory",
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

function ensureRuntimeRelation(fromId, toId, protocolId) {
  if (!fromId || !toId || fromId === toId || network.findRelation(fromId, toId, protocolId)) {
    return;
  }
  const relation = network.registerRelation({
    id: `runtime-${protocolId}-${fromId}-${toId}`,
    from: fromId,
    to: toId,
    kind: protocolId === "conversation-routing" ? "conversation" : "runtime",
    protocolId,
    latency: 0.72,
    trust: 0.84,
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
    existing.toolsets = [...(snapshot.toolsets ?? [])];
    existing.runtime.status = snapshot.state;
    existing.runtime.load = snapshot.load;
    applyAgentAppearance(existing);
    const state = agentWorld.getAgentState(existing.id);
    if (state) {
      state.lastRuntimeStatus = "";
    }
    ensureSupervisorRelation(snapshot.id);
    renderWorkstationControls();
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
    toolsets: snapshot.toolsets ?? [],
    position: positionForAgent(snapshot.id),
    summary: `${snapshot.role} agent managed by the native runtime.`,
    runtime: { status: snapshot.state, load: snapshot.load },
  });
  agentWorld.registerAgent(agent);
  createAgentVisual(agent);
  ensureSupervisorRelation(snapshot.id);
  renderWorkstationControls();
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
  const protocolBindings = {
    "task-contract": {
      protocolId: "contract-net",
      typeMap: {
        "task.announce": "task.announce",
        "task.award": "task.award",
        "task.accept": "task.proposal",
        "task.progress": "task.status",
        "task.result": "task.status",
      },
    },
    "conversation-routing": {
      protocolId: "conversation-routing",
      typeMap: {
        "chat.route": "chat.route",
        "chat.consult": "chat.consult",
        "chat.strategy": "chat.strategy",
        "chat.peer-brief": "chat.peer-brief",
        "chat.peer-request": "chat.peer-request",
        "chat.reasoning": "chat.reasoning",
        "chat.plan": "chat.plan",
        "chat.council": "chat.council",
        "chat.revise": "chat.revise",
        "chat.strategy-update": "chat.strategy-update",
        "chat.accept": "chat.accept",
        "chat.reply": "chat.reply",
      },
    },
    "memory-learning": {
      protocolId: "blackboard-sync",
      typeMap: {
        "memory.recall": "memory.recall",
        "memory.propose": "memory.propose",
        "memory.approve": "memory.approve",
        "memory.commit": "memory.commit",
      },
    },
    "blackboard-sync": {
      protocolId: "blackboard-sync",
      typeMap: {
        "memory.write": "memory.write",
        "memory.snapshot": "memory.snapshot",
      },
    },
  };
  const binding = protocolBindings[message.protocol] ?? null;
  const protocolId = binding?.protocolId;
  const type = binding?.typeMap?.[message.type];
  if (!protocolId || !type) {
    return;
  }
  ensureRuntimeRelation(message.sender, message.recipient, protocolId);
  network.enqueue({
    from: message.sender,
    to: message.recipient,
    protocolId,
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

function rememberTaskUiNotice(taskId, phase) {
  const normalizedTaskId = String(taskId || "").trim();
  const normalizedPhase = String(phase || "").trim();
  if (!normalizedTaskId || !normalizedPhase) {
    return false;
  }
  const key = `${normalizedTaskId}:${normalizedPhase}`;
  if (taskUiNotices.has(key)) {
    return false;
  }
  taskUiNotices.add(key);
  return true;
}

function rememberThreadUiNotice(entryId) {
  const normalizedEntryId = String(entryId || "").trim();
  if (!normalizedEntryId || threadUiNotices.has(normalizedEntryId)) {
    return false;
  }
  threadUiNotices.add(normalizedEntryId);
  return true;
}

function showGameNotification({ title = "", subtitle = "", summary = "", tone = "active", key = "" } = {}) {
  if (!jobToastStack || !summary) {
    return;
  }
  const notificationKey = String(key ?? "").trim();
  if (notificationKey && gameNotificationKeys.has(notificationKey)) return;
  if (notificationKey) gameNotificationKeys.add(notificationKey);
  if (gameNotificationKeys.size > 500) {
    while (gameNotificationKeys.size > 300) gameNotificationKeys.delete(gameNotificationKeys.values().next().value);
  }
  const notice = document.createElement("article");
  notice.className = "job-toast job-toast--active";
  if (tone === "success") {
    notice.classList.add("job-toast--success");
  } else if (tone === "danger") {
    notice.classList.add("job-toast--danger");
  }
  if (notificationKey) {
    notice.dataset.notificationKey = notificationKey;
  }
  notice.innerHTML = `
    <div class="job-toast__header">
      <div class="job-toast__title">
        <strong></strong>
        <span></span>
      </div>
      <div class="job-toast__meta">
        <span class="job-toast__status" data-tone="${escapeHtml(tone)}"></span>
        <button type="button" aria-label="Chiudi notifica">x</button>
      </div>
    </div>
    <p class="job-toast__summary"></p>
    <pre class="job-toast__output"></pre>
  `;
  notice.querySelector(".job-toast__title strong").textContent = title;
  notice.querySelector(".job-toast__title span").textContent = subtitle;
  notice.querySelector(".job-toast__status").textContent =
    tone === "danger" ? "Errore" : tone === "success" ? "Completato" : "Nuovo";
  notice.querySelector(".job-toast__summary").textContent = summary;
  notice.querySelector(".job-toast__output").textContent = "";
  const dismiss = () => notice.remove();
  notice.querySelector("button")?.addEventListener("click", dismiss);
  jobToastStack.prepend(notice);
  while (jobToastStack.children.length > 5) jobToastStack.lastElementChild?.remove();
  jobNotificationsButton?.classList.add("is-pulse");
  window.setTimeout(() => jobNotificationsButton?.classList.remove("is-pulse"), 900);
  window.setTimeout(dismiss, 9000);
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

function threadEntryUiSummary(entry) {
  const kind = String(entry?.kind || "").trim();
  const senderId = String(entry?.sender || "").trim();
  const recipientId = String(entry?.recipient || "").trim();
  const senderLabel = network.getAgent(senderId)?.label || senderId || "Agent";
  const recipientLabel = network.getAgent(recipientId)?.label || recipientId || "Agent";
  const content = String(entry?.content || "").trim();
  const extra = entry?.extra && typeof entry.extra === "object" ? entry.extra : null;
  const phase = String(extra?.phase || "").trim();
  const routeMode = String(extra?.route_mode || "").trim();
  const targetKind = String(extra?.target_kind || extra?.followup_target_kind || "").trim();
  const targetLabel = String(extra?.target_label || extra?.followup_target_label || "").trim();
  const requestedById = String(extra?.requested_by_agent_id || extra?.followup_requested_by_agent_id || "").trim();
  const requestedByLabel = network.getAgent(requestedById)?.label || requestedById || "";
  if (kind === "strategy") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} set the initial strategy.`,
      notificationTitle: senderLabel,
      notificationSubtitle: routeMode ? `Strategy · ${routeMode}` : "Strategy",
      notificationSummary: content || `${senderLabel} set the initial execution strategy.`,
    };
  }
  if (kind === "strategy-update") {
    const honoredRequestText = requestedByLabel && phase === "memory-followup"
      ? `${senderLabel} honored ${requestedByLabel}'s request for Memory Core context.`
      : requestedByLabel && phase === "followup-consult"
        ? `${senderLabel} honored ${requestedByLabel}'s request and brought in ${targetLabel || "another specialist"}.`
        : requestedByLabel && phase === "council-request"
          ? `${senderLabel} honored ${requestedByLabel}'s request and prepared a council step.`
          : "";
    return {
      bubbleAgentId: senderId,
      bubbleText: content || honoredRequestText || `${senderLabel} updated the strategy.`,
      notificationTitle: senderLabel,
      notificationSubtitle: phase ? `Strategy update · ${phase}` : "Strategy update",
      notificationSummary: content || honoredRequestText || `${senderLabel} updated the execution strategy.`,
    };
  }
  if (kind === "peer-brief") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} briefed ${recipientLabel}.`,
      notificationTitle: senderLabel,
      notificationSubtitle: "Peer brief",
      notificationSummary: content || `${senderLabel} briefed ${recipientLabel}.`,
    };
  }
  if (kind === "peer-request") {
    const peerRequestText = targetKind === "memory"
      ? `${senderLabel} asked ${recipientLabel} to query Memory Core.`
      : targetKind === "council"
        ? `${senderLabel} asked ${recipientLabel} to run a council step.`
        : `${senderLabel} asked ${recipientLabel} to bring in ${targetLabel || "another specialist"}.`;
    return {
      bubbleAgentId: senderId,
      bubbleText: content || peerRequestText,
      notificationTitle: senderLabel,
      notificationSubtitle: targetKind === "memory" ? "Memory escalation" : targetKind === "council" ? "Council escalation" : "Peer escalation",
      notificationSummary: content || peerRequestText,
    };
  }
  if (kind === "reasoning") {
    const focus = String(extra?.focus || "").trim();
    const concern = String(extra?.concern || "").trim();
    const nextStep = String(extra?.next_step || "").trim();
    const reasoningType = String(extra?.reasoning_type || "").trim();
    const reactingTo = String(extra?.reacting_to || "").trim();
    const baseText = content || `${senderLabel} shared an internal reasoning note.`;
    const bubbleText = concern ? `${baseText} Concern: ${concern}` : baseText;
    return {
      bubbleAgentId: senderId,
      bubbleText,
      notificationTitle: senderLabel,
      notificationSubtitle: reasoningType === "council" ? "Council reasoning" : "Specialist reasoning",
      notificationSummary: [
        focus ? `Focus: ${focus}` : "",
        baseText,
        concern ? `Concern: ${concern}` : "",
        reactingTo ? `Reacting to: ${reactingTo}` : "",
        nextStep ? `Next: ${nextStep}` : "",
      ].filter(Boolean).join(" · "),
    };
  }
  if (kind === "revise") {
    return {
      bubbleAgentId: recipientId || senderId,
      bubbleText: content || `${senderLabel} requested a revision.`,
      notificationTitle: recipientLabel || senderLabel,
      notificationSubtitle: "Revision request",
      notificationSummary: content || `${senderLabel} asked for a stronger specialist answer.`,
    };
  }
  if (kind === "revision-result") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} returned a revised answer.`,
      notificationTitle: senderLabel,
      notificationSubtitle: "Revision result",
      notificationSummary: content || `${senderLabel} returned a revised specialist answer.`,
    };
  }
  if (kind === "council-policy") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} decided whether to run a council step.`,
      notificationTitle: senderLabel,
      notificationSubtitle: "Council policy",
      notificationSummary: content || `${senderLabel} decided whether the specialists should run a council step.`,
    };
  }
  if (kind === "council-turn" || kind === "council-turn-request") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} exchanged a council note with ${recipientLabel}.`,
      notificationTitle: senderLabel,
      notificationSubtitle: "Council exchange",
      notificationSummary: content || `${senderLabel} exchanged a council note with ${recipientLabel}.`,
    };
  }
  if (kind === "synthesis") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} is synthesizing the specialist input.`,
      notificationTitle: senderLabel,
      notificationSubtitle: "Final synthesis",
      notificationSummary: content || `${senderLabel} is synthesizing the specialist input.`,
    };
  }
  if (kind === "memory") {
    return {
      bubbleAgentId: senderId,
      bubbleText: content || `${senderLabel} delivered memory context to ${recipientLabel}.`,
      notificationTitle: senderLabel,
      notificationSubtitle: "Memory recall",
      notificationSummary: content || `${senderLabel} delivered memory context to ${recipientLabel}.`,
    };
  }
  return null;
}

function maybeNotifyDiscussionEntry(task, entry) {
  if (!task?.id || !entry?.id || !rememberThreadUiNotice(entry.id)) {
    return;
  }
  const summary = threadEntryUiSummary(entry);
  if (!summary) {
    return;
  }
  if (summary.bubbleAgentId) {
    showAgentReply(summary.bubbleAgentId, summary.bubbleText, false, Array.isArray(entry.sources) ? entry.sources : [], `${task.id}-${entry.id}`);
  }
  showGameNotification({
    title: summary.notificationTitle,
    subtitle: `${summary.notificationSubtitle} · ${task.id}`,
    summary: summary.notificationSummary,
    tone: "active",
    key: `${task.id}-${entry.id}`,
  });
}

function protocolSpeechText(message, mode = "recipient") {
  if (!message) {
    return "";
  }
  const payload = message.payload ?? {};
  const senderLabel = network.getAgent(message.sender)?.label || message.sender;
  const recipientLabel = network.getAgent(message.recipient)?.label || message.recipient;
  const title = String(payload.title || "").trim();
  const capability = String(payload.capability || "").trim();
  const summary = String(payload.summary || "").trim();
  const progress = Number(payload.progress);
  const query = String(payload.query || "").trim();
  const firstMatch = Array.isArray(payload.matches) ? payload.matches[0] : null;
  const firstMatchName = String(firstMatch?.name || "").trim();
  const targetKind = String(payload.target_kind || payload.followup_target_kind || "").trim();
  const targetLabel = String(payload.target_label || payload.target_specialist || payload.followup_target_label || "").trim();
  const requestedById = String(payload.requested_by_agent_id || payload.followup_requested_by_agent_id || "").trim();
  const requestedByLabel = network.getAgent(requestedById)?.label || requestedById || "";

  if (message.protocol === "task-contract") {
    if (message.type === "task.announce") {
      return mode === "sender"
        ? `Assigning ${title || "a task"} to ${recipientLabel}.`
        : `${senderLabel} assigned ${title || "a task"}${capability ? ` (${capability})` : ""}.`;
    }
    if (message.type === "task.award") {
      return mode === "sender"
        ? `${recipientLabel} will handle ${title || "the task"}.`
        : `I got ${title || "the task"}.`;
    }
    if (message.type === "task.accept") {
      return mode === "sender"
        ? `Accepted by ${recipientLabel}.`
        : `Accepted. Starting now.`;
    }
    if (message.type === "task.progress" && Number.isFinite(progress)) {
      return mode === "sender"
        ? `${progress}% done.`
        : `${senderLabel} is at ${progress}%.`;
    }
    if (message.type === "task.result") {
      return mode === "sender"
        ? `${summary || "Result is ready."}`
        : `${senderLabel}: ${summary || "Result is ready."}`;
    }
  }

  if (message.protocol === "memory-learning") {
    if (message.type === "memory.recall") {
      return mode === "sender"
        ? `Sending context${firstMatchName ? `: ${firstMatchName}` : ""}.`
        : `Memory recall${firstMatchName ? `: ${firstMatchName}` : query ? `: ${query.slice(0, 34)}` : ""}.`;
    }
    if (message.type === "memory.propose") {
      return mode === "sender" ? "Proposing a memory update." : `${senderLabel} proposed a memory update.`;
    }
    if (message.type === "memory.approve") {
      return mode === "sender" ? "Approving the memory update." : `${senderLabel} approved the memory update.`;
    }
    if (message.type === "memory.commit") {
      return mode === "sender" ? "Committing the memory update." : `${senderLabel} committed the memory update.`;
    }
  }

  if (message.protocol === "blackboard-sync") {
    if (message.type === "memory.write") {
      return mode === "sender" ? "Writing to shared memory." : `${senderLabel} updated shared memory.`;
    }
    if (message.type === "memory.snapshot") {
      return mode === "sender" ? "Publishing memory snapshot." : `${senderLabel} sent a memory snapshot.`;
    }
  }

  if (message.protocol === "conversation-routing") {
    if (message.type === "chat.route") {
      return mode === "sender"
        ? `Passing this to ${recipientLabel}.`
        : `${senderLabel} routed this conversation to me.`;
    }
    if (message.type === "chat.consult") {
      return mode === "sender"
        ? `Consulting ${recipientLabel}.`
        : `${senderLabel} is asking for my specialist input.`;
    }
    if (message.type === "chat.strategy") {
      const strategySummary = String(payload.summary || payload.strategy_summary || "").trim();
      return mode === "sender"
        ? (strategySummary ? `Strategy for ${recipientLabel}: ${strategySummary}` : `Sending the execution strategy to ${recipientLabel}.`)
        : (strategySummary ? `${senderLabel}'s strategy: ${strategySummary}` : `${senderLabel} sent me the execution strategy.`);
    }
    if (message.type === "chat.peer-brief") {
      const previousSpecialist = String(payload.previous_specialist || "").trim();
      const previousSummary = String(payload.previous_summary || "").trim();
      return mode === "sender"
        ? (previousSummary
          ? `Briefing ${recipientLabel}${previousSpecialist ? ` about ${previousSpecialist}` : ""}: ${previousSummary}`
          : `Sending a peer brief to ${recipientLabel}.`)
        : (previousSummary
          ? `${senderLabel} briefed me${previousSpecialist ? ` about ${previousSpecialist}` : ""}: ${previousSummary}`
          : `${senderLabel} sent me a peer brief.`);
    }
    if (message.type === "chat.peer-request") {
      const reason = String(payload.reason || "").trim();
      if (targetKind === "memory") {
        return mode === "sender"
          ? (reason ? `Requesting Memory Core context: ${reason}` : "Requesting Memory Core context before synthesis.")
          : (reason ? `${senderLabel} requested Memory Core context: ${reason}` : `${senderLabel} requested Memory Core context.`);
      }
      if (targetKind === "council") {
        return mode === "sender"
          ? (reason ? `Requesting a council step: ${reason}` : "Requesting a council step before synthesis.")
          : (reason ? `${senderLabel} requested a council step: ${reason}` : `${senderLabel} requested a council step.`);
      }
      return mode === "sender"
        ? (reason
          ? `Requesting ${targetLabel || recipientLabel}: ${reason}`
          : `Requesting ${targetLabel || "another specialist"} before synthesis.`)
        : (reason
          ? `${senderLabel} requested ${targetLabel || "another specialist"}: ${reason}`
          : `${senderLabel} requested ${targetLabel || "another specialist"}.`);
    }
    if (message.type === "chat.reasoning") {
      const focus = String(payload.focus || "").trim();
      const conclusion = String(payload.conclusion || payload.summary || "").trim();
      const concern = String(payload.concern || "").trim();
      const nextStep = String(payload.next_step || "").trim();
      const reactingTo = String(payload.reacting_to || "").trim();
      const parts = [
        focus ? `focus ${focus}` : "",
        conclusion ? `conclusion ${conclusion}` : "",
        concern ? `concern ${concern}` : "",
        reactingTo ? `reacting to ${reactingTo}` : "",
        nextStep ? `next ${nextStep}` : "",
      ].filter(Boolean);
      if (!parts.length) {
        return mode === "sender"
          ? "Sending an internal reasoning note."
          : `${senderLabel} sent an internal reasoning note.`;
      }
      return mode === "sender"
        ? `Reasoning note: ${parts.join(" · ")}`
        : `${senderLabel}'s reasoning: ${parts.join(" · ")}`;
    }
    if (message.type === "chat.plan") {
      const planSummary = String(payload.plan_summary || "").trim();
      const specialistQuestion = String(payload.specialist_question || "").trim();
      const consultPosition = String(payload.consult_position || "").trim();
      if (mode === "sender") {
        return specialistQuestion
          ? `Plan for ${recipientLabel}${consultPosition ? ` (${consultPosition})` : ""}: ${specialistQuestion}`
          : `Sending the delegation plan to ${recipientLabel}.`;
      }
      return planSummary
        ? `${senderLabel}'s plan: ${planSummary}`
        : `${senderLabel} sent me the delegation plan.`;
    }
    if (message.type === "chat.council") {
      const otherSpecialist = String(payload.other_specialist || "").trim();
      return mode === "sender"
        ? `Asking ${recipientLabel} for a council reaction${otherSpecialist ? ` about ${otherSpecialist}` : ""}.`
        : `${senderLabel} is asking for my council reaction${otherSpecialist ? ` about ${otherSpecialist}` : ""}.`;
    }
    if (message.type === "chat.revise") {
      const followupQuestion = String(payload.followup_question || "").trim();
      return mode === "sender"
        ? (followupQuestion ? `Follow-up for ${recipientLabel}: ${followupQuestion}` : `Requesting a revision from ${recipientLabel}.`)
        : (followupQuestion ? `${senderLabel} asked me to revise: ${followupQuestion}` : `${senderLabel} requested a revision.`);
    }
    if (message.type === "chat.strategy-update") {
      const strategySummary = String(payload.summary || payload.strategy_summary || "").trim();
      const phase = String(payload.phase || "").trim();
      if (requestedByLabel && phase === "memory-followup") {
        return mode === "sender"
          ? `Honoring ${requestedByLabel}'s memory request.`
          : `${senderLabel} honored ${requestedByLabel}'s memory request.`;
      }
      if (requestedByLabel && phase === "followup-consult") {
        return mode === "sender"
          ? `Honoring ${requestedByLabel}'s request and consulting ${targetLabel || recipientLabel}.`
          : `${senderLabel} honored ${requestedByLabel}'s request and consulted ${targetLabel || recipientLabel}.`;
      }
      if (requestedByLabel && phase === "council-request") {
        return mode === "sender"
          ? `Honoring ${requestedByLabel}'s request for a council step.`
          : `${senderLabel} honored ${requestedByLabel}'s request for a council step.`;
      }
      return mode === "sender"
        ? (strategySummary
          ? `Updating strategy${phase ? ` (${phase})` : ""} for ${recipientLabel}: ${strategySummary}`
          : `Updating the execution strategy for ${recipientLabel}.`)
        : (strategySummary
          ? `${senderLabel} updated the strategy${phase ? ` (${phase})` : ""}: ${strategySummary}`
          : `${senderLabel} updated the execution strategy.`);
    }
    if (message.type === "chat.accept") {
      return mode === "sender"
        ? `I will take this conversation.`
        : `${senderLabel} accepted the handoff.`;
    }
    if (message.type === "chat.reply") {
      return mode === "sender"
        ? `Sending the reply back.`
        : `${senderLabel} sent the reply back.`;
    }
  }

  return mode === "sender"
    ? `Sending ${message.type} to ${recipientLabel}.`
    : `${senderLabel}: ${message.type}`;
}

function rememberProjectJobUiNotice(jobId, phase = "update") {
  const normalizedJobId = String(jobId || "").trim();
  const normalizedPhase = String(phase || "").trim();
  if (!normalizedJobId || !normalizedPhase) {
    return false;
  }
  const key = `${normalizedJobId}:${normalizedPhase}`;
  if (projectJobUiNotices.has(key)) {
    return false;
  }
  projectJobUiNotices.add(key);
  return true;
}

function storeProjectJobAgentMessage(agentId, message) {
  if (!agentId || !message) {
    return;
  }
  const current = projectJobAgentMessages.get(agentId) ?? [];
  if (message.id && current.some((entry) => entry.id === message.id)) {
    return;
  }
  const next = [...current, message].sort((left, right) => String(left?.created_at ?? "").localeCompare(String(right?.created_at ?? "")));
  projectJobAgentMessages.set(agentId, next);
}

function projectJobRows(job) {
  const result = job?.result ?? {};
  const normalized = result.normalized ?? {};
  if (Array.isArray(normalized.rows)) {
    return normalized.rows;
  }
  if (Array.isArray(result.rows)) {
    return result.rows;
  }
  return [];
}

function projectJobMeta(job) {
  const result = job?.result ?? {};
  const normalized = result.normalized ?? {};
  return normalized.meta_summary ?? result.meta_summary ?? {};
}

function extractProjectJobDealMatches(job) {
  return projectJobRows(job).filter((row) => row && typeof row === "object" && row.deal_hunter_match);
}

function formatDealPriceForChat(row) {
  return String(
    row?.price
      || row?.total_price
      || row?.base_price
      || row?.price_value
      || row?.total_price_value
      || ""
  ).trim();
}

function formatDealLineForChat(row) {
  const title = String(row?.name || row?.title || row?.item_id || "Affare Vinted").trim();
  const price = formatDealPriceForChat(row);
  const reason = String(row?.deal_hunter_reason || row?.deal_hunter_label || "").trim();
  const parts = [title];
  if (price) parts.push(price);
  if (reason) parts.push(reason);
  return parts.join(" — ");
}

function notifyAgentAboutProjectJobDeals(job) {
  if (!job?.id || !job?.agent_id || job.state !== "completed" || !rememberProjectJobUiNotice(job.id, "deal-hunter")) {
    return;
  }
  const meta = projectJobMeta(job);
  const dealMatches = extractProjectJobDealMatches(job);
  const declaredMatches = Number(meta?.deal_hunter_matches ?? job?.result?.normalized?.meta_summary?.deal_hunter_matches ?? 0) || 0;
  const matches = dealMatches.length ? dealMatches : [];
  const matchCount = matches.length || declaredMatches;
  if (matchCount <= 0 || !meta?.deal_hunter_enabled) {
    return;
  }
  const agent = network.getAgent(job.agent_id);
  const agentLabel = agent?.label || job.agent_id;
  const preview = matches.slice(0, 3).map((row) => formatDealLineForChat(row));
  const summary = preview.length
    ? `I found ${matchCount} deal-hunter matches.\n${preview.map((line, index) => `${index + 1}. ${line}`).join("\n")}`
    : `I found ${matchCount} deal-hunter matches. Open the job output for the full detail.`;
  const sources = matches.slice(0, 8)
    .map((row, index) => {
      const url = safeWebUrl(row?.link);
      if (!url) {
        return null;
      }
      return {
        title: formatDealLineForChat(row) || `Affare ${index + 1}`,
        url,
      };
    })
    .filter(Boolean);
  const createdAt = job.updated_at || job.created_at || new Date().toISOString();
  storeProjectJobAgentMessage(job.agent_id, {
    id: `${job.id}-deal-hunter`,
    task_id: job.id,
    role: "assistant",
    content: summary,
    sources,
    created_at: createdAt,
  });
  showAgentReply(job.agent_id, summary, false, sources, `${job.id}-deal-hunter`);
  showGameNotification({
    title: agentLabel,
    subtitle: `Deals found · ${job.id}`,
    summary: `Deal hunter: ${matchCount} confirmed matches.`,
    tone: "success",
    key: `${job.id}-deal-hunter-toast`,
  });
}

function acknowledgeAgentTask(task, phase = "accepted") {
  if (!task?.id || !task?.assigned_agent_id || !rememberTaskUiNotice(task.id, phase)) {
    return;
  }
  const agent = network.getAgent(task.assigned_agent_id);
  const agentLabel = agent?.label || task.assigned_agent_id;
  const requestText = String(task.description || task.title || "Task ricevuto.").trim();
  const shortRequest = requestText.length > 72 ? `${requestText.slice(0, 69)}...` : requestText;
  const replyText = phase === "running"
    ? `Sto lavorando su: ${shortRequest}`
    : `Ricevuto. Mi occupo di: ${shortRequest}`;
  showAgentReply(task.assigned_agent_id, replyText, false, [], `${task.id}-${phase}`);
  const state = agentWorld.getAgentState(task.assigned_agent_id);
  if (state) {
    state.bubble = replyText.slice(0, 42);
  }
  showGameNotification({
    title: agentLabel,
    subtitle: `Task ${phase === "running" ? "in corso" : "assegnato"} · ${task.id}`,
    summary: replyText,
    tone: "active",
    key: `${task.id}-${phase}`,
  });
}

function handleRuntimeEvent(event) {
  if (event.type === "runtime.snapshot") {
    for (const agent of event.agents ?? []) {
      ensureRuntimeAgent(agent);
    }
    for (const task of event.tasks ?? []) {
      cacheRuntimeTask(task);
      if (["accepted", "running"].includes(task.state) && task.assigned_agent_id) {
        agentWorld.assignAgentToWork(task.assigned_agent_id, task.id, task.title || "Working on task", network);
      }
    }
    for (const historicEvent of (event.events ?? []).slice(-8)) {
      network.log(historicEvent.summary);
    }
    renderWorkstationControls();
  } else if (event.type === "agent.created" || event.type === "agent.updated") {
    ensureRuntimeAgent(event.data.agent);
    renderWorkstationControls();
  } else if (event.type === "agent.state.changed") {
    const agent = network.getAgent(event.agent_id);
    if (agent) {
      agent.runtime.status = event.data.to;
      agent.runtime.load = event.data.load;
    }
  } else if (event.type === "protocol.message") {
    renderRuntimeMessage(event);
    const message = event.data?.message;
    const senderAgent = network.getAgent(message?.sender);
    const recipientAgent = network.getAgent(message?.recipient);
    if (senderAgent && recipientAgent) {
      showAgentReply(message.sender, protocolSpeechText(message, "sender"), false, [], `${message.id}-sender`);
      showAgentReply(message.recipient, protocolSpeechText(message, "recipient"), false, [], `${message.id}-recipient`);
    }
    if (message?.protocol === "memory-learning" && message?.type === "memory.recall") {
      queueMemoryCouncilSignal("memory", 1);
    }
    if (message?.type === "task.result") {
      showAgentReply(
        message.sender,
        message.payload?.summary ?? "Task completato.",
        false,
        message.payload?.sources ?? [],
        message.task_id ?? ""
      );
      showGameNotification({
        title: network.getAgent(message.sender)?.label || message.sender || "Agente",
        subtitle: `Task completato · ${message.task_id ?? ""}`,
        summary: message.payload?.summary ?? "Task completato.",
        tone: "success",
        key: `${message.task_id ?? ""}-result`,
      });
    }
  } else if (event.type === "task.created") {
    const task = event.data?.task;
    cacheRuntimeTask(task);
    if (task?.channel === "chat" && !isAutoCouncilTask(task)) {
      queueMemoryCouncilSignal("user", 1);
    }
  } else if (event.type === "chat.thread.updated") {
    const task = event.data?.task;
    const entry = event.data?.entry;
    cacheRuntimeTask(task);
    if (task?.id && entry) {
      upsertDiscussionEntry(task.id, entry);
      maybeNotifyDiscussionEntry(task, entry);
    }
    if (!selectedTaskThreadId && task?.id) {
      selectedTaskThreadId = task.id;
    }
    renderTaskThreadList();
    if (task?.id === selectedTaskThreadId) {
      renderSelectedTaskThread();
    }
    if (quickChatAgentId && !quickChat.hidden && taskInvolvesAgent(task, quickChatAgentId) && entry) {
      appendDiscussionMessage(discussionEntryToChatMessage(entry, quickChatAgentId));
    }
  } else if (event.type === "chat.routed") {
    const task = event.data?.task;
    cacheRuntimeTask(task);
    const toAgentId = event.data?.to_agent_id || task?.requested_agent_id || "";
    const fromAgentId = event.data?.from_agent_id || task?.source_agent_id || "";
    const routeMode = String(event.data?.route_mode || task?.route_mode || "route");
    if (toAgentId && routeMode === "route") {
      selectedAgentId = toAgentId;
      openQuickChat(toAgentId);
    }
    showGameNotification({
      title: network.getAgent(toAgentId)?.label || "Agent",
      subtitle: routeMode === "consult" ? "Specialist consulted" : "Conversation routed",
      summary: fromAgentId && toAgentId
        ? routeMode === "consult"
          ? `${network.getAgent(fromAgentId)?.label || fromAgentId} is consulting ${network.getAgent(toAgentId)?.label || toAgentId}.`
          : `${network.getAgent(fromAgentId)?.label || fromAgentId} routed the conversation to ${network.getAgent(toAgentId)?.label || toAgentId}.`
        : routeMode === "consult"
          ? "The current agent is consulting a specialist."
          : "Conversation routed to the best matching agent.",
      tone: "active",
      key: `${task?.id ?? ""}-chat-routed`,
    });
  } else if (event.type === "chat.consulted") {
    const task = event.data?.task;
    cacheRuntimeTask(task);
    const fromAgentId = event.data?.from_agent_id || task?.source_agent_id || "";
    const toAgentId = event.data?.to_agent_id || "";
    const specialistQuestion = String(event.data?.specialist_question || "").trim();
    const summary = String(event.data?.summary || "").trim();
    showGameNotification({
      title: network.getAgent(toAgentId)?.label || "Specialist",
      subtitle: "Specialist response",
      summary: specialistQuestion && summary
        ? `${specialistQuestion}\n\n${summary}`
        : summary || "A specialist returned their reasoning.",
      tone: "active",
      key: `${task?.id ?? ""}-${toAgentId}-consulted`,
    });
  } else if (event.type === "chat.returned") {
    const task = event.data?.task;
    cacheRuntimeTask(task);
    const toAgentId = event.data?.to_agent_id || task?.source_agent_id || "";
    const fromAgentId = event.data?.from_agent_id || task?.assigned_agent_id || "";
    const summary = String(event.data?.summary || "Reply returned.").trim();
    const sources = Array.isArray(event.data?.sources) ? event.data.sources : [];
    if (quickChatAgentId === toAgentId && !quickChat.hidden) {
      renderQuickChatReply(summary, sources, false, `${task?.id ?? ""}-returned`);
    }
    showGameNotification({
      title: network.getAgent(toAgentId)?.label || "Agent",
      subtitle: "Consultation returned",
      summary: fromAgentId && toAgentId
        ? `${network.getAgent(fromAgentId)?.label || fromAgentId} sent the answer back to ${network.getAgent(toAgentId)?.label || toAgentId}.`
        : "A routed conversation returned a reply.",
      tone: "success",
      key: `${task?.id ?? ""}-chat-returned`,
    });
  } else if (event.type === "task.state.changed") {
    const task = event.data?.task;
    cacheRuntimeTask(task);
    const taskAgentId = task?.assigned_agent_id || event.agent_id;
    const taskAgent = taskAgentId ? network.getAgent(taskAgentId) : null;
    if (taskAgent) {
      const nextTaskState = event.data?.to;
      if (nextTaskState === "running" || nextTaskState === "accepted") {
        taskAgent.runtime.status = "executing";
        taskAgent.runtime.load = 0.82;
      } else if (nextTaskState === "completed") {
        taskAgent.runtime.status = "completed";
        taskAgent.runtime.load = 0.08;
      } else if (nextTaskState === "failed") {
        taskAgent.runtime.status = "failed";
        taskAgent.runtime.load = 0.08;
      }
    }
    if (["accepted", "running"].includes(event.data?.to) && taskAgentId) {
      agentWorld.assignAgentToWork(taskAgentId, task.id, task.title || task.description || "Working on task", network);
    } else if (["completed", "failed", "cancelled"].includes(event.data?.to) && taskAgentId) {
      agentWorld.releaseAgentFromWork(taskAgentId, task.id, network);
    }
    renderTaskThreadList();
    if (task?.id === selectedTaskThreadId) {
      renderSelectedTaskThread();
    }
    if (event.data?.to === "accepted") {
      acknowledgeAgentTask(task, "accepted");
    } else if (event.data?.to === "running") {
      acknowledgeAgentTask(task, "running");
    } else if (event.data?.to === "failed") {
      showAgentReply(task?.assigned_agent_id, task?.error ?? "Task fallito.", true, [], task?.id ?? "");
      showGameNotification({
        title: network.getAgent(task?.assigned_agent_id)?.label || task?.assigned_agent_id || "Agente",
        subtitle: `Task fallito · ${task?.id ?? ""}`,
        summary: task?.error ?? "Task fallito.",
        tone: "danger",
        key: `${task?.id ?? ""}-failed`,
      });
    }
  } else if (event.type === "memory.updated") {
    queueMemoryCouncilSignal("memory", 2);
  } else if (event.type === "wiki.proposal.resolved" || event.type === "wiki.maintenance.completed") {
    queueMemoryCouncilSignal("memory", 1);
  } else if (event.type === "runpod.gpu.available") {
    showGameNotification({ title: "RunPod Manager", subtitle: "GPU available", summary: `${event.data?.name || event.entity_id} is now available in ${event.data?.region || "your configured region"}.`, tone: "success", key: `runpod-gpu-${event.entity_id}-${event.created_at}` });
  } else if (event.type?.startsWith("project.job.")) {
    const job = event.data?.job;
    if (job?.id) {
      activityJobCache.set(job.id, job);
      while (activityJobCache.size > 100) activityJobCache.delete(activityJobCache.keys().next().value);
      if (["scheduled", "queued", "running"].includes(job.state)) {
        activeProjectJobs.set(job.id, job);
      } else {
        activeProjectJobs.delete(job.id);
      }
      renderActiveWorkOverview();
      const checkedCompetitorId = reportCompetitorSaleCheckJobs.get(job.id);
      if (checkedCompetitorId && (job.state === "completed" || job.state === "failed")) {
        reportCompetitorSaleCheckJobs.delete(job.id);
        reportCompetitorSaleChecks.delete(checkedCompetitorId);
        reportCompetitorDetails.delete(checkedCompetitorId);
        if (reportSelectedCompetitorId === checkedCompetitorId) {
          renderReportCompetitors();
          if (job.state === "completed") loadReportCompetitorDetail(checkedCompetitorId);
        }
      }
    }
    const agent = job?.agent_id ? network.getAgent(job.agent_id) : null;
    if (agent) {
      const active = event.type === "project.job.queued" || event.type === "project.job.started";
      agent.runtime.status = event.type === "project.job.alert"
        ? "waiting"
        : active
          ? "executing"
          : event.type.endsWith("failed")
            ? "failed"
            : event.type.endsWith("completed")
              ? "completed"
              : "idle";
      agent.runtime.load = active ? 0.82 : 0.08;
    }
    if (event.type === "project.job.started" && job?.agent_id) {
      agentWorld.assignAgentToWork(
        job.agent_id,
        job.id,
        `${projectActionLabelFor(job)} · ${projectNameFor(job)}`,
        network,
      );
    } else if ((event.type === "project.job.completed" || event.type === "project.job.failed") && job?.agent_id) {
      agentWorld.releaseAgentFromWork(job.agent_id, job.id, network);
    }
    syncProjectJobToast(job, event.type);
    if (event.type === "project.job.alert") {
      notifyAgentAboutProjectJobAlert(job, event.data?.alert ?? null);
    }
    if (event.type === "project.job.completed") {
      notifyAgentAboutProjectJobDeals(job);
    }
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
    if (job && monitoringJobDefinitions.some((definition) => definition.action === job.action)) {
      void refreshMonitoringDashboard();
    }
  } else if (event.type === "runtime.disconnected") {
    setRuntimeConnection(false);
  }

  if (event.summary) {
    const job = event.data?.job;
    const task = event.data?.task;
    network.log(event.summary, {
      jobId: job?.id || "",
      taskId: task?.id || "",
      agentId: job?.agent_id || task?.assigned_agent_id || event.agent_id || "",
      activityState: job?.state || task?.state || "",
    });
  }
  updateHud();
}

function selectedProject() {
  return availableProjects.find((project) => project.id === projectSelect.value);
}

function selectedProjectAction() {
  return selectedProject()?.actions.find((action) => action.id === projectAction.value);
}

function projectParameterDefinitions(action) {
  return (action?.parameters ?? [])
    .map((parameter) => {
      if (typeof parameter === "string") {
        return { id: parameter };
      }
      if (parameter && typeof parameter === "object" && typeof parameter.id === "string" && parameter.id) {
        return parameter;
      }
      return null;
    })
    .filter(Boolean);
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
  projectParameters.innerHTML = projectParameterDefinitions(action)
    .map((parameter) => {
      const id = parameter.id;
      const label = parameter.label ?? id;
      const type = parameter.type ?? (booleanParameters.has(id) ? "checkbox" : id.includes("max-") ? "number" : "text");
      const checkedClass = type === "checkbox" ? " project-parameter--check" : "";
      const min = parameter.min !== undefined ? ` min="${parameter.min}"` : "";
      const max = parameter.max !== undefined ? ` max="${parameter.max}"` : "";
      const step = parameter.step !== undefined ? ` step="${parameter.step}"` : "";
      const placeholder = parameter.placeholder ? ` placeholder="${String(parameter.placeholder).replaceAll('"', "&quot;")}"` : "";
      if (type === "select") {
        const options = Array.isArray(parameter.options) ? parameter.options : [];
        const renderedOptions = options
          .map((option) => {
            if (option && typeof option === "object") {
              const value = String(option.value ?? "");
              const optionLabel = String(option.label ?? value);
              const selected = parameter.default !== undefined && String(parameter.default) === value ? " selected" : "";
              return `<option value="${value}"${selected}>${optionLabel}</option>`;
            }
            const value = String(option ?? "");
            const selected = parameter.default !== undefined && String(parameter.default) === value ? " selected" : "";
            return `<option value="${value}"${selected}>${value}</option>`;
          })
          .join("");
        return `<label class="${checkedClass}"><span>${label}</span><select data-project-parameter="${id}">${renderedOptions}</select>${projectParameterHelpHtml(parameter)}</label>`;
      }
      if (type === "checkbox") {
        const checked = parameter.default ? " checked" : "";
        return `<label class="${checkedClass}"><span>${label}</span><input data-project-parameter="${id}" type="checkbox"${checked} />${projectParameterHelpHtml(parameter)}</label>`;
      }
      if (type === "duration") {
        return projectDurationParameterHtml(parameter);
      }
      if (type === "list") {
        const storedRows = readStoredProjectListParameterRows(id);
        const rows = storedRows ?? splitProjectListParameterRows(parameter.default);
        const renderedRows = (rows.length ? rows : [{ name: "", url: "" }])
          .map((row) => projectListParameterRowHtml(id, parameter, row))
          .join("");
        const addLabel = escapeHtml(parameter.addLabel ?? "+ Add");
        return `
          <label class="project-parameter-list" data-project-list="${escapeHtml(id)}">
            <span>${escapeHtml(label)}</span>
            <div class="project-parameter-list__rows" data-project-list-rows="${escapeHtml(id)}">${renderedRows}</div>
            <button class="button button--secondary button--compact" type="button" data-project-list-add="${escapeHtml(id)}">${addLabel}</button>
            ${projectParameterHelpHtml(parameter)}
          </label>
        `;
      }
      if (type === "competitor-list") {
        const profiles = Array.isArray(projectCompetitorProfiles) ? projectCompetitorProfiles : [];
        const rows = profiles.length ? profiles.map((profile) => {
          const url = String(profile.seller_profile_url || "").trim();
          if (!url) return "";
          const name = String(profile.seller_name || `Seller ${profile.seller_member_id || ""}`).trim();
          const status = String(profile.status || "candidate");
          return `<label class="project-competitor-option"><input type="checkbox" data-project-competitor-profile value="${escapeHtml(url)}" /><span><b>${escapeHtml(name)}</b><small>${escapeHtml(status)} · ${escapeHtml(profile.seller_member_id || "")}</small></span></label>`;
        }).join("") : '<p class="project-parameter-help">No saved competitors yet. Run Competitor discovery or enter a profile URL manually.</p>';
        return `<section class="project-competitor-list"><span>${escapeHtml(label)}</span><div>${rows}</div>${projectParameterHelpHtml(parameter)}</section>`;
      }
      const value = parameter.default !== undefined && parameter.default !== null ? ` value="${String(parameter.default).replaceAll('"', "&quot;")}"` : "";
      return `<label class="${checkedClass}"><span>${label}</span><input data-project-parameter="${id}" type="${type}"${value}${placeholder}${min}${max}${step} />${projectParameterHelpHtml(parameter)}</label>`;
    })
    .join("");
  setupProjectListParameters();
  projectRisk.textContent = action ? `Risk: ${action.risk}` : "";
  if (action?.description) {
    projectRisk.textContent += ` | ${action.description}`;
  }
  projectApprovalRow.hidden = !action?.requiresApproval;
  projectForm.elements.namedItem("approved").checked = false;
}

function readProjectParameters() {
  const parameters = {};
  for (const list of projectParameters.querySelectorAll("[data-project-list]")) {
    const id = list.dataset.projectList;
    const rows = readProjectListRowsFromElement(list);
    persistProjectListParameterRows(id, rows);
    const values = rows.map((row) => row.url.trim()).filter(Boolean);
    if (values.length) {
      parameters[id] = values.join("\n");
    }
  }
  for (const input of projectParameters.querySelectorAll("[data-project-duration-value]")) {
    const id = input.dataset.projectDurationValue;
    const value = Number(String(input.value ?? "").trim() || "0");
    const unit = projectParameters.querySelector(`[data-project-duration-unit="${CSS.escape(id)}"]`)?.value ?? "seconds";
    if (Number.isFinite(value) && value >= 0) {
      parameters[id] = Math.round(value * projectDurationUnitMultiplier(unit));
    }
  }
  for (const input of projectParameters.querySelectorAll("[data-project-parameter]")) {
    if (input.type === "checkbox") {
      parameters[input.dataset.projectParameter] = input.checked;
      continue;
    }
    const value = input.value.trim();
    if (value !== "") {
      parameters[input.dataset.projectParameter] = input.type === "number" ? Number(value) : value;
    }
  }
  const competitorUrls = [...projectParameters.querySelectorAll("[data-project-competitor-profile]:checked")]
    .map((input) => String(input.value || "").trim())
    .filter(Boolean);
  if (competitorUrls.length) {
    const manualUrls = String(parameters["profile-urls"] || "").split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    parameters["profile-urls"] = [...new Set([...manualUrls, ...competitorUrls])].join("\n");
  }
  return parameters;
}

function projectDurationParameterHtml(parameter) {
  const id = parameter.id;
  const label = parameter.label ?? id;
  const duration = splitProjectDurationValue(parameter.default, parameter.defaultUnit);
  const min = parameter.min !== undefined ? ` min="${parameter.min}"` : ' min="0"';
  const max = parameter.max !== undefined ? ` max="${parameter.max}"` : "";
  const step = parameter.step !== undefined ? ` step="${parameter.step}"` : ' step="1"';
  const options = [
    ["seconds", "seconds"],
    ["minutes", "minutes"],
    ["hours", "hours"],
  ].map(([value, optionLabel]) => `<option value="${value}"${duration.unit === value ? " selected" : ""}>${optionLabel}</option>`).join("");
  return `
    <label class="project-parameter-duration">
      <span>${escapeHtml(label)}</span>
      <div class="project-parameter-duration__controls">
        <input data-project-duration-value="${escapeHtml(id)}" type="number" value="${escapeHtml(duration.value)}"${min}${max}${step} />
        <select data-project-duration-unit="${escapeHtml(id)}">${options}</select>
      </div>
      ${projectParameterHelpHtml(parameter)}
    </label>
  `;
}

function projectParameterHelpHtml(parameter) {
  return parameter.help ? `<small class="project-parameter-help">${escapeHtml(parameter.help)}</small>` : "";
}

function splitProjectDurationValue(value, preferredUnit = "") {
  const seconds = Math.max(0, Number(value ?? 0) || 0);
  const preferred = String(preferredUnit || "").toLowerCase();
  if (preferred && ["seconds", "minutes", "hours"].includes(preferred)) {
    return { value: formatProjectDurationValue(seconds / projectDurationUnitMultiplier(preferred)), unit: preferred };
  }
  if (seconds > 0 && seconds % 3600 === 0) {
    return { value: formatProjectDurationValue(seconds / 3600), unit: "hours" };
  }
  if (seconds > 0 && seconds % 60 === 0) {
    return { value: formatProjectDurationValue(seconds / 60), unit: "minutes" };
  }
  return { value: formatProjectDurationValue(seconds), unit: "seconds" };
}

function projectDurationUnitMultiplier(unit) {
  if (unit === "hours") {
    return 3600;
  }
  if (unit === "minutes") {
    return 60;
  }
  return 1;
}

function formatProjectDurationValue(value) {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)));
}

function setProjectDurationValue(id, seconds, preferredUnit = "") {
  const input = projectParameters.querySelector(`[data-project-duration-value="${CSS.escape(id)}"]`);
  const unit = projectParameters.querySelector(`[data-project-duration-unit="${CSS.escape(id)}"]`);
  if (!input || !unit) {
    return;
  }
  const duration = splitProjectDurationValue(seconds, preferredUnit);
  input.value = duration.value;
  unit.value = duration.unit;
}

function projectListParameterStorageKey(id) {
  const projectId = projectSelect?.value || "project";
  return `${PROJECT_LIST_PARAMETERS_STORAGE_PREFIX}:${projectId}:${id}`;
}

function normalizeProjectListRow(row) {
  if (row && typeof row === "object") {
    return {
      name: String(row.name ?? row.label ?? "").trim(),
      url: String(row.url ?? row.value ?? "").trim(),
    };
  }
  return {
    name: "",
    url: String(row ?? "").trim(),
  };
}

function splitProjectListParameterRows(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeProjectListRow);
  }
  return splitProjectListParameterValue(value).map((url) => ({ name: "", url }));
}

function splitProjectListParameterValue(value) {
  return String(value ?? "")
    .replaceAll("\r", "\n")
    .replaceAll(";", "\n")
    .split("\n")
    .flatMap((chunk) => chunk.split(","))
    .map((item) => item.trim())
    .filter(Boolean);
}

function readStoredProjectListParameterRows(id) {
  try {
    const raw = window.localStorage?.getItem(projectListParameterStorageKey(id));
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return null;
    }
    const rows = parsed.map(normalizeProjectListRow);
    return rows.length ? rows : [{ name: "", url: "" }];
  } catch (_error) {
    return null;
  }
}

function persistProjectListParameterRows(id, rows) {
  if (!id) {
    return;
  }
  try {
    const normalizedRows = (Array.isArray(rows) ? rows : [])
      .map(normalizeProjectListRow);
    window.localStorage?.setItem(projectListParameterStorageKey(id), JSON.stringify(normalizedRows.length ? normalizedRows : [{ name: "", url: "" }]));
  } catch (_error) {
    // localStorage can be unavailable in private/restricted contexts; the job can still run.
  }
}

function projectListParameterRowHtml(id, parameter = {}, row = {}) {
  const normalized = normalizeProjectListRow(row);
  const placeholder = parameter.placeholder ?? "";
  const namePlaceholder = parameter.namePlaceholder ?? "Profile name";
  const renderedPlaceholder = placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : "";
  const renderedNamePlaceholder = namePlaceholder ? ` placeholder="${escapeHtml(namePlaceholder)}"` : "";
  return `
    <div class="project-parameter-list__row">
      <input data-project-list-name="${escapeHtml(id)}" type="text" value="${escapeHtml(normalized.name)}"${renderedNamePlaceholder} />
      <input data-project-list-input="${escapeHtml(id)}" type="text" value="${escapeHtml(normalized.url)}"${renderedPlaceholder} />
      <button class="button button--secondary button--compact" type="button" data-project-list-remove="${escapeHtml(id)}">−</button>
    </div>
  `;
}

function readProjectListRowsFromElement(list) {
  return [...list.querySelectorAll(".project-parameter-list__row")].map((row) => ({
    name: String(row.querySelector("[data-project-list-name]")?.value ?? "").trim(),
    url: String(row.querySelector("[data-project-list-input]")?.value ?? "").trim(),
  }));
}

function persistProjectListFromElement(list) {
  if (!list) {
    return;
  }
  persistProjectListParameterRows(list.dataset.projectList, readProjectListRowsFromElement(list));
}

function setProjectListRows(list, rows, parameter = {}) {
  if (!list) {
    return;
  }
  const id = list.dataset.projectList;
  const rowsContainer = list.querySelector(`[data-project-list-rows="${CSS.escape(id)}"]`);
  if (!rowsContainer) {
    return;
  }
  const normalizedRows = (Array.isArray(rows) && rows.length ? rows : [{ name: "", url: "" }]).map(normalizeProjectListRow);
  rowsContainer.innerHTML = normalizedRows.map((row) => projectListParameterRowHtml(id, parameter, row)).join("");
  setupProjectListRemoveButtons(list);
  setupProjectListInputPersistence(list);
  persistProjectListParameterRows(id, normalizedRows);
}

function setupProjectListParameters() {
  projectParameters.querySelectorAll("[data-project-list-add]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.projectListAdd;
      const definition = projectParameterDefinitions(selectedProjectAction()).find((parameter) => parameter.id === id) ?? {};
      const rows = projectParameters.querySelector(`[data-project-list-rows="${CSS.escape(id)}"]`);
      if (!rows) {
        return;
      }
      rows.insertAdjacentHTML("beforeend", projectListParameterRowHtml(id, definition, { name: "", url: "" }));
      setupProjectListRemoveButtons(rows.closest("[data-project-list]"));
      setupProjectListInputPersistence(rows.closest("[data-project-list]"));
      const names = rows.querySelectorAll("[data-project-list-name]");
      names[names.length - 1]?.focus?.();
      persistProjectListFromElement(rows.closest("[data-project-list]"));
    });
  });
  projectParameters.querySelectorAll("[data-project-list]").forEach((list) => {
    setupProjectListRemoveButtons(list);
    setupProjectListInputPersistence(list);
  });
}

function setupProjectListInputPersistence(list) {
  if (!list) {
    return;
  }
  list.querySelectorAll("[data-project-list-name], [data-project-list-input]").forEach((input) => {
    if (input.dataset.boundProjectListPersist === "true") {
      return;
    }
    input.dataset.boundProjectListPersist = "true";
    input.addEventListener("input", () => persistProjectListFromElement(list));
  });
}

function setupProjectListRemoveButtons(list) {
  if (!list) {
    return;
  }
  const buttons = [...list.querySelectorAll("[data-project-list-remove]")];
  buttons.forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      const rows = [...list.querySelectorAll(".project-parameter-list__row")];
      if (rows.length <= 1) {
        rows[0]?.querySelectorAll("[data-project-list-name], [data-project-list-input]").forEach((input) => {
          input.value = "";
        });
        persistProjectListFromElement(list);
        return;
      }
      button.closest(".project-parameter-list__row")?.remove();
      setupProjectListRemoveButtons(list);
      persistProjectListFromElement(list);
    });
  });
  const disabled = buttons.length <= 1;
  buttons.forEach((button) => {
    button.disabled = disabled;
  });
}

function readProjectParameterValue(parameterId, fallback = "") {
  if (!projectParameters || !parameterId) {
    return fallback;
  }
  const input = projectParameters.querySelector(`[data-project-parameter="${parameterId}"]`);
  if (!input) {
    const durationInput = projectParameters.querySelector(`[data-project-duration-value="${parameterId}"]`);
    if (durationInput) {
      const value = Number(String(durationInput.value ?? "").trim() || "0");
      const unit = projectParameters.querySelector(`[data-project-duration-unit="${parameterId}"]`)?.value ?? "seconds";
      return Number.isFinite(value) && value >= 0 ? Math.round(value * projectDurationUnitMultiplier(unit)) : fallback;
    }
    const list = projectParameters.querySelector(`[data-project-list="${parameterId}"]`);
    if (!list) {
      return fallback;
    }
    const value = readProjectListRowsFromElement(list).map((row) => row.url.trim()).filter(Boolean).join("\n");
    return value === "" ? fallback : value;
  }
  if (input.type === "checkbox") {
    return input.checked;
  }
  const value = String(input.value ?? "").trim();
  return value === "" ? fallback : value;
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
  for (const list of projectParameters.querySelectorAll("[data-project-list]")) {
    const id = list.dataset.projectList;
    const value = preset.parameters[id];
    if (value !== undefined && value !== null) {
      const definition = projectParameterDefinitions(selectedProjectAction()).find((parameter) => parameter.id === id) ?? {};
      setProjectListRows(list, splitProjectListParameterRows(value), definition);
    }
  }
  for (const input of projectParameters.querySelectorAll("[data-project-duration-value]")) {
    const id = input.dataset.projectDurationValue;
    const value = preset.parameters[id];
    if (value !== undefined && value !== null) {
      const definition = projectParameterDefinitions(selectedProjectAction()).find((parameter) => parameter.id === id) ?? {};
      setProjectDurationValue(id, value, definition.defaultUnit);
    }
  }
  projectPresetName.value = preset.name;
  projectResult.textContent = `Preset loaded: ${preset.name}`;
}

async function openProjectGateway(options = {}) {
  const panel = ["finished", "memory"].includes(options.panel) ? options.panel : "output";
  projectDialogMode = ["notifications", "memory"].includes(options.mode) ? options.mode : "gateway";
  projectError.textContent = "";
  projectResult.textContent = "Caricamento progetti...";
  try {
    availableProjects = await runtimeClient.listProjects();
    try {
      const report = await runtimeClient.getVintedReports(3650, 5000);
      projectCompetitorProfiles = Array.isArray(report?.competitor_profiles) ? report.competitor_profiles : [];
    } catch {
      projectCompetitorProfiles = [];
    }
    const ready = availableProjects.filter((project) => project.enabled && project.available);
    projectSelect.innerHTML = ready.map((project) => `<option value="${project.id}">${project.name}</option>`).join("");
    if (!ready.length && panel !== "memory") {
      throw new Error("No configured and available project found.");
    }
    if (ready.length) {
      renderProjectActions();
      await refreshProjectPresets();
      refreshProjectScheduleDefaults();
    }
    setProjectPanel(panel);
    syncProjectDialogMode();
    projectResult.textContent = panel === "finished"
      ? "Job history loaded."
      : panel === "memory"
        ? "Memory proposals loaded."
        : "Select an action to run with the current agent.";
    projectDialog.showModal();
    await refreshProjectJobHistory(false);
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "openProjectGateway", agentId: selectedAgentId });
    setBootMessage(error.message);
  }
}

function projectNameFor(job) {
  return availableProjects.find((project) => project.id === job.project_id)?.name ?? job.project_id ?? "Project";
}

function syncProjectDialogMode() {
  const notificationsMode = projectDialogMode === "notifications";
  const memoryMode = projectDialogMode === "memory";
  const compactMode = notificationsMode || memoryMode;
  if (projectDialogKicker) {
    projectDialogKicker.textContent = notificationsMode
      ? "Job notifications"
      : memoryMode
        ? "Memory Core"
        : "Project Gateway";
  }
  if (projectDialogTitle) {
    projectDialogTitle.textContent = notificationsMode
      ? "Jobs and notifications"
      : memoryMode
        ? "Memory Core"
        : "The Main Scraper";
  }
  if (projectGatewayHeaderGrid) {
    projectGatewayHeaderGrid.hidden = compactMode;
  }
  if (projectPresetsSection) {
    projectPresetsSection.hidden = compactMode;
  }
  if (projectParametersSection) {
    projectParametersSection.hidden = compactMode;
  }
  if (projectApprovalRow) {
    projectApprovalRow.hidden = compactMode;
  }
  if (projectScheduleSection) {
    projectScheduleSection.hidden = compactMode;
  }
  if (runProjectActionButton) {
    runProjectActionButton.hidden = compactMode;
  }
  if (projectJobFilters) {
    projectJobFilters.hidden = !notificationsMode;
  }
  if (projectDialogActions) {
    projectDialogActions.classList.toggle("dialog-actions--notifications", compactMode);
  }
}

function syncProjectJobFilterButtons() {
  for (const button of projectJobFilterButtons) {
    const active = button.dataset.jobFilter === projectJobFilter;
    button.classList.toggle("project-job-filter--active", active);
    button.setAttribute("aria-pressed", String(active));
  }
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

function formatReportNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value) || 0);
}

function formatReportDuration(seconds) {
  if (seconds == null || seconds === "" || !Number.isFinite(Number(seconds))) return "—";
  const total = Math.max(0, Math.floor(Number(seconds)));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatReportDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function reportArticleKey(article) {
  const itemId = String(article?.item_id || "").trim();
  const link = String(article?.link || "").trim();
  return itemId ? `item:${itemId}|${link}` : `link:${link}`;
}

function reportArticleCanSource(article) {
  return Boolean(String(article?.link || "").trim() && (
    String(article?.image_url || "").trim() || String(article?.archive_image_path || "").trim()
  ));
}

function selectedReportArticles() {
  const articles = Array.isArray(reportSnapshot?.articles) ? reportSnapshot.articles : [];
  return articles.filter((article) => reportSelectedArticleKeys.has(reportArticleKey(article)) && reportArticleCanSource(article));
}

function updateReportSourcingSelectionControls() {
  const count = selectedReportArticles().length;
  if (reportSelectedCount) reportSelectedCount.textContent = `${count} selected`;
  if (reportSourcingSelectedButton) reportSourcingSelectedButton.disabled = count === 0 || !runtimeClient.connected;
  if (reportClearSelectionButton) reportClearSelectionButton.disabled = count === 0;
}

function renderReportArticles() {
  if (!reportArticles) return;
  const articles = Array.isArray(reportSnapshot?.articles) ? reportSnapshot.articles : [];
  const reportArticleStatus = (article) => article.status === "sold"
    ? "sold"
    : (article.availability_status === "unavailable" || article.status === "unavailable" ? "unavailable" : "active");
  let filtered = reportArticleFilter === "all"
    ? articles
    : articles.filter((article) => reportArticleStatus(article) === reportArticleFilter);
  if (reportSaleTimeFilter !== "all") {
    const ranges = {
      "under-1": [0, 3600],
      "1-6": [3600, 21600],
      "6-12": [21600, 43200],
      "12-24": [43200, 86400],
      "over-24": [86400, Number.POSITIVE_INFINITY],
    };
    const [minimum, maximum] = ranges[reportSaleTimeFilter] ?? [0, Number.POSITIVE_INFINITY];
    filtered = filtered.filter((article) => {
      const seconds = Number(article.sold_after_seconds);
      return article.status === "sold" && Number.isFinite(seconds) && seconds >= minimum && seconds < maximum;
    });
  }
  if (!filtered.length) {
    reportArticles.innerHTML = '<div class="report-status">No articles match this filter.</div>';
    updateReportSourcingSelectionControls();
    return;
  }
  reportArticles.innerHTML = filtered.map((article) => {
    const status = reportArticleStatus(article);
    const key = reportArticleKey(article);
    const selectable = reportArticleCanSource(article);
    const selected = selectable && reportSelectedArticleKeys.has(key);
    const archivedImage = article.archive_image_path
      ? `/api/vinted/archive?path=${encodeURIComponent(article.archive_image_path)}`
      : "";
    const archivedScreenshot = article.archive_screenshot_path
      ? `/api/vinted/archive?path=${encodeURIComponent(article.archive_screenshot_path)}`
      : "";
    const imageSource = archivedImage || article.image_url || archivedScreenshot;
    const image = imageSource
      ? `<img src="${escapeHtml(imageSource)}" data-archive-fallback="${escapeHtml(archivedScreenshot)}" alt="" loading="lazy" />`
      : '<div class="report-article__placeholder" aria-hidden="true">◇</div>';
    const timing = status === "sold"
      ? `Sold in ${escapeHtml(article.sold_after_text || "—")} · ${escapeHtml(formatReportDate(article.sold_at))} · ${article.sale_duration_source === "listing_age" ? "listing time" : "deal discovery"}`
      : status === "unavailable"
        ? `Unavailable since ${escapeHtml(formatReportDate(article.unavailable_at))} · historical data preserved`
        : `Tracked since ${escapeHtml(formatReportDate(article.first_seen_at))}`;
    const favorites = Number.isFinite(Number(article.favorite_count))
      ? ` · ${formatReportNumber(article.favorite_count)} likes`
      : "";
    return `
      <article class="report-article ${selected ? "report-article--selected" : ""}">
        ${selectable ? `<label class="report-article__select" title="Select for visual sourcing"><input type="checkbox" data-report-article-select="${escapeHtml(key)}" ${selected ? "checked" : ""} aria-label="Select ${escapeHtml(article.name || "article")}" /></label>` : ""}
        <a class="report-article__link" href="${escapeHtml(article.link)}" target="_blank" rel="noopener noreferrer">
          ${image}
          <div class="report-article__body">
            <div class="report-article__top">
              <strong title="${escapeHtml(article.name)}">${escapeHtml(article.name)}</strong>
              <span class="report-pill ${status === "active" ? "report-pill--active" : ""}">${status}</span>
            </div>
            <p>${escapeHtml(article.price || "Price unavailable")}</p>
            <small>${timing}${favorites}</small>
          </div>
        </a>
      </article>
    `;
  }).join("");
  reportArticles.querySelectorAll("img").forEach((image) => {
    image.addEventListener("error", () => {
      const fallback = image.dataset.archiveFallback;
      if (fallback && image.src !== new URL(fallback, window.location.href).href) {
        image.src = fallback;
        return;
      }
      const placeholder = document.createElement("div");
      placeholder.className = "report-article__placeholder";
      placeholder.textContent = "◇";
      image.replaceWith(placeholder);
    }, { once: true });
  });
  reportArticles.querySelectorAll("[data-report-article-select]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const key = checkbox.dataset.reportArticleSelect || "";
      if (checkbox.checked) reportSelectedArticleKeys.add(key);
      else reportSelectedArticleKeys.delete(key);
      renderReportArticles();
    });
  });
  updateReportSourcingSelectionControls();
}

async function startReportSourcingBatch() {
  const articles = selectedReportArticles();
  if (!articles.length) return;
  const confirmed = window.confirm(`Start an isolated AliExpress visual search for ${articles.length} selected article${articles.length === 1 ? "" : "s"}?`);
  if (!confirmed) return;
  reportSourcingSelectedButton.disabled = true;
  reportStatus.textContent = `Starting visual sourcing for ${articles.length} selected article${articles.length === 1 ? "" : "s"}…`;
  try {
    const job = await runtimeClient.createVintedReportSourcingBatch(articles.map((article) => ({
      item_id: String(article.item_id || ""),
      name: String(article.name || ""),
      link: String(article.link || ""),
      image_url: String(article.image_url || ""),
      archive_image_path: String(article.archive_image_path || ""),
    })));
    syncProjectJobToast(job, "project.job.queued");
    reportStatus.textContent = `Sourcing Agent queued for ${articles.length} selected article${articles.length === 1 ? "" : "s"}. Follow progress in Active jobs.`;
    showGameNotification({
      title: "Visual sourcing queued",
      subtitle: `${articles.length} article${articles.length === 1 ? "" : "s"} assigned to Sourcing Agent`,
      tone: "active",
      key: `report-sourcing-${job.id}`,
    });
  } catch (error) {
    reportStatus.textContent = `Could not start visual sourcing: ${error.message}`;
    reportUiError("ui.vinted-reports.sourcing-batch", error, { phase: "create-sourcing-batch", selected_count: articles.length });
  } finally {
    updateReportSourcingSelectionControls();
  }
}

function renderReportCompetitors() {
  if (!reportCompetitors) return;
  const profiles = Array.isArray(reportSnapshot?.competitor_profiles)
    ? reportSnapshot.competitor_profiles
    : [];
  if (reportSelectedCompetitorId && !profiles.some((profile) => profile.seller_member_id === reportSelectedCompetitorId)) {
    reportSelectedCompetitorId = "";
  }
  if (reportCompetitorCount) reportCompetitorCount.textContent = formatReportNumber(profiles.length);
  const filtered = reportCompetitorStatusFilter === "all"
    ? profiles
    : profiles.filter((profile) => profile.status === reportCompetitorStatusFilter);
  if (!filtered.length) {
    reportCompetitors.innerHTML = '<div class="report-status">No competitor profiles match this filter.</div>';
    return;
  }
  if (reportCompetitorDetail) {
    const selectedSummary = profiles.find((profile) => profile.seller_member_id === reportSelectedCompetitorId);
    const selected = selectedSummary ? { ...selectedSummary, ...(reportCompetitorDetails.get(reportSelectedCompetitorId) || {}) } : null;
    if (!selected) {
      reportCompetitorDetail.hidden = true;
      reportCompetitorDetail.innerHTML = "";
    } else {
      const sellerName = selected.seller_name || `Seller ${selected.seller_member_id || "unknown"}`;
      const detailLoaded = reportCompetitorDetails.has(reportSelectedCompetitorId);
      const allItems = Array.isArray(selected.items) ? selected.items : [];
      const items = reportCompetitorItemFilter === "all" ? allItems : allItems.filter((item) => (item.status || "active") === reportCompetitorItemFilter);
      const itemCards = !detailLoaded ? '<div class="report-status">Loading saved listing history…</div>' : items.length ? items.map((item) => {
        const status = item.status || "active";
        const image = item.image_url
          ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" />`
          : '<span class="report-competitor-item__placeholder">◇</span>';
        const outcome = status === "sold"
          ? `Sold in ${item.sold_after_text || "unknown time"}${item.sold_at ? ` · ${formatReportDate(item.sold_at)}` : ""}`
          : status === "gone" ? "Removed / no longer active" : `Last seen ${formatReportDate(item.last_seen_at || item.first_seen_at)}`;
        return `<a class="report-competitor-item" href="${escapeHtml(item.link || selected.seller_profile_url || "#")}" target="_blank" rel="noopener noreferrer">
          ${image}<span><strong>${escapeHtml(item.name || "Marketplace item")}</strong><small>${escapeHtml(item.price || "Price unavailable")} · ${escapeHtml(outcome)}</small><small>${escapeHtml(item.search_term ? `Search: ${item.search_term}` : "")}</small></span>
          <span class="report-competitor-item__meta"><b>${item.favorite_count == null ? "—" : formatReportNumber(item.favorite_count)} likes</b><em class="report-pill report-pill--competitor-${escapeHtml(status)}">${escapeHtml(status)}</em></span>
        </a>`;
      }).join("") : '<div class="report-status">No listing history has been collected for this competitor yet.</div>';
      const averageSale = selected.average_sale_text || "—";
      const known = Number(selected.known_items_count) || 0;
      const active = Number(selected.active_items_count) || 0;
      const sold = Number(selected.sold_items_count) || 0;
      const gone = Number(selected.gone_items_count) || 0;
      const categories = [...new Set([
        ...(Array.isArray(selected.categories) ? selected.categories : []),
        "Charms e ciondoli", "Braccialetti", "Collane", "Anelli", "Orecchini", "Spille", "Altro",
      ])].sort((left, right) => left.localeCompare(right, "it"));
      const categoryOptions = categories.map((category) => `<option value="${escapeHtml(category)}"></option>`).join("");
      const distribution = known ? [
        ["active", active], ["sold", sold], ["gone", gone],
      ].filter(([, count]) => count > 0).map(([status, count]) => `<i data-status="${status}" style="--competitor-segment:${(Number(count) / known) * 100}%" title="${status}: ${count}"></i>`).join("") : "";
      reportCompetitorDetail.hidden = false;
      reportCompetitorDetail.innerHTML = `<header class="report-competitor-detail__heading">
        <div class="report-competitor-detail__identity"><span class="section-label">Competitor intelligence</span><h4>${escapeHtml(sellerName)}</h4><small>Member ID ${escapeHtml(selected.seller_member_id || "—")} · last observed ${escapeHtml(formatReportDate(selected.last_seen_at))}</small></div>
        <div class="report-competitor-detail__actions"><a class="button button--compact" href="${escapeHtml(selected.seller_profile_url || "#")}" target="_blank" rel="noopener noreferrer">Open profile ↗</a><label class="report-competitor-category"><span>Category</span><input data-competitor-sales-category list="competitor-category-${escapeHtml(selected.seller_member_id || "")}" placeholder="All categories" /><datalist id="competitor-category-${escapeHtml(selected.seller_member_id || "")}">${categoryOptions}</datalist></label><button class="button button--compact button--primary" type="button" data-competitor-check-sales ${reportCompetitorSaleChecks.has(reportSelectedCompetitorId) ? "disabled" : ""}>${reportCompetitorSaleChecks.has(reportSelectedCompetitorId) ? "Checking sold listings…" : "Check sold listings"}</button><button class="button button--compact" type="button" data-competitor-detail-close>Close</button></div>
      </header>
      <div class="report-competitor-detail__metrics">
        <span data-tone="known"><b>${formatReportNumber(known)}</b> listings known</span><span data-tone="active"><b>${formatReportNumber(active)}</b> live now</span>
        <span data-tone="sold"><b>${formatReportNumber(sold)}</b> confirmed sold</span><span data-tone="gone"><b>${formatReportNumber(gone)}</b> removed / unknown</span>
        <span data-tone="time"><b>${escapeHtml(averageSale)}</b> avg. sale time</span>
      </div>
      <div class="report-competitor-detail__distribution"><div>${distribution || '<i data-status="empty" style="--competitor-segment:100%"></i>'}</div><span><b>${formatReportNumber(sold)}</b> sold confirmed · <b>${formatReportNumber(active)}</b> currently active</span></div>
      <div class="report-competitor-detail__toolbar"><div class="report-competitor-detail__filters">
        ${[["all", "All", known], ["active", "Active", active], ["sold", "Sold", sold], ["gone", "Removed", gone]].map(([status, label, count]) => `<button type="button" data-competitor-item-filter="${status}" class="${reportCompetitorItemFilter === status ? "is-active" : ""}">${label} <b>${formatReportNumber(count)}</b></button>`).join("")}
      </div><small>${formatReportNumber(items.length)} of ${formatReportNumber(allItems.length)} listing${allItems.length === 1 ? "" : "s"} shown · “Removed” is never counted as sold without platform confirmation.</small></div>
      <div class="report-competitor-items">${itemCards}</div>`;
      reportCompetitorDetail.querySelector("[data-competitor-detail-close]")?.addEventListener("click", () => {
        reportSelectedCompetitorId = "";
        renderReportCompetitors();
      });
      reportCompetitorDetail.querySelector("[data-competitor-check-sales]")?.addEventListener("click", () => {
        const category = reportCompetitorDetail.querySelector("[data-competitor-sales-category]")?.value || "";
        startReportCompetitorSaleCheck(reportSelectedCompetitorId, category);
      });
      reportCompetitorDetail.querySelectorAll("img").forEach((image) => {
        image.addEventListener("error", () => image.replaceWith(Object.assign(document.createElement("span"), { className: "report-competitor-item__placeholder", textContent: "◇" })), { once: true });
      });
      reportCompetitorDetail.querySelectorAll("[data-competitor-item-filter]").forEach((button) => {
        button.addEventListener("click", () => {
          reportCompetitorItemFilter = button.dataset.competitorItemFilter || "all";
          renderReportCompetitors();
        });
      });
    }
  }
  reportCompetitors.innerHTML = filtered.map((profile) => {
    const sellerName = profile.seller_name || `Seller ${profile.seller_member_id || "unknown"}`;
    const keyword = profile.top_deal_keyword || "No confirmed keyword yet";
    const sameKeywordDeals = Number(profile.same_keyword_deal_count) || 0;
    const status = profile.status || "candidate";
    const content = `
      <div class="report-competitor__top">
        <div>
          <strong title="${escapeHtml(sellerName)}">${escapeHtml(sellerName)}</strong>
          <small>ID ${escapeHtml(profile.seller_member_id || "—")}</small>
        </div>
        <span class="report-pill report-pill--competitor-${escapeHtml(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="report-competitor__keyword">
        <span>${profile.manual_priority ? "Manually prioritized · top keyword" : "Top deal keyword"}</span>
        <strong>${escapeHtml(keyword)}</strong>
        <b>${formatReportNumber(sameKeywordDeals)} deals</b>
      </div>
      <div class="report-competitor__signals">
        <span><b>${formatReportNumber(profile.interesting_item_count)}</b> items</span>
        <span><b>${formatReportNumber(profile.distinct_search_terms)}</b> searches</span>
        <span><b>${formatReportNumber(profile.gone_item_count)}</b> gone/sold</span>
        <span><b>${formatReportNumber(profile.max_favorite_count)}</b> max likes</span>
      </div>
      <div class="report-competitor__footer">
        <span>Score <b>${formatReportNumber(profile.score)}</b></span>
        <span>Last seen ${escapeHtml(formatReportDate(profile.last_seen_at))}</span>
      </div><span class="report-competitor__open">View listing history →</span>`;
    return `<button class="report-competitor" type="button" data-competitor-detail="${escapeHtml(profile.seller_member_id || "")}" aria-label="View listing history for ${escapeHtml(sellerName)}">${content}</button>`;
  }).join("");
  reportCompetitors.querySelectorAll("[data-competitor-detail]").forEach((button) => {
    button.addEventListener("click", () => {
      reportSelectedCompetitorId = button.dataset.competitorDetail || "";
      reportCompetitorItemFilter = "all";
      renderReportCompetitors();
      reportCompetitorDetail?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      loadReportCompetitorDetail(reportSelectedCompetitorId);
    });
  });
}

async function startReportCompetitorSaleCheck(memberId, category = "") {
  if (!memberId || reportCompetitorSaleChecks.has(memberId) || !runtimeClient.connected) return;
  reportCompetitorSaleChecks.add(memberId);
  renderReportCompetitors();
  try {
    const job = await runtimeClient.checkVintedCompetitorSales(memberId, category);
    reportCompetitorSaleCheckJobs.set(job.id, memberId);
    syncProjectJobToast(job, "project.job.queued");
    reportStatus.textContent = `Sold-listing verification started${category ? ` for ${category}` : ""}. The competitor report will refresh when the job completes.`;
    showGameNotification({ title: "Sold listings check started", subtitle: "Vinted Analyst is verifying this seller's listings", tone: "active", key: `competitor-sales-${job.id}` });
  } catch (error) {
    reportCompetitorSaleChecks.delete(memberId);
    reportStatus.textContent = `Could not start sold-listing check: ${error.message}`;
    reportUiError("ui.vinted-reports.competitor-sales", error, { phase: "create-sale-check", member_id: memberId });
  } finally {
    renderReportCompetitors();
  }
}

async function loadReportCompetitorDetail(memberId) {
  if (!memberId || reportCompetitorDetails.has(memberId) || !runtimeClient.connected) return;
  try {
    const detail = await runtimeClient.getVintedCompetitorReport(memberId);
    reportCompetitorDetails.set(memberId, detail);
    if (reportSelectedCompetitorId === memberId) renderReportCompetitors();
  } catch (error) {
    if (reportSelectedCompetitorId === memberId && reportCompetitorDetail) {
      reportCompetitorDetail.hidden = false;
      reportCompetitorDetail.innerHTML = `<div class="report-status">Could not load competitor history: ${escapeHtml(error.message)}</div>`;
    }
    reportUiError("ui.vinted-reports.competitor-detail", error, { phase: "load-competitor-detail", member_id: memberId });
  }
}

function renderReportOwnedProfiles() {
  if (!reportOwnedProfiles) return;
  const profiles = Array.isArray(reportSnapshot?.owned_profiles) ? reportSnapshot.owned_profiles : [];
  if (reportOwnedCount) reportOwnedCount.textContent = formatReportNumber(profiles.length);
  if (!profiles.length) {
    if (reportOwnedSummary) reportOwnedSummary.innerHTML = "";
    if (reportOwnedInventoryChart) reportOwnedInventoryChart.innerHTML = "";
    if (reportOwnedSpeedChart) reportOwnedSpeedChart.innerHTML = "";
    reportOwnedProfiles.innerHTML = '<div class="report-status">No owned profiles configured yet.</div>';
    return;
  }
  const totals = profiles.reduce((result, profile) => {
    result.known += Number(profile.known_items_count) || 0;
    result.active += Number(profile.active_items_count) || 0;
    result.sold += Number(profile.sold_items_count) || 0;
    result.snapshots += Number(profile.snapshots_count) || 0;
    result.weightedSaleSeconds += (Number(profile.average_sale_seconds) || 0) * (Number(profile.sold_items_count) || 0);
    return result;
  }, { known: 0, active: 0, sold: 0, snapshots: 0, weightedSaleSeconds: 0 });
  const sellThrough = totals.active + totals.sold ? (totals.sold / (totals.active + totals.sold)) * 100 : 0;
  const averageSaleSeconds = totals.sold ? totals.weightedSaleSeconds / totals.sold : 0;
  const averageSaleHours = averageSaleSeconds / 3600;
  const averageSaleLabel = averageSaleSeconds >= 86400
    ? `${(averageSaleSeconds / 86400).toFixed(1)}d`
    : averageSaleSeconds ? `${averageSaleHours.toFixed(1)}h` : "—";
  if (reportOwnedSummary) {
    reportOwnedSummary.innerHTML = [
      [profiles.length, "Owned profiles", `${totals.snapshots} snapshots`],
      [totals.active, "Current listings", `${totals.known} products known`],
      [totals.sold, "Confirmed sold", `${sellThrough.toFixed(1)}% sell-through`],
      [averageSaleLabel, "Average sale time", "Confirmed sales only"],
    ].map(([value, label, note]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  }
  if (reportOwnedInventoryChart) {
    reportOwnedInventoryChart.innerHTML = profiles.map((profile) => {
      const items = Array.isArray(profile.items) ? profile.items : [];
      const counts = items.reduce((result, item) => {
        const status = ["sold", "gone", "observed"].includes(item.status) ? item.status : "active";
        result[status] += 1;
        return result;
      }, { active: 0, sold: 0, gone: 0, observed: 0 });
      const total = Math.max(counts.active + counts.sold + counts.gone + counts.observed, 1);
      const segments = ["active", "sold", "gone", "observed"].map((status) =>
        `<i data-tone="${status}" style="--segment:${(counts[status] / total) * 100}%" title="${status}: ${counts[status]}"></i>`
      ).join("");
      return `<div class="report-owned-chart-row"><div><strong>${escapeHtml(profile.display_name)}</strong><small>${formatReportNumber(total)} known</small></div><div class="report-owned-stack">${segments}</div><b>${formatReportNumber(profile.active_items_count)} live</b></div>`;
    }).join("") + '<div class="report-owned-legend"><span data-tone="active">Active</span><span data-tone="sold">Sold</span><span data-tone="gone">Gone</span><span data-tone="observed">Observed</span></div>';
  }
  if (reportOwnedSpeedChart) {
    const maxSpeed = Math.max(1, ...profiles.map((profile) => Number(profile.average_sale_seconds) || 0));
    reportOwnedSpeedChart.innerHTML = profiles.map((profile) => {
      const seconds = Number(profile.average_sale_seconds) || 0;
      const width = seconds ? Math.max((seconds / maxSpeed) * 100, 5) : 0;
      return `<div class="report-owned-speed-row"><div><strong>${escapeHtml(profile.display_name)}</strong><small>${formatReportNumber(profile.sold_items_count)} confirmed sales</small></div><div class="report-owned-speed-track"><i style="--speed:${width}%"></i></div><b>${escapeHtml(profile.average_sale_text || "—")}</b></div>`;
    }).join("") + '<p class="report-owned-chart-note">Shorter bars indicate faster average sales.</p>';
  }
  reportOwnedProfiles.innerHTML = profiles.map((profile) => {
    const allItems = Array.isArray(profile.items) ? profile.items : [];
    const items = allItems.filter((item) => {
      const status = item.status || "observed";
      const statusMatches = reportOwnedStatusFilter === "all" || status === reportOwnedStatusFilter;
      const searchText = `${item.name || ""} ${item.price || ""}`.toLowerCase();
      return statusMatches && (!reportOwnedSearchFilter || searchText.includes(reportOwnedSearchFilter));
    });
    const itemCards = items.length ? items.map((item) => {
      const status = item.status || "observed";
      const image = item.image_url
        ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" />`
        : '<span class="report-owned-item__placeholder">◇</span>';
      const timing = status === "sold"
        ? `Sold in ${escapeHtml(item.sold_after_text || "—")} · ${escapeHtml(formatReportDate(item.sold_at))}`
        : status === "gone" ? "Gone / sold / removed" : `Seen ${escapeHtml(formatReportDate(item.last_seen_at || item.first_seen_at))}`;
      return `<div class="report-owned-item">
        <a class="report-owned-item__link" href="${escapeHtml(item.link || profile.profile_url)}" target="_blank" rel="noopener noreferrer">${image}<span><strong>${escapeHtml(item.name || "Marketplace item")}</strong><small>${escapeHtml(item.price || "Price unavailable")} · ${timing}</small></span></a>
        <b class="report-pill ${status === "active" ? "report-pill--active" : ""}">${escapeHtml(status)}</b>
        <button class="button button--danger button--compact report-owned-item__ignore" type="button" data-owned-item-ignore="${escapeHtml(item.item_id || "")}" data-owned-item-member="${escapeHtml(profile.member_id)}" ${item.item_id ? "" : "disabled"} title="Escludi dal profilo e interrompi il monitoraggio">Non tracciare</button>
      </div>`;
    }).join("") : '<div class="report-status">No product history collected for this profile yet.</div>';
    return `<article class="report-owned-profile">
      <header>
        <div><a href="${escapeHtml(profile.profile_url)}" target="_blank" rel="noopener noreferrer"><strong>${escapeHtml(profile.display_name)}</strong></a><small>Member ID ${escapeHtml(profile.member_id)}</small></div>
        <button class="button button--danger button--compact" type="button" data-owned-profile-remove="${escapeHtml(profile.member_id)}">Remove</button>
      </header>
      <div class="report-owned-metrics">
        <span><b>${formatReportNumber(profile.known_items_count)}</b> known</span>
        <span><b>${formatReportNumber(profile.active_items_count)}</b> active</span>
        <span><b>${formatReportNumber(profile.sold_items_count)}</b> sold</span>
        <span><b>${escapeHtml(profile.average_sale_text || "—")}</b> avg. sale</span>
        <span><b>${formatReportNumber(profile.snapshots_count)}</b> snapshots</span>
      </div>
      <div class="report-owned-profile__caption"><span>${formatReportNumber(items.length)} of ${formatReportNumber(allItems.length)} products shown</span><span>Last snapshot ${escapeHtml(formatReportDate(profile.latest_snapshot_at))}</span></div>
      <div class="report-owned-items">${itemCards}</div>
    </article>`;
  }).join("");
  reportOwnedProfiles.querySelectorAll("img").forEach((image) => {
    image.addEventListener("error", () => image.replaceWith(Object.assign(document.createElement("span"), { className: "report-owned-item__placeholder", textContent: "◇" })), { once: true });
  });
}

function renderReportProcacciatore() {
  if (!reportProcacciatoreArticles) return;
  const report = reportSnapshot?.procacciatore ?? {};
  const summary = report.summary ?? {};
  const articles = Array.isArray(report.articles) ? report.articles : [];
  const topLiked = Array.isArray(report.top_liked) ? report.top_liked : [];
  const cohorts = Array.isArray(report.cohorts) ? report.cohorts : [];
  const brands = Array.isArray(report.brands) ? report.brands : [];
  const brandSummary = report.brand_summary ?? {};
  if (reportProcacciatoreCount) reportProcacciatoreCount.textContent = formatReportNumber(summary.tracked_count);
  if (reportProcacciatoreChecked) {
    reportProcacciatoreChecked.textContent = summary.last_checked_at
      ? `Ultimo controllo: ${formatReportDate(summary.last_checked_at)}`
      : report.available ? "In attesa del primo controllo" : "Archivio non ancora creato";
  }
  if (reportProcacciatoreSummary) {
    const metrics = [
      [formatReportNumber(summary.tracked_count), "Articoli tracciati", "Archivio Procacciatore"],
      [formatReportNumber(summary.active_count), "Ancora attivi", "Monitoraggio vendita"],
      [formatReportNumber(summary.sold_count), "Venduti", `${formatReportNumber(summary.unavailable_count)} non disponibili`],
      [formatReportDuration(summary.average_sale_seconds), "Tempo medio di vendita", `Mediana ${formatReportDuration(summary.median_sale_seconds)}`],
      [summary.average_sold_likes == null ? "—" : formatReportNumber(summary.average_sold_likes), "Like medi sui venduti", "Articoli con like noti"],
      [formatReportNumber(summary.observed_count), "Annunci osservati", `${formatReportNumber(summary.newly_observed_count)} nuovi nel periodo`],
      [formatReportNumber(summary.observed_supply_24h), "Offerta vista nelle ultime 24h", "Annunci distinti riapparsi di recente"],
      [summary.demand_supply_ratio == null ? "—" : `${(summary.demand_supply_ratio * 100).toFixed(1)}%`, "Vendite confermate / nuovi annunci", `${formatReportNumber(summary.period_sold_count)} venduti nel periodo · proxy sui soli tracciati`],
    ];
    reportProcacciatoreSummary.innerHTML = metrics.map(([value, label, note]) => `
      <article><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span><small>${escapeHtml(note)}</small></article>
    `).join("");
  }
  reportProcacciatoreTop.innerHTML = topLiked.length ? topLiked.slice(0, 12).map((article, index) => {
    const image = article.image_url
      ? `<img src="${escapeHtml(article.image_url)}" alt="" loading="lazy" />`
      : '<span class="report-procacciatore-placeholder">◇</span>';
    const soldTime = article.status === "sold" ? `Venduto in ${article.sold_after_text || "—"}` : article.status === "active" ? "Ancora monitorato" : "Non disponibile";
    return `<a class="report-procacciatore-card" href="${escapeHtml(article.link || "#")}" target="_blank" rel="noopener noreferrer">
      <span class="report-procacciatore-rank">#${index + 1}</span>${image}
      <span class="report-procacciatore-card__body"><strong>${escapeHtml(article.name || "Articolo")}</strong><small>${formatReportNumber(article.favorite_count)} like · ${escapeHtml(article.price || "Prezzo n/d")}</small><small>${escapeHtml(article.search_term || article.category || "Ricerca")}</small><small>${article.likes_per_hour == null ? "Velocità like: servono altri campioni" : `${article.likes_per_hour > 0 ? "+" : ""}${article.likes_per_hour} like/ora`} · accel. ${article.likes_acceleration == null ? "n/d" : `${article.likes_acceleration > 0 ? "+" : ""}${article.likes_acceleration} like/ora²`}</small><small>Variazione prezzo ${article.price_change_value == null ? "non campionata" : `${article.price_change_value > 0 ? "+" : ""}€${Number(article.price_change_value).toFixed(2)}`}</small><b>${escapeHtml(soldTime)}</b></span>
    </a>`;
  }).join("") : '<div class="report-status">Il Procacciatore non ha ancora raccolto articoli con like. Avvia una ricerca per iniziare.</div>';
  if (reportProcacciatoreBrandNote) {
    reportProcacciatoreBrandNote.textContent = `${formatReportNumber(brandSummary.observed_listings)} annunci distinti · ${formatReportNumber(brandSummary.labels)} etichette · ${formatReportNumber(brandSummary.generic_labels)} generiche/da verificare. Un articolo ripetuto in più keyword conta una sola volta.`;
  }
  if (reportProcacciatoreBrands) {
    const formatAveragePrice = (value) => value == null ? "—" : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(Number(value));
    reportProcacciatoreBrands.innerHTML = brands.length ? brands.map((brand) => {
      const generic = brand.label_type === "Etichetta generica / da verificare";
      return `<tr><td><strong>${escapeHtml(brand.name || "Senza etichetta")}</strong></td>
        <td><span class="report-procacciatore-label ${generic ? "report-procacciatore-label--generic" : ""}">${generic ? "Da verificare" : "Marchio / etichetta"}</span></td>
        <td>${formatReportNumber(brand.observed_count)}</td><td>${formatReportNumber(brand.sold_count)}</td>
        <td>${formatAveragePrice(brand.average_price)}</td><td>${brand.average_likes == null ? "—" : formatReportNumber(brand.average_likes)}</td>
        <td>${brand.sale_sample_size ? `${formatReportDuration(brand.average_sale_seconds)}<small class="report-procacciatore-cell-note">su ${formatReportNumber(brand.sale_sample_size)} vendite con durata nota</small>` : "—"}</td></tr>`;
    }).join("") : '<tr><td colspan="7" class="report-status">Nessuna etichetta disponibile nel periodo. Avvia una ricerca del Procacciatore per raccogliere dati.</td></tr>';
  }
  const cohortBody = document.querySelector("#report-procacciatore-cohorts");
  if (cohortBody) cohortBody.innerHTML = cohorts.length ? cohorts.map((cohort) => {
    const rate = cohort.sell_through_rate == null ? "—" : `${cohort.sell_through_rate}%`;
    const within24 = cohort.sale_sample_size ? `${cohort.sold_within_24h} (${Math.round(cohort.sold_within_24h / cohort.sale_sample_size * 100)}%)` : "—";
    const within72 = cohort.sale_sample_size ? `${cohort.sold_within_72h} (${Math.round(cohort.sold_within_72h / cohort.sale_sample_size * 100)}%)` : "—";
    return `<tr><td>${escapeHtml(cohort.search_term || "—")}</td><td>${escapeHtml(cohort.price_band || "—")}</td><td>${formatReportNumber(cohort.observed_count)}</td><td>${formatReportNumber(cohort.tracked_count)}</td><td>${formatReportNumber(cohort.active_count)}</td><td>${formatReportNumber(cohort.sold_count)}</td><td>${formatReportNumber(cohort.unavailable_count)}</td><td>${rate}</td><td>${within24}</td><td>${within72}</td><td>${formatReportDuration(cohort.median_sale_seconds)}</td><td>${formatReportNumber(cohort.sale_sample_size)}</td></tr>`;
  }).join("") : '<tr><td colspan="12" class="report-status">Servono osservazioni del Procacciatore e vendite confermate per costruire le coorti.</td></tr>';
  const filtered = reportProcacciatoreStatusFilter === "all"
    ? articles
    : articles.filter((article) => reportProcacciatoreStatusFilter === "unavailable"
      ? ["unavailable", "gone"].includes(article.status)
      : article.status === reportProcacciatoreStatusFilter);
  reportProcacciatoreArticles.innerHTML = filtered.length ? filtered.map((article) => {
    const status = article.status === "gone" ? "unavailable" : article.status || "active";
    const image = article.image_url
      ? `<img src="${escapeHtml(article.image_url)}" alt="" loading="lazy" />`
      : '<span class="report-procacciatore-placeholder">◇</span>';
    return `<tr><td><a class="report-procacciatore-item" href="${escapeHtml(article.link || "#")}" target="_blank" rel="noopener noreferrer">${image}<span><strong>${escapeHtml(article.name || "Articolo")}</strong><small>${escapeHtml(article.item_id || "")}</small></span></a></td>
      <td>${article.favorite_count == null ? "—" : formatReportNumber(article.favorite_count)}${article.likes_per_hour == null ? "" : `<small class="report-procacciatore-cell-note">${article.likes_per_hour > 0 ? "+" : ""}${article.likes_per_hour}/h</small>`}</td><td>${escapeHtml(article.price || "—")}${article.price_change_value == null ? "" : `<small class="report-procacciatore-cell-note">${article.price_change_value > 0 ? "+" : ""}€${Number(article.price_change_value).toFixed(2)}</small>`}</td><td>${escapeHtml(article.search_term || article.category || "—")}</td>
      <td><span class="report-pill ${status === "active" ? "report-pill--active" : status === "sold" ? "report-pill--sold" : ""}">${escapeHtml(status)}</span></td>
      <td>${escapeHtml(formatReportDate(article.first_seen_at))}</td><td>${escapeHtml(formatReportDate(article.last_checked_at))}</td>
      <td>${article.status === "sold" ? escapeHtml(article.sold_after_text || "—") : "—"}</td></tr>`;
  }).join("") : '<tr><td colspan="8" class="report-status">Nessun articolo per questo stato.</td></tr>';
  reportProcacciatoreArticles.querySelectorAll("img").forEach((image) => {
    image.addEventListener("error", () => image.replaceWith(Object.assign(document.createElement("span"), { className: "report-procacciatore-placeholder", textContent: "◇" })), { once: true });
  });
}

function renderVintedReport(snapshot) {
  reportSnapshot = snapshot;
  reportCompetitorDetails.clear();
  const eligible = new Set((Array.isArray(snapshot?.articles) ? snapshot.articles : [])
    .filter(reportArticleCanSource)
    .map(reportArticleKey));
  reportSelectedArticleKeys = new Set([...reportSelectedArticleKeys].filter((key) => eligible.has(key)));
  const summary = snapshot?.summary ?? {};
  const metrics = [
    ["Analyzed articles", formatReportNumber(summary.total_items), "Current database"],
    ["Active deals", formatReportNumber(summary.active_deals), "Still being tracked"],
    ["Sold in period", formatReportNumber(summary.sold_in_period), `${snapshot.period_days} day window`],
    ["Average sale time", summary.average_sale_text || "—", `Median ${summary.median_sale_text || "—"}`],
    ["Conversion", `${Number(summary.conversion_rate || 0).toFixed(1)}%`, `${formatReportNumber(summary.sold_total)} confirmed sold`],
    ["Competitors", formatReportNumber(summary.competitors), `${formatReportNumber(summary.priority_competitors)} confirmed / priority`],
  ];
  reportMetrics.innerHTML = metrics.map(([label, value, note]) => `
    <article class="report-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>
  `).join("");

  const daily = Array.isArray(snapshot.daily_sales) ? snapshot.daily_sales : [];
  const visibleDaily = daily.slice(-60);
  const maxDaily = Math.max(1, ...visibleDaily.map((row) => Number(row.sold_count) || 0));
  reportSalesChart.innerHTML = visibleDaily.map((row) => {
    const count = Number(row.sold_count) || 0;
    const height = count ? Math.max((count / maxDaily) * 100, 5) : 2;
    return `<div class="report-bar" style="--bar-height:${height}%" title="${escapeHtml(row.date)} · ${count} sold"><span>${count || ""}</span></div>`;
  }).join("");
  reportSalesCaption.textContent = `${formatReportNumber(summary.sold_in_period)} sold · last ${snapshot.period_days} days`;

  const distribution = Array.isArray(snapshot.status_distribution) ? snapshot.status_distribution : [];
  const maxStatus = Math.max(1, ...distribution.map((row) => Number(row.value) || 0));
  reportStatusChart.innerHTML = distribution.map((row) => `
    <div class="report-distribution__row" data-tone="${escapeHtml(row.tone)}">
      <span>${escapeHtml(row.label)}</span>
      <div class="report-progress"><i style="--progress:${Math.max((Number(row.value) / maxStatus) * 100, row.value ? 4 : 0)}%"></i></div>
      <strong>${formatReportNumber(row.value)}</strong>
    </div>
  `).join("");

  const searches = Array.isArray(snapshot.top_searches) ? snapshot.top_searches : [];
  const maxSearch = Math.max(1, ...searches.map((row) => Number(row.seen) || 0));
  reportSearchRanking.innerHTML = searches.length ? searches.map((row) => `
    <div class="report-ranking__row">
      <span title="${escapeHtml(row.term)}">${escapeHtml(row.term)}</span>
      <div class="report-progress"><i style="--progress:${Math.max((Number(row.seen) / maxSearch) * 100, 4)}%"></i></div>
      <strong>${formatReportNumber(row.seen)}</strong>
    </div>
  `).join("") : '<div class="report-status">No search history yet.</div>';

  const keywordRows = Array.isArray(snapshot.keyword_metrics) ? snapshot.keyword_metrics : [];
  reportKeywordCount.textContent = formatReportNumber(keywordRows.length);
  const keywordTotals = keywordRows.reduce((totals, row) => {
    totals.searches += Number(row.search_runs) || 0;
    totals.sold += Number(row.sold_items) || 0;
    totals.active += Number(row.active_items) || 0;
    return totals;
  }, { searches: 0, sold: 0, active: 0 });
  reportKeywordSummary.innerHTML = [
    ["Keywords tracked", formatReportNumber(keywordRows.length)],
    ["Search runs", formatReportNumber(keywordTotals.searches)],
    ["Tracked sold", formatReportNumber(keywordTotals.sold)],
    ["Tracked active", formatReportNumber(keywordTotals.active)],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  reportKeywords.innerHTML = keywordRows.length ? keywordRows.map((row) => `
    <tr data-keyword-row data-keyword="${escapeHtml(String(row.keyword || "").toLowerCase())}">
      <td><strong>${escapeHtml(row.keyword || "—")}</strong><small>Last searched ${escapeHtml(formatReportDate(row.last_searched_at))}</small></td>
      <td>${formatReportNumber(row.search_runs)}</td><td>${formatReportNumber(row.run_result_count)}</td>
      <td>${formatReportNumber(row.items_seen)}</td><td>${formatReportNumber(row.sold_items)}</td>
      <td>${formatReportNumber(row.active_items)}</td><td>${formatReportNumber(row.unavailable_items)}</td>
      <td>${Number(row.sell_through_percent || 0).toFixed(1)}%</td>
      <td>${row.average_price == null ? "—" : `€${Number(row.average_price).toFixed(2)}`}</td>
      <td>${row.average_likes == null ? "—" : Number(row.average_likes).toFixed(1)}</td>
      <td>${escapeHtml(formatReportDuration(row.average_sale_seconds))}</td>
      <td>${escapeHtml(formatReportDuration(row.median_sale_seconds))}</td>
    </tr>
  `).join("") : '<tr><td colspan="12" class="report-status">No keyword-level tracking data for this period yet.</td></tr>';

  reportStatus.textContent = `Updated ${formatReportDate(snapshot.generated_at)} · ${formatReportNumber(summary.unavailable_items)} unavailable articles preserved`;
  renderReportArticles();
  renderReportCompetitors();
  renderReportOwnedProfiles();
  renderReportProcacciatore();
}

async function loadVintedReport() {
  if (!runtimeClient.connected) {
    reportStatus.textContent = "Start the runtime to load reports.";
    return;
  }
  reportRefreshButton.disabled = true;
  reportStatus.textContent = "Loading marketplace report…";
  try {
    const snapshot = await runtimeClient.getVintedReports(Number(reportPeriod.value) || 30, 5000);
    if (!snapshot.available) {
      reportStatus.textContent = "The scraper database is not available yet.";
      reportMetrics.innerHTML = "";
      reportArticles.innerHTML = "";
      return;
    }
    renderVintedReport(snapshot);
  } catch (error) {
    reportStatus.textContent = `Report load failed: ${error.message}`;
    reportUiError("ui.vinted-reports.load", error, { phase: "load-vinted-reports" });
  } finally {
    reportRefreshButton.disabled = false;
  }
}

async function openVintedReports() {
  if (!reportDialog.open) reportDialog.showModal();
  await loadVintedReport();
}

function monitoringJobsForActions(jobs) {
  const actionIds = new Set(monitoringJobDefinitions.map((definition) => definition.action));
  return jobs.filter((job) => actionIds.has(job.action));
}

function monitoringStateLabel(job) {
  const labels = { running: "In esecuzione", queued: "In coda", scheduled: "Programmato", completed: "Completato", failed: "Fallito", cancelled: "Fermato" };
  return labels[job?.state] || "Non avviato";
}

function renderMonitoringDashboard(jobs = []) {
  if (!monitoringJobs) return;
  const relevantJobs = monitoringJobsForActions(jobs);
  const activeCount = relevantJobs.filter((job) => ["running", "queued", "scheduled"].includes(job.state)).length;
  if (monitoringCount) monitoringCount.textContent = `${activeCount}/2`;
  monitoringJobs.innerHTML = monitoringJobDefinitions.map((definition) => {
    const job = relevantJobs
      .filter((candidate) => candidate.action === definition.action)
      .sort((left, right) => String(right.updated_at || right.created_at).localeCompare(String(left.updated_at || left.created_at)))[0];
    const active = Boolean(job && ["running", "queued", "scheduled"].includes(job.state));
    const status = job ? monitoringStateLabel(job) : "Non avviato";
    const timestamp = job?.updated_at || job?.created_at;
    const time = timestamp ? new Date(timestamp).toLocaleString("it-IT") : "";
    const detail = definition.action === "vinted.continuous_monitoring"
      ? "Ricerca charm/Pandora continua · tre profili personali ogni ora · competitor prioritario 306388399 · DB scraper.db"
      : "Procacciatore gioielli · 500 annunci per ricerca · prezzo minimo 15 € · almeno 20 like · senza login · DB procacciatore.db";
    return `<article class="monitoring-job-card ${active ? "monitoring-job-card--active" : ""}">
      <div class="monitoring-job-card__top"><span class="monitoring-job-card__indicator" aria-hidden="true"></span><div><span class="section-label">${active ? "Attivo" : "Stato"}</span><h4>${escapeHtml(definition.label)}</h4></div><span class="monitoring-job-card__state">${escapeHtml(status)}</span></div>
      <p>${escapeHtml(detail)}</p>
      <div class="monitoring-job-card__meta"><span>${job?.id ? `Job ${escapeHtml(job.id)}` : "Nessun job registrato"}</span>${time ? `<time>${escapeHtml(time)}</time>` : ""}</div>
      <div class="monitoring-job-card__actions">${active
        ? `<button class="button button--danger button--compact" type="button" data-monitoring-stop="${escapeHtml(job.id)}">Ferma</button>`
        : `<button class="button button--primary button--compact" type="button" data-monitoring-start="${escapeHtml(definition.action)}">Avvia ora</button>`}</div>
    </article>`;
  }).join("");
  if (monitoringStatus && !monitoringStatus.textContent.includes("Avvio automatico non riuscito")) {
    monitoringStatus.textContent = activeCount === 2
      ? "Entrambi i monitoraggi sono attivi. Lo stato si aggiorna automaticamente."
      : `${activeCount} di 2 monitoraggi attivi. I monitoraggi mancanti partiranno automaticamente all’avvio dell’app.`;
  }
}

async function refreshMonitoringDashboard() {
  if (!runtimeClient.connected) {
    if (monitoringStatus) monitoringStatus.textContent = "Runtime non connesso: avvia prima il runtime dell’app.";
    return [];
  }
  try {
    const jobs = await runtimeClient.listProjectJobs();
    renderMonitoringDashboard(jobs);
    return jobs;
  } catch (error) {
    if (monitoringStatus) monitoringStatus.textContent = `Impossibile aggiornare lo stato: ${error.message}`;
    return [];
  }
}

async function startMonitoringJob(definition, { automatic = false } = {}) {
  if (!runtimeClient.connected) throw new Error("Avvia prima il runtime dell’app.");
  const job = await runtimeClient.createProjectJob({
    project_id: "main-scraper",
    action: definition.action,
    parameters: definition.parameters,
    agent_id: definition.agent_id,
    approved: true,
  });
  syncProjectJobToast(job, "project.job.queued");
  if (monitoringStatus) monitoringStatus.textContent = automatic
    ? `Avvio automatico: ${definition.label}…`
    : `${definition.label} avviato.`;
  return job;
}

async function ensureAutoMonitoringJobs() {
  if (monitoringAutoStartTriggered || !runtimeClient.connected) return;
  monitoringAutoStartTriggered = true;
  if (monitoringStatus) monitoringStatus.textContent = "Controllo dei monitoraggi attivi…";
  try {
    const jobs = await runtimeClient.listProjectJobs();
    const activeActions = new Set(monitoringJobsForActions(jobs)
      .filter((job) => ["running", "queued", "scheduled"].includes(job.state))
      .map((job) => job.action));
    for (const definition of monitoringJobDefinitions) {
      if (activeActions.has(definition.action)) continue;
      try {
        await startMonitoringJob(definition, { automatic: true });
      } catch (error) {
        runtimeClient.logClient("error", error.message, { operation: "autoStartVintedMonitoring", action: definition.action });
        if (monitoringStatus) monitoringStatus.textContent = `Avvio automatico non riuscito per ${definition.label}: ${error.message}`;
      }
    }
    await refreshMonitoringDashboard();
  } catch (error) {
    monitoringAutoStartTriggered = false;
    if (monitoringStatus) monitoringStatus.textContent = `Avvio automatico non riuscito: ${error.message}`;
    runtimeClient.logClient("error", error.message, { operation: "autoStartVintedMonitoring.listJobs" });
  }
}

async function openMonitoringDashboard() {
  if (!reportDialog.open) reportDialog.showModal();
  reportTabButtons.find((button) => button.dataset.reportTab === "monitoring")?.click();
  await refreshMonitoringDashboard();
}

let linkedinReportPosts = [];
let selectedLinkedInPostId = "";
const linkedinRewritePromptsByPost = new Map();
let linkedinSearchTimer = 0;

function safeLinkedInMediaUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" && (url.hostname === "licdn.com" || url.hostname.endsWith(".licdn.com")) ? url.href : "";
  } catch (_error) { return ""; }
}

function linkedinRewriteUserPrompt(postText, instruction) {
  return `Post di partenza:\n${String(postText || "").slice(0, 10000)}\n\nIndicazioni aggiuntive: ${String(instruction || "").trim() || "tono tranquillo, come se spiegassi a un amico"}`;
}

function linkedinPostIsInteresting(post) {
  const match = String(post.published_text || "").match(/(?:^|\s)(\d+)\s*d\b/i);
  const seen = Date.parse(post.last_seen_at || "");
  if (!match || !Number.isFinite(seen)) return false;
  const approximateDays = Number(match[1]) + Math.max(0, (Date.now() - seen) / 86_400_000);
  return Number(post.reactions) >= 1000 && approximateDays >= 1 && approximateDays < 4;
}

function renderLinkedInPosts() {
  const filter = reportLinkedInFilter?.value || "interesting";
  const posts = linkedinReportPosts.filter((post) => {
    if (filter === "interesting") return linkedinPostIsInteresting(post);
    if (filter === "images") return Boolean(post.image_url) || Number(post.image_count) > 0;
    if (filter === "videos") return Number(post.video_count) > 0;
    return true;
  });
  reportLinkedInStatus.textContent = `${posts.length} visualizzati · ${linkedinReportPosts.length} caricati`;
  reportLinkedInCount.textContent = String(linkedinReportPosts.filter(linkedinPostIsInteresting).length);
  reportLinkedInList.innerHTML = posts.length ? posts.map((post) => {
    const image = safeLinkedInMediaUrl(post.image_url);
    const selected = selectedLinkedInPostId === post.post_id;
    return `<button class="linkedin-post-row${selected ? " linkedin-post-row--selected" : ""}" type="button" data-linkedin-post-id="${escapeHtml(post.post_id)}">
      ${image ? `<img src="${escapeHtml(image)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span class="linkedin-post-row__placeholder">${Number(post.video_count) ? "▶" : "in"}</span>`}
      <span class="linkedin-post-row__body"><strong>${escapeHtml(post.author || "Autore non disponibile")}</strong><small>${escapeHtml(String(post.text || "").slice(0, 170)) || "Testo non disponibile"}</small><em>${Number(post.reactions).toLocaleString("it-IT")} reazioni · ${escapeHtml(post.published_text || "età non nota")}${Number(post.video_count) ? " · video" : ""}</em></span>
    </button>`;
  }).join("") : '<p class="linkedin-empty">Nessun post con questo filtro. Prova “Tutti i post”.</p>';
}

async function loadLinkedInPosts() {
  if (!runtimeClient.connected) {
    reportLinkedInStatus.textContent = "Avvia il runtime per leggere i post.";
    return;
  }
  reportLinkedInRefresh.disabled = true;
  reportLinkedInStatus.textContent = "Caricamento post…";
  try {
    const result = await runtimeClient.getLinkedInPosts(reportLinkedInSearch.value.trim(), 2000);
    linkedinReportPosts = Array.isArray(result.posts) ? result.posts : [];
    renderLinkedInPosts();
    if (selectedLinkedInPostId && linkedinReportPosts.some((post) => post.post_id === selectedLinkedInPostId)) {
      await loadLinkedInDetail(selectedLinkedInPostId);
    } else if (selectedLinkedInPostId) {
      selectedLinkedInPostId = "";
    }
  } catch (error) {
    reportLinkedInStatus.textContent = `Errore: ${error.message}`;
    reportUiError("ui.linkedin-reports.load", error, { phase: "load-linkedin-posts" });
  } finally { reportLinkedInRefresh.disabled = false; }
}

async function loadLinkedInDetail(postId) {
  selectedLinkedInPostId = postId;
  renderLinkedInPosts();
  reportLinkedInDetail.innerHTML = '<p class="linkedin-empty">Caricamento dettaglio…</p>';
  try {
    const post = await runtimeClient.getLinkedInPost(postId);
    if (selectedLinkedInPostId !== postId) return;
    const latest = post.observations?.[0] || {};
    const link = String(post.link || "").startsWith("https://www.linkedin.com/") && post.link !== "https://www.linkedin.com/feed/" ? post.link : "";
    const media = Array.isArray(post.media) ? post.media : [];
    const mediaHtml = media.length ? media.map((item) => {
      const preview = safeLinkedInMediaUrl(item.kind === "image" ? item.urls?.[0] : item.poster_url);
      const videoUrl = item.kind === "video" ? safeLinkedInMediaUrl(item.urls?.[0]) : "";
      const original = item.archive?.find((archive) => archive.variant === "original");
      const poster = item.archive?.find((archive) => archive.variant === "poster");
      const fileHref = (variant) => `/api/linkedin/posts/${encodeURIComponent(postId)}/media/${item.index}/file?variant=${variant}`;
      return `<div class="linkedin-media-card">
        ${videoUrl ? `<video src="${escapeHtml(videoUrl)}" poster="${escapeHtml(preview)}" controls preload="none" referrerpolicy="no-referrer"></video>` : preview ? `<img src="${escapeHtml(preview)}" alt="${item.kind === "video" ? "Anteprima video" : "Immagine del post"}" loading="lazy" referrerpolicy="no-referrer">` : `<div class="linkedin-media-card__missing">${item.kind === "video" ? "Video rilevato · anteprima non disponibile" : "Immagine non disponibile"}</div>`}
        <div class="linkedin-media-card__actions"><strong>${item.kind === "video" ? "Video" : "Immagine"} ${item.index + 1}</strong>
          ${original ? `<a class="button" href="${fileHref("original")}" download>Scarica file</a>` : `<button class="button" type="button" data-linkedin-archive="${item.index}" ${item.urls?.length ? "" : "disabled"}>Salva nel PC</button>`}
          ${item.kind === "video" && item.poster_url ? (poster ? `<a class="button" href="${fileHref("poster")}" download>Scarica anteprima</a>` : `<button class="button" type="button" data-linkedin-poster="${item.index}">Salva anteprima</button>`) : ""}
        </div>
        ${item.kind === "video" && !item.urls?.length ? '<small>Stream senza URL diretto: il video non è ancora scaricabile. L’anteprima, se presente, si può salvare separatamente.</small>' : ""}
      </div>`;
    }).join("") : '<p class="linkedin-empty">Nessun media rilevato per questo post. I video saranno identificati nei prossimi giri del LinkedIn Agent.</p>';
    const drafts = (post.rewrites || []).map((draft) => `<div class="linkedin-draft"><small>${escapeHtml(formatReportDate(draft.created_at))} · ${escapeHtml(draft.model)}</small><textarea readonly>${escapeHtml(draft.draft)}</textarea><button class="button" type="button" data-linkedin-copy="${draft.rewrite_id}">Copia bozza</button> <button class="button" type="button" data-linkedin-send-to-publisher="${draft.rewrite_id}">Prepara pubblicazione</button></div>`).join("");
    const promptValue = linkedinRewritePromptsByPost.get(postId) ?? linkedinRewriteUserPrompt(post.text, "");
    reportLinkedInDetail.innerHTML = `<div class="linkedin-detail-heading"><div><span class="section-label">${escapeHtml(post.author || "Autore sconosciuto")}</span><h3>Analisi post</h3><small>${escapeHtml(post.published_text || "Età non nota")} · ${Number(latest.reactions || 0).toLocaleString("it-IT")} reazioni · ${Number(latest.comments || 0).toLocaleString("it-IT")} commenti · ${Number(latest.reposts || 0).toLocaleString("it-IT")} repost</small></div>${link ? `<a class="button" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Apri post</a>` : '<span class="linkedin-no-link">Permalink non disponibile</span>'}</div>
      <div class="linkedin-original-text">${escapeHtml(post.text || "Testo non disponibile")}</div>
      <h4>Media</h4><div class="linkedin-media-grid">${mediaHtml}</div>
      <div class="linkedin-rewrite"><h4>Riscrivi con OpenAI</h4><p>Questo è l’unico prompt inviato al modello: puoi modificarlo liberamente, inclusa la lingua. Nessuna istruzione di sistema aggiuntiva viene applicata.</p><details class="linkedin-prompt-inspection" open><summary>Prompt modificabile</summary><label for="linkedin-rewrite-prompt">Prompt completo</label><textarea id="linkedin-rewrite-prompt" maxlength="15000">${escapeHtml(promptValue)}</textarea></details><button class="button button--primary" type="button" data-linkedin-rewrite>Genera bozza</button><p id="linkedin-detail-status" role="status"></p>${drafts}</div>`;
  } catch (error) {
    reportLinkedInDetail.innerHTML = `<p class="linkedin-empty">Dettaglio non disponibile: ${escapeHtml(error.message)}</p>`;
  }
}

let linkedinPublisherState = null;
let linkedinPublicationDrafts = [];

function renderLinkedInPublisher() {
  const state = linkedinPublisherState || {};
  linkedinPublisherAccount.textContent = state.ready
    ? "Browser pronto. Il login LinkedIn verrà controllato all’avvio della pubblicazione."
    : "Ambiente Chrome del Main Scraper non disponibile: impossibile pubblicare.";
  linkedinPublisherDrafts.innerHTML = linkedinPublicationDrafts.length ? linkedinPublicationDrafts.map((draft) => {
    const editable = draft.state === "draft";
    return `<article class="linkedin-publication-draft" data-publication-draft-id="${draft.draft_id}">
      <div class="linkedin-publication-draft__heading"><strong>Bozza #${draft.draft_id}</strong><span class="linkedin-publication-state linkedin-publication-state--${escapeHtml(draft.state)}">${escapeHtml(draft.state)}</span></div>
      ${draft.has_attachment ? `<div class="linkedin-publication-image-wrap"><img class="linkedin-publication-image" src="/api/linkedin/publisher/drafts/${encodeURIComponent(draft.draft_id)}/attachment?v=${encodeURIComponent(draft.updated_at || "")}" alt="Immagine allegata alla bozza" loading="lazy"><small class="linkedin-publication-attachment">📷 Immagine originale allegata · ${escapeHtml(draft.attachment_name || "")}</small></div>` : draft.source_post_id ? `<small class="linkedin-publication-attachment">${escapeHtml(draft.image_error || "Recupero immagine originale del post…")}</small>` : ""}
      <textarea maxlength="3000" ${editable ? "" : "readonly"}>${escapeHtml(draft.body)}</textarea>
      ${draft.error ? `<small>${escapeHtml(draft.error)}</small>` : ""}
      ${draft.post_url ? `<a href="${escapeHtml(draft.post_url)}" target="_blank" rel="noopener noreferrer">Apri post pubblicato</a>` : ""}
      ${editable ? `<div class="linkedin-publisher-actions"><button class="button" type="button" data-publication-save>Salva modifiche</button><button class="button button--primary" type="button" data-publication-publish ${state.ready ? "" : "disabled"}>Rivedi e pubblica</button></div>` : ""}
    </article>`;
  }).join("") : '<p class="linkedin-empty">Nessuna bozza. Puoi scriverne una qui o partire da un post analizzato.</p>';
}

async function loadLinkedInPublisher() {
  if (!runtimeClient.connected) return;
  try {
    const [state, drafts] = await Promise.all([runtimeClient.getLinkedInPublisherStatus(), runtimeClient.getLinkedInDrafts()]);
    linkedinPublisherState = state;
    linkedinPublicationDrafts = Array.isArray(drafts.drafts) ? drafts.drafts : [];
    const missingSourceImages = linkedinPublicationDrafts.filter((draft) => draft.state === "draft" && draft.source_post_id && !draft.has_attachment).slice(0, 10);
    for (const draft of missingSourceImages) {
      try {
        const updated = await runtimeClient.attachLinkedInDraftSourceImage(draft.draft_id);
        linkedinPublicationDrafts = linkedinPublicationDrafts.map((item) => item.draft_id === updated.draft_id ? updated : item);
      } catch (error) {
        linkedinPublicationDrafts = linkedinPublicationDrafts.map((item) => item.draft_id === draft.draft_id
          ? { ...item, image_error: `Immagine sorgente non recuperata: ${error.message}` }
          : item);
      }
    }
    renderLinkedInPublisher();
    linkedinPublisherStatus.textContent = "";
  } catch (error) {
    linkedinPublisherStatus.textContent = `Publisher non disponibile: ${error.message}`;
  }
}

function aiNewsSections(summary) {
  const lines = String(summary || "").split(/\r?\n/);
  const scriptIndex = lines.findIndex((line) => /script\s+(?:parlato|per\s+(?:video|reel|short))/i.test(line));
  if (scriptIndex < 0) return { news: lines.join("\n").trim(), script: "" };
  const sourceIndex = lines.findIndex((line, index) => index > scriptIndex && /fonti\s+(?:per\s+)?(?:lo\s+)?script/i.test(line));
  return {
    news: lines.slice(0, scriptIndex).join("\n").trim(),
    script: lines.slice(scriptIndex + 1, sourceIndex < 0 ? undefined : sourceIndex).join("\n").replaceAll("**", "").trim(),
  };
}

function aiNewsTextHtml(value) {
  const linked = (text) => String(text || "").split(/(\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g).map((part) => {
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    return link ? `<a href="${escapeHtml(link[2])}" target="_blank" rel="noopener noreferrer">${escapeHtml(link[1])}</a>` : escapeHtml(part).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  }).join("");
  return String(value || "").split(/\r?\n/).map((line) => {
    const clean = line.trim();
    if (!clean) return "";
    if (/^#{1,4}\s/.test(clean)) return `<h4>${linked(clean.replace(/^#{1,4}\s+/, ""))}</h4>`;
    if (/^[-*]\s/.test(clean)) return `<p class="ai-news-bullet">${linked(clean.replace(/^[-*]\s+/, ""))}</p>`;
    return `<p>${linked(clean)}</p>`;
  }).join("");
}

function renderAiNewsDashboard() {
  const completed = aiNewsBriefings.filter((task) => task.state === "completed");
  const withScript = completed.filter((task) => aiNewsSections(task.result?.summary).script);
  reportAiNewsCount.textContent = String(completed.length);
  reportAiNewsMetrics.innerHTML = [
    ["Briefing disponibili", completed.length],
    ["Script pronti", withScript.length],
    ["Ultimo aggiornamento", completed[0] ? formatReportDate(completed[0].updated_at) : "—"],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`).join("");
  reportAiNewsArchive.innerHTML = aiNewsBriefings.length ? aiNewsBriefings.map((task) => `
    <button type="button" class="ai-news-entry${task.id === selectedAiNewsId ? " ai-news-entry--active" : ""}" data-ai-news-id="${escapeHtml(task.id)}">
      <span>${escapeHtml(task.title.replace(/^AI morning briefing\s*[—-]\s*/, ""))}</span>
      <small>${escapeHtml(formatReportDate(task.updated_at))} · ${escapeHtml(task.state)}</small>
    </button>`).join("") : '<p class="report-status">Nessun briefing salvato.</p>';
  const selected = aiNewsBriefings.find((task) => task.id === selectedAiNewsId);
  if (!selected) {
    reportAiNewsDetail.innerHTML = '<p class="report-status">Seleziona un briefing.</p>';
    return;
  }
  if (selected.state !== "completed") {
    reportAiNewsDetail.innerHTML = `<h3>${escapeHtml(selected.title)}</h3><p class="report-status">Stato: ${escapeHtml(selected.state)}${selected.error ? ` · ${escapeHtml(selected.error)}` : ""}</p>`;
    return;
  }
  const { news, script } = aiNewsSections(selected.result?.summary);
  const links = [...new Set((String(selected.result?.summary || "").match(/https?:\/\/[^\s)]+/g) || []).map((url) => url.replace(/[.,;]+$/, "")))].slice(0, 12);
  reportAiNewsDetail.innerHTML = `
    <div class="report-card__heading"><div><span class="section-label">${escapeHtml(formatReportDate(selected.updated_at))}</span><h3>${escapeHtml(selected.title)}</h3></div></div>
    <section class="ai-news-script"><div class="report-card__heading"><div><span class="section-label">Pronto da registrare</span><h3>Script · circa 1 minuto</h3></div><button class="button" type="button" data-ai-news-copy ${script ? "" : "disabled"}>Copia script</button></div><p>${escapeHtml(script || "Script non presente in questo briefing.")}</p></section>
    <section class="ai-news-stories"><h3>Le notizie</h3>${aiNewsTextHtml(news)}</section>
    <section class="ai-news-sources"><h3>Fonti citate</h3>${links.length ? links.map((url) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>`).join("") : "<p>Nessuna fonte citata.</p>"}</section>`;
}

async function loadAiNewsDashboard() {
  if (!runtimeClient.connected) {
    reportAiNewsDetail.innerHTML = '<p class="report-status">Avvia il runtime per leggere i briefing.</p>';
    return;
  }
  reportAiNewsRefresh.disabled = true;
  reportAiNewsDetail.innerHTML = '<p class="report-status">Caricamento notizie…</p>';
  try {
    const tasks = await runtimeClient.listTasks();
    aiNewsBriefings = tasks.filter((task) => task.requested_agent_id === "ai-news-navigator" && /^AI morning briefing\s*[—-]/.test(task.title || ""))
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    if (!aiNewsBriefings.some((task) => task.id === selectedAiNewsId)) selectedAiNewsId = aiNewsBriefings[0]?.id || "";
    renderAiNewsDashboard();
  } catch (error) {
    reportAiNewsDetail.innerHTML = `<p class="report-status">Impossibile caricare le notizie: ${escapeHtml(error.message)}</p>`;
  } finally {
    reportAiNewsRefresh.disabled = false;
  }
}

function renderProjectOutputSummary(job) {
  if (!projectOutputSummary) {
    return;
  }
  if (!job) {
    projectOutputSummary.innerHTML = "";
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
  const active = ["queued", "running", "scheduled"].includes(job.state);
  const summaryText = parts.join(" · ");
  projectOutputSummary.innerHTML = `
    <div class="project-output-summary__row">
      <span>${escapeHtml(summaryText)}</span>
      ${active ? `<button class="button button--danger button--compact project-job-stop" type="button" data-project-output-stop="${job.id}">Stop</button>` : ""}
    </div>
  `;
  const stopButton = projectOutputSummary.querySelector("[data-project-output-stop]");
  if (stopButton) {
    stopButton.addEventListener("click", async () => {
      stopButton.disabled = true;
      await stopProjectJob(job.id, stopButton);
    });
  }
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
        <button type="button" class="button button--danger button--compact job-toast__stop" hidden>Stop</button>
        <button type="button" aria-label="Chiudi job">x</button>
      </div>
    </div>
    <p class="job-toast__summary"></p>
    <pre class="job-toast__output"></pre>
  `;
  const dismissButton = card.querySelector('[aria-label="Chiudi job"]');
  const stopButton = card.querySelector(".job-toast__stop");
  const summary = card.querySelector(".job-toast__summary");
  const output = card.querySelector(".job-toast__output");
  const title = card.querySelector(".job-toast__title strong");
  const subtitle = card.querySelector(".job-toast__title span");
  const status = card.querySelector(".job-toast__status");
  dismissButton.addEventListener("click", () => {
    card.remove();
    projectJobToasts.delete(job.id);
  });
  stopButton?.addEventListener("click", async () => {
    stopButton.disabled = true;
    await stopProjectJob(job.id, stopButton);
  });

  toast = { card, summary, output, title, subtitle, status, stopButton };
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
    ? "Job received and queued."
    : phase === "project.job.scheduled"
      ? "Job scheduled for the selected time."
    : phase === "project.job.started"
      ? "Job started."
      : phase === "project.job.alert"
        ? "Live job alert."
      : job.state === "scheduled"
        ? "Waiting for the selected time."
      : job.state === "completed"
        ? "Final output."
        : job.state === "failed"
          ? "Execution failed."
          : "Job updated.";

  toast.card.classList.toggle("job-toast--active", job.state === "queued" || job.state === "running" || job.state === "scheduled");
  toast.card.classList.toggle("job-toast--success", job.state === "completed");
  toast.card.classList.toggle("job-toast--danger", job.state === "failed");
  toast.title.textContent = titleText;
  toast.subtitle.textContent = subtitleText;
  toast.status.textContent = jobToastStatus(job);
  toast.status.dataset.tone = jobToastTone(job);
  toast.summary.textContent = summaryText;
  toast.output.textContent = formatProjectJobOutput(job);
  if (toast.stopButton) {
    const active = job.state === "queued" || job.state === "running" || job.state === "scheduled";
    toast.stopButton.hidden = !active;
    toast.stopButton.disabled = !active;
  }
}

function notifyAgentAboutProjectJobAlert(job, alert) {
  if (!job?.id || !alert) {
    return;
  }
  const title = String(alert.title ?? "Project alert");
  const summary = String(alert.summary ?? "A live project alert was emitted.");
  const currentUrl = String(alert.current_url ?? "").trim();
  const lines = [title, summary];
  if (currentUrl) {
    lines.push(currentUrl);
  }
  if (job.agent_id) {
    showAgentReply(job.agent_id, lines.join("\n"), false, [], `${job.id}-${alert.kind ?? "alert"}`);
  }
  showGameNotification({
    title: projectNameFor(job),
    subtitle: `${projectActionLabelFor(job)} · ${projectAgentLabelFor(job)}`,
    summary,
    tone: alert.kind === "vinted_login_required" || alert.kind === "vinted_marker_missing" ? "danger" : "active",
    key: `${job.id}-${alert.kind ?? "alert"}`,
  });
  if (projectDialog.open && projectPanel === "output") {
    projectResult.textContent = `${title}${currentUrl ? `\n${currentUrl}` : ""}`;
  }
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
  projectPanel = ["finished", "memory", "threads"].includes(panel) ? panel : "output";
  for (const tab of projectPanelTabs) {
    const active = tab.dataset.panelTab === projectPanel;
    tab.classList.toggle("project-panel-tab--active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const pane of projectPanels) {
    pane.hidden = pane.dataset.projectPanel !== projectPanel;
  }
  if (projectPanel === "finished") {
    void refreshProjectJobHistory(true);
  } else if (projectPanel === "memory") {
    void refreshWikiProposals();
    void refreshWikiPages();
  } else if (projectPanel === "threads") {
    void refreshTaskThreads();
  }
}

function renderJobNotificationBadge() {
  if (!jobNotificationCount) {
    return;
  }
  const previousCount = unreadCompletedProjectJobs;
  unreadCompletedProjectJobs = jobNotificationState.unreadIds.size;
  const hasUnread = unreadCompletedProjectJobs > 0;
  jobNotificationsButton?.setAttribute(
    "aria-label",
    hasUnread ? `Jobs and notifications, ${unreadCompletedProjectJobs} unread` : "Jobs and notifications"
  );
  if (hasUnread) {
    jobNotificationCount.hidden = false;
    jobNotificationCount.textContent = unreadCompletedProjectJobs > 99 ? "99+" : String(unreadCompletedProjectJobs);
    if (unreadCompletedProjectJobs > previousCount) {
      jobNotificationsButton?.classList.add("is-pulse");
      window.setTimeout(() => jobNotificationsButton?.classList.remove("is-pulse"), 900);
    }
    return;
  }
  jobNotificationCount.hidden = true;
  jobNotificationCount.textContent = "0";
}

function renderActiveWorkOverview(jobs = null) {
  if (!activeWorkList || !activeWorkCount) return;
  if (Array.isArray(jobs)) {
    activeProjectJobs.clear();
    for (const job of jobs) {
      if (["scheduled", "queued", "running"].includes(job.state)) {
        activeProjectJobs.set(job.id, job);
      }
    }
  }
  const active = [...activeProjectJobs.values()]
    .sort((left, right) => String(right.updated_at ?? right.created_at ?? "").localeCompare(String(left.updated_at ?? left.created_at ?? "")));
  activeWorkCount.textContent = String(active.length);
  activeWorkAllButton?.setAttribute("aria-label", `Open all jobs and notifications (${active.length} active)`);
  if (!active.length) {
    activeWorkList.innerHTML = '<p class="active-work__empty">Nessun job attivo. I nuovi lavori appariranno qui.</p>';
    return;
  }
  activeWorkList.innerHTML = active.slice(0, 4).map((job) => {
    const status = jobToastStatus(job);
    const detail = `${projectAgentLabelFor(job)} · ${status}`;
    return `
      <div class="active-work__job">
        <button class="active-work__open" type="button" data-active-work-job="${escapeHtml(job.id)}" aria-label="Apri ${escapeHtml(projectActionLabelFor(job))}, ${escapeHtml(status)}">
          <span class="active-work__job-top"><strong>${escapeHtml(projectActionLabelFor(job))}</strong><span>${escapeHtml(status)}</span></span>
          <small>${escapeHtml(projectNameFor(job))} · ${escapeHtml(detail)}</small>
          <span class="active-work__progress" role="progressbar" aria-label="Job in corso" aria-valuetext="${escapeHtml(status)}"><i></i></span>
        </button>
        <button class="button button--danger button--compact active-work__stop" type="button" data-active-work-stop="${escapeHtml(job.id)}" aria-label="Stop ${escapeHtml(projectActionLabelFor(job))}">Stop</button>
      </div>
    `;
  }).join("");
  if (active.length > 4) {
    activeWorkList.insertAdjacentHTML("beforeend", `<p class="active-work__more">+${active.length - 4} altri · apri Jobs per vedere tutto</p>`);
  }
}

function acknowledgeCompletedJobs(jobIds = []) {
  jobNotificationState.acknowledge(jobIds);
  renderJobNotificationBadge();
}

function markCompletedJobUnread(jobId) {
  jobNotificationState.markUnread(jobId);
  renderJobNotificationBadge();
}

function projectJobsForHistory(jobs) {
  const currentProjectId = projectSelect.value;
  return jobs
    .filter((job) => (
      projectDialogMode === "notifications"
        ? true
        : (job.state === "completed" || job.state === "failed")
    ))
    .filter((job) => {
      if (projectDialogMode !== "notifications") {
        return true;
      }
      if (projectJobFilter === "active") {
        return ["queued", "running", "scheduled"].includes(job.state);
      }
      if (projectJobFilter === "done") {
        return job.state === "completed";
      }
      if (projectJobFilter === "failed") {
        return job.state === "failed";
      }
      return true;
    })
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
    projectJobList.innerHTML = `<p class="project-job-empty">${
      projectDialogMode === "notifications"
        ? "No jobs match the current filter for this project."
        : "No completed jobs for this project."
    }</p>`;
    return;
  }
  projectJobList.innerHTML = jobs
    .map((job) => {
      const tone = job.state === "failed"
        ? "project-job-item--failed"
        : (job.state === "completed" ? "project-job-item--completed" : "");
      const summary = formatProjectJobSummary(job);
      const time = formatProjectJobTime(job);
      const stopButton = ["queued", "running", "scheduled"].includes(job.state)
        ? `<button class="button button--danger button--compact project-job-stop" type="button" data-job-stop="${job.id}">Stop</button>`
        : "";
      return `
        <div class="project-job-item ${tone}">
          <button class="project-job-item__open" type="button" data-job-id="${job.id}">
            <strong>${projectNameFor(job)} · ${projectActionLabelFor(job)}</strong>
            <small>${projectAgentLabelFor(job)} · ${jobToastStatus(job)}${time ? ` · ${time}` : ""}</small>
            <small>${summary || job.id}</small>
          </button>
          ${stopButton}
        </div>
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
  projectJobList.querySelectorAll("[data-job-stop]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const jobId = button.dataset.jobStop;
      if (!jobId) {
        return;
      }
      button.disabled = true;
      await stopProjectJob(jobId, button);
    });
  });
}

async function stopProjectJob(jobId, button = null) {
  if (!jobId) {
    return;
  }
  try {
    const job = await runtimeClient.cancelProjectJob(jobId);
    projectJobsCache.set(job.id, job);
    syncProjectJobToast(job, "project.job.failed");
    await refreshProjectJobHistory(false);
    if (projectPanel === "output") {
      renderProjectJobDetail(job);
    }
    setBootMessage(`Stopped job ${job.id}.`);
    return job;
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "cancelProjectJob", jobId });
    setBootMessage(error.message);
    if (button) {
      button.disabled = false;
    }
    return null;
  }
}

async function refreshProjectJobHistory(markSeen = false) {
  if (!runtimeClient.connected) {
    return;
  }
  try {
    const jobs = await runtimeClient.listProjectJobs();
    renderActiveWorkOverview(jobs);
    const filtered = projectJobsForHistory(jobs);
    renderProjectJobHistory(filtered);
    jobNotificationState.observe(jobs);
    renderJobNotificationBadge();
    if (markSeen) {
      acknowledgeCompletedJobs(filtered.filter((job) => job.state === "completed" || job.state === "failed").map((job) => job.id));
    }
  } catch (error) {
    runtimeClient.logClient("error", error.message, { operation: "refreshProjectJobHistory" });
  }
}

function wikiProposalMeta(content) {
  const text = String(content ?? "");
  const meta = {};
  if (text.startsWith("---\n")) {
    const closing = text.indexOf("\n---\n", 4);
    if (closing > 0) {
      for (const line of text.slice(4, closing).split("\n")) {
        const separator = line.indexOf(":");
        if (separator > 0) {
          meta[line.slice(0, separator).trim()] = line.slice(separator + 1).trim();
        }
      }
    }
  }
  const body = text.replace(/^---\n[\s\S]*?\n---\n/, "").trim();
  const heading = body.match(/^#\s+(.+)$/m)?.[1]?.trim();
  return {
    title: heading || "Wiki proposal",
    body,
    agent: meta.agent || "unknown",
    source: meta.source || "",
    targetPage: meta.target_page || "shared-knowledge",
    conflict: meta.conflict === "true",
    confidence: meta.confidence || "",
    created: meta.created || "",
  };
}

function renderWikiProposals(proposals) {
  if (!wikiProposalList || !wikiProposalCount) {
    return;
  }
  wikiProposalsCache.clear();
  for (const proposal of proposals) {
    wikiProposalsCache.set(proposal.name, proposal);
  }
  wikiProposalCount.textContent = proposals.length
    ? `${proposals.length} pending proposal${proposals.length === 1 ? "" : "s"}`
    : "No pending proposals";
  if (!proposals.length) {
    wikiProposalList.innerHTML = '<p class="project-job-empty">No wiki proposals are waiting for review.</p>';
    return;
  }
  wikiProposalList.innerHTML = proposals.map((proposal) => {
    const meta = wikiProposalMeta(proposal.content);
    const created = meta.created ? formatLocalDateTime(new Date(meta.created)) : "";
    const tone = meta.conflict ? " wiki-proposal-card--conflict" : "";
    const badge = [meta.conflict ? "Conflict" : "", meta.confidence, meta.targetPage].filter(Boolean).join(" · ");
    return `
      <article class="wiki-proposal-card${tone}" data-wiki-proposal="${escapeHtml(proposal.name)}" data-wiki-conflict="${String(meta.conflict)}">
        <div class="wiki-proposal-card__heading">
          <div>
            <strong>${escapeHtml(meta.title)}</strong>
            <small>${escapeHtml(meta.agent)}${meta.source ? ` · ${escapeHtml(meta.source)}` : ""}${created ? ` · ${escapeHtml(created)}` : ""}</small>
          </div>
          <span>${escapeHtml(badge)}</span>
        </div>
        <pre>${escapeHtml(clampText(meta.body, 2600))}</pre>
        <div class="wiki-proposal-card__actions">
          <button class="button" type="button" data-wiki-action="memory-review">Review with Memory Core</button>
          <button class="button" type="button" data-wiki-action="memory-improve">Improve via Memory Core</button>
          <button class="button button--primary" type="button" data-wiki-action="approved">Approve</button>
          <button class="button button--danger" type="button" data-wiki-action="rejected">Reject</button>
        </div>
      </article>
    `;
  }).join("");
}

async function refreshWikiProposals() {
  if (!runtimeClient.connected || !wikiProposalList) {
    return;
  }
  wikiProposalList.innerHTML = '<p class="project-job-empty">Loading wiki proposals...</p>';
  if (wikiProposalCount) {
    wikiProposalCount.textContent = "Loading...";
  }
  try {
    const proposals = await runtimeClient.listWikiProposals(80);
    renderWikiProposals(proposals);
  } catch (error) {
    if (wikiProposalCount) {
      wikiProposalCount.textContent = "Could not load proposals";
    }
    wikiProposalList.innerHTML = `<p class="project-job-empty">${escapeHtml(error.message)}</p>`;
    runtimeClient.logClient("error", error.message, { operation: "refreshWikiProposals" });
  }
}

function renderWikiPages(pages) {
  if (!wikiPageList) {
    return;
  }
  wikiPagesCache.clear();
  for (const page of pages) {
    wikiPagesCache.set(page.name, page);
  }
  if (!pages.length) {
    wikiPageList.innerHTML = '<p class="project-job-empty">No canonical wiki pages yet.</p>';
    return;
  }
  wikiPageList.innerHTML = pages.map((page) => `
    <button class="wiki-page-item" type="button" data-wiki-page="${escapeHtml(page.name)}">
      <strong>${escapeHtml(page.title || page.name)}</strong>
      <small>${escapeHtml(page.name)} · ${escapeHtml(page.kind)} · ${page.sections} sections · ${page.characters} chars</small>
    </button>
  `).join("");
}

async function refreshWikiPages() {
  if (!runtimeClient.connected || !wikiPageList) {
    return;
  }
  wikiPageList.innerHTML = '<p class="project-job-empty">Loading wiki pages...</p>';
  try {
    renderWikiPages(await runtimeClient.listWikiPages());
  } catch (error) {
    wikiPageList.innerHTML = `<p class="project-job-empty">${escapeHtml(error.message)}</p>`;
    runtimeClient.logClient("error", error.message, { operation: "refreshWikiPages" });
  }
}

async function openWikiPage(name) {
  if (!runtimeClient.connected || !wikiPageContent) {
    return;
  }
  wikiPageContent.textContent = "Loading wiki page...";
  try {
    const page = await runtimeClient.getWikiPage(name);
    wikiPageContent.textContent = page.content || "";
  } catch (error) {
    wikiPageContent.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "openWikiPage", name });
  }
}

async function searchWikiPages() {
  if (!runtimeClient.connected || !wikiPageContent) {
    return;
  }
  const query = wikiSearchQuery?.value.trim() ?? "";
  if (!query) {
    await refreshWikiPages();
    wikiPageContent.textContent = "Select a wiki page or run a search.";
    return;
  }
  wikiPageContent.textContent = "Searching wiki...";
  try {
    const result = await runtimeClient.searchWiki(query, 8);
    wikiPageContent.textContent = result.pages.length
      ? result.pages.map((page) => `## ${page.name}\n${page.content}`).join("\n\n")
      : "No matching wiki sections.";
  } catch (error) {
    wikiPageContent.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "searchWikiPages", query });
  }
}

async function runWikiMaintenanceFromUi(button) {
  if (!runtimeClient.connected) {
    return;
  }
  button.disabled = true;
  projectError.textContent = "";
  try {
    const result = await runtimeClient.runWikiMaintenance();
    await refreshWikiPages();
    setBootMessage(`Wiki maintenance updated ${result.pages_updated} page(s).`);
    if (wikiPageContent) {
      wikiPageContent.textContent = JSON.stringify(result, null, 2);
    }
  } catch (error) {
    projectError.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "runWikiMaintenance" });
  } finally {
    button.disabled = false;
  }
}

async function resolveWikiProposalFromButton(button) {
  const card = button.closest("[data-wiki-proposal]");
  const proposalName = card?.dataset.wikiProposal;
  const status = button.dataset.wikiAction;
  if (!proposalName) {
    return;
  }
  if (status === "memory-review" || status === "memory-improve") {
    const proposal = wikiProposalsCache.get(proposalName);
    const meta = wikiProposalMeta(proposal?.content ?? "");
    const request = status === "memory-review"
      ? `Review this wiki proposal in Memory Core and tell me whether it should be approved or rejected.\n\nProposal: ${proposalName}\nTitle: ${meta.title}\n\n${meta.body}`
      : `Improve this wiki proposal in Memory Core and suggest the exact canonical version that should be committed.\n\nProposal: ${proposalName}\nTitle: ${meta.title}\n\n${meta.body}`;
    button.disabled = true;
    projectError.textContent = "";
    try {
      const task = await askMemoryCore(request, {
        title: status === "memory-review" ? "Memory Core proposal review" : "Memory Core proposal improvement",
        priority: 2,
        openChat: true,
      });
      setBootMessage(`Sent to Memory Core: ${task?.id ?? proposalName}`);
    } catch (error) {
      projectError.textContent = error.message;
      runtimeClient.logClient("error", error.message, { operation: "memoryCoreProposalRequest", proposalName, status });
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (!["approved", "rejected"].includes(status)) {
    return;
  }
  const conflict = card?.dataset.wikiConflict === "true";
  let reason = status === "approved" ? "Approved from game UI." : "Rejected from game UI.";
  if (status === "approved" && conflict) {
    const note = window.prompt("This proposal conflicts with existing wiki knowledge. Type an approval reason that includes 'override conflict'.");
    if (!note) {
      return;
    }
    reason = note;
  } else if (status === "rejected") {
    const note = window.prompt("Optional rejection reason:", reason);
    if (note === null) {
      return;
    }
    reason = note.trim() || reason;
  }
  button.disabled = true;
  projectError.textContent = "";
  try {
    await runtimeClient.resolveWikiProposal(
      proposalName,
      status,
      "game-ui",
      reason,
    );
    await refreshWikiProposals();
    if (status === "approved") {
      await refreshWikiPages();
    }
    setBootMessage(status === "approved" ? "Wiki proposal approved." : "Wiki proposal rejected.");
  } catch (error) {
    projectError.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "resolveWikiProposal", proposalName, status });
  } finally {
    button.disabled = false;
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
  cancelPendingAgentQuickChat();
  const agent = network.getAgent(agentId);
  if (!agent) {
    return;
  }
  agentActionTitle.textContent = agent.label;
  agentActionRole.textContent = agent.role;
  agentActionStatus.textContent = agent.runtime.status;
  workOptions.hidden = true;
  const browsingAgent = isBrowsingAgent(agent);
  const runPodAgent = isRunPodAgent(agent);
  const creativeAgent = isCreativeComfyUiAgent(agent);
  const appiumAgent = isAppiumAgent(agent);
  setCreativeComfyUiView(creativeAgent);
  browserOptions.hidden = !browsingAgent;
  runPodOptions.hidden = !(runPodAgent || creativeAgent);
  appiumOptions.hidden = !appiumAgent;
  if (!agentActionDialog.open) {
    agentActionDialog.showModal();
  }
  if (browsingAgent) {
    void refreshBrowserSessions(selectedBrowserSessionId || "");
  }
  if (runPodAgent || creativeAgent) {
    void loadRunPodAgentConfiguration();
    startRunPodLiveStatusRefresh();
    startRunPodJobPolling();
  } else {
    stopRunPodLiveStatusRefresh();
  }
  if (appiumAgent) void loadAppiumAgentConfiguration();
  else stopAppiumScreenPolling("Apri l’agente Mobile Automation per vedere lo schermo del telefono.");
}

function isBrowsingAgent(agent) {
  if (!agent) {
    return false;
  }
  const toolsets = Array.isArray(agent.toolsets) ? agent.toolsets : [];
  const capabilities = Array.isArray(agent.capabilities) ? agent.capabilities : [];
  return agent.role === "browser" || toolsets.includes("browser") || capabilities.includes("browser");
}

function isRunPodAgent(agent) {
  return agent?.id === "runpod-manager" || agent?.role === "media-infrastructure";
}

function isCreativeComfyUiAgent(agent) {
  return agent?.id === "comfyui-creative-director" || agent?.role === "media-creative";
}

function isAppiumAgent(agent) {
  return agent?.id === "mobile-automation" || agent?.role === "mobile-automation";
}

function renderAppiumStatus(status) {
  const connected = Boolean(status?.server_connected);
  if (appiumServerState) appiumServerState.textContent = connected ? "Connected" : status?.enabled ? "Unavailable" : "Disabled";
  if (appiumServerDetail) appiumServerDetail.textContent = status?.server_error || `Appium ${status?.server_version || "2"} · ${status?.server_url || ""}`;
  if (appiumServerCard) appiumServerCard.classList.toggle("runpod-card--running", connected);
  if (appiumServerCard) appiumServerCard.classList.toggle("runpod-card--error", Boolean(status?.enabled && !connected));
  const count = Number(status?.device_count || 0);
  if (appiumDeviceCount) appiumDeviceCount.textContent = `${count} ready`;
  if (appiumAdbDetail) {
    const androidCount = Number(status?.android_device_count || 0);
    const iosCount = Number(status?.ios_device_count || 0);
    const androidStatus = status?.adb_error || `${androidCount} Android via ADB`;
    appiumAdbDetail.textContent = `${androidStatus} · ${iosCount} iPhone/iPad or simulator · ${status?.ios_discovery || "iOS discovery unavailable"}`;
  }
  if (appiumAdbCard) appiumAdbCard.classList.toggle("runpod-card--running", count > 0);
  if (appiumAdbCard) appiumAdbCard.classList.toggle("runpod-card--error", Boolean(status?.adb_error));
  if (appiumTargetDevice) {
    const previousDevice = appiumTargetDevice.value;
    appiumTargetDevice.replaceChildren();
    const prompt = document.createElement("option");
    prompt.value = "";
    prompt.textContent = "Seleziona un iPhone collegato";
    appiumTargetDevice.append(prompt);
    for (const device of Array.isArray(status?.devices) ? status.devices : []) {
      if (device.platform !== "iOS" || device.state !== "device") continue;
      const option = document.createElement("option");
      option.value = device.id;
      option.textContent = `${device.model || "iPhone/iPad"} · ${device.id}`;
      appiumTargetDevice.append(option);
    }
    appiumTargetDevice.value = previousDevice && Array.from(appiumTargetDevice.options).some((option) => option.value === previousDevice)
      ? previousDevice
      : (status?.devices || []).find((device) => device.platform === "iOS" && device.state === "device")?.id || "";
  }
  if (appiumSessionState) {
    appiumSessionState.textContent = status?.active_session
      ? `Sessione attiva · ${status.active_app_bundle_id || "app non specificata"}`
      : "Nessuna sessione di automazione aperta.";
  }
  if (appiumEndSessionButton) appiumEndSessionButton.disabled = !status?.active_session;
  if (status?.active_session) startAppiumScreenPolling();
  else stopAppiumScreenPolling("Apri un’app per vedere qui lo schermo del telefono.");
  if (!appiumDeviceList) return;
  appiumDeviceList.replaceChildren();
  const devices = Array.isArray(status?.devices) ? status.devices : [];
  if (!devices.length) {
    const empty = document.createElement("small");
    empty.textContent = status?.adb_available ? "No Android devices detected by ADB." : "Connect an Android device or configure ADB to see the inventory.";
    appiumDeviceList.append(empty);
    return;
  }
  for (const device of devices) {
    const row = document.createElement("div");
    row.className = "mobile-device";
    const label = document.createElement("strong");
    label.textContent = `${device.model || device.device || "Mobile device"}${device.platform ? ` · ${device.platform}` : ""}`;
    const id = document.createElement("small");
    id.textContent = device.id || "Unknown device ID";
    const state = document.createElement("span");
    state.className = `mobile-device__state ${device.state === "device" ? "mobile-device__state--ready" : "mobile-device__state--error"}`;
    state.textContent = device.state || "unknown";
    row.append(label, state, id);
    appiumDeviceList.append(row);
  }
}

async function refreshAppiumStatus() {
  if (appiumActionStatus) appiumActionStatus.textContent = "Checking Appium and querying ADB…";
  if (appiumRefreshButton) appiumRefreshButton.disabled = true;
  try {
    const status = await runtimeClient.getAppiumStatus();
    renderAppiumStatus(status);
    if (appiumActionStatus) appiumActionStatus.textContent = "Stato aggiornato. Scegli un iPhone per elencare e avviare un’app installata.";
    return status;
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "appium.refresh" });
    throw error;
  } finally {
    if (appiumRefreshButton) appiumRefreshButton.disabled = false;
  }
}

async function startAppiumServer() {
  if (appiumStartButton) appiumStartButton.disabled = true;
  if (appiumActionStatus) appiumActionStatus.textContent = "Starting the project-local Appium server…";
  try {
    const result = await runtimeClient.startAppium();
    if (appiumActionStatus) appiumActionStatus.textContent = result.already_running ? "Appium is already running; checking device inventory…" : `Appium starting (PID ${result.pid ?? "n/a"}); waiting for readiness…`;
    let status = result.status;
    const deadline = Date.now() + 25_000;
    while (!status?.server_connected && Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      status = await runtimeClient.getAppiumStatus();
    }
    renderAppiumStatus(status);
    if (appiumActionStatus) appiumActionStatus.textContent = status?.server_connected
      ? `Appium ${status.server_version || "2/3"} pronto · ${status.ios_device_count || 0} iPhone/iPad rilevati.`
      : `Appium non ha risposto entro 25 secondi. Controlla data/appium.log. ${status?.server_error || ""}`;
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "appium.start" });
  } finally {
    if (appiumStartButton) appiumStartButton.disabled = false;
  }
}

async function stopAppiumServer() {
  if (!window.confirm("Fermare il server Appium avviato da questa app?")) return;
  if (appiumStopButton) appiumStopButton.disabled = true;
  if (appiumActionStatus) appiumActionStatus.textContent = "Stopping Appium…";
  try {
    const result = await runtimeClient.stopAppium();
    renderAppiumStatus(result.status);
    if (appiumActionStatus) appiumActionStatus.textContent = result.stopped ? "Appium stopped." : "No Appium process started by this app was running.";
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "appium.stop" });
  } finally {
    if (appiumStopButton) appiumStopButton.disabled = false;
  }
}

async function loadAppiumAgentConfiguration() {
  try {
    const settings = await runtimeClient.getSystemSettings();
    const appium = settings.appium ?? {};
    if (appiumEnabledSelect) appiumEnabledSelect.value = String(Boolean(appium.enabled));
    if (appiumServerUrlInput) appiumServerUrlInput.value = appium.server_url || "http://127.0.0.1:4723";
    if (appiumAdbPathInput) appiumAdbPathInput.value = appium.adb_path || "adb";
    if (appiumIosToolInput) appiumIosToolInput.value = appium.ios_device_tool || "idevice_id";
    await refreshAppiumStatus();
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "appium.load-settings" });
  }
}

async function listAppiumInstalledApps() {
  const deviceId = appiumTargetDevice?.value || "";
  if (!deviceId) {
    if (appiumActionStatus) appiumActionStatus.textContent = "Collega e seleziona un iPhone prima di cercare le app.";
    return;
  }
  if (appiumListAppsButton) appiumListAppsButton.disabled = true;
  if (appiumActionStatus) appiumActionStatus.textContent = "Avvio XCUITest/WebDriverAgent e lettura delle app installate. Il primo avvio può richiedere un po’…";
  try {
    const result = await runtimeClient.listAppiumApps(deviceId);
    const apps = Array.isArray(result.apps) ? result.apps : [];
    appiumInstalledApps?.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = apps.length ? "Seleziona un’app" : "Nessuna app utente trovata";
    appiumInstalledApps?.append(placeholder);
    for (const app of apps) {
      const option = document.createElement("option");
      option.value = app.bundle_id;
      option.textContent = `${app.name}${app.version ? ` · ${app.version}` : ""} (${app.bundle_id})`;
      appiumInstalledApps?.append(option);
    }
    const vinted = apps.find((app) => /vinted/i.test(`${app.name} ${app.bundle_id}`));
    if (vinted && appiumInstalledApps) appiumInstalledApps.value = vinted.bundle_id;
    if (appiumActionStatus) appiumActionStatus.textContent = vinted
      ? `Trovata Vinted (${vinted.bundle_id}). Premi “Apri app selezionata” per avviarla.`
      : `${apps.length} app installate elencate. Scegli quella da aprire.`;
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = `Lettura app non riuscita: ${error.message}. Se è il primo uso, controlla firma WebDriverAgent/Xcode e “Modalità sviluppatore” sull’iPhone.`;
    runtimeClient.logClient("error", error.message, { operation: "appium.list-apps", deviceId });
  } finally {
    if (appiumListAppsButton) appiumListAppsButton.disabled = false;
  }
}

async function launchAppiumSelectedApp() {
  const deviceId = appiumTargetDevice?.value || "";
  const bundleId = appiumInstalledApps?.value || "";
  if (!deviceId || !bundleId) {
    if (appiumActionStatus) appiumActionStatus.textContent = "Seleziona prima un iPhone e un’app installata.";
    return;
  }
  if (appiumLaunchAppButton) appiumLaunchAppButton.disabled = true;
  if (appiumActionStatus) appiumActionStatus.textContent = `Apertura di ${bundleId}…`;
  try {
    const result = await runtimeClient.launchAppiumApp(deviceId, bundleId);
    if (appiumActionStatus) appiumActionStatus.textContent = `App avviata sul dispositivo. Sessione Appium ${result.session_id} mantenuta aperta.`;
    await refreshAppiumStatus();
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = `Apertura non riuscita: ${error.message}. Al primo avvio può essere necessario firmare WebDriverAgent con Xcode.`;
    runtimeClient.logClient("error", error.message, { operation: "appium.launch-app", deviceId, bundleId });
  } finally {
    if (appiumLaunchAppButton) appiumLaunchAppButton.disabled = false;
  }
}

async function endAppiumDeviceSession() {
  if (!window.confirm("Terminare la sessione di automazione Appium? L’app potrebbe restare aperta sul telefono.")) return;
  if (appiumEndSessionButton) appiumEndSessionButton.disabled = true;
  try {
    const result = await runtimeClient.endAppiumSession();
    if (appiumActionStatus) appiumActionStatus.textContent = result.closed ? "Sessione Appium terminata." : "Non c’era una sessione Appium attiva.";
    await refreshAppiumStatus();
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "appium.end-session" });
  } finally {
    if (appiumEndSessionButton) appiumEndSessionButton.disabled = false;
  }
}

function startAppiumScreenPolling() {
  if (appiumScreenTimer) return;
  if (appiumScreenState) appiumScreenState.textContent = "Anteprima quasi in tempo reale · aggiornamento ogni 1,5 secondi.";
  void updateAppiumScreenPreview();
  appiumScreenTimer = window.setInterval(() => { void updateAppiumScreenPreview(); }, 1500);
}

function stopAppiumScreenPolling(message = "Anteprima in pausa.") {
  if (appiumScreenTimer) window.clearInterval(appiumScreenTimer);
  appiumScreenTimer = null;
  if (appiumScreenState) appiumScreenState.textContent = message;
}

async function updateAppiumScreenPreview() {
  if (appiumScreenRequestPending || appiumOptions?.hidden || !agentActionDialog?.open) return;
  appiumScreenRequestPending = true;
  try {
    const blob = await runtimeClient.getAppiumScreenshot();
    if (!appiumScreenPreview) return;
    const nextUrl = URL.createObjectURL(blob);
    const oldUrl = appiumScreenObjectUrl;
    appiumScreenObjectUrl = nextUrl;
    appiumScreenPreview.src = nextUrl;
    appiumScreenPreview.hidden = false;
    if (appiumScreenPlaceholder) appiumScreenPlaceholder.hidden = true;
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    if (appiumScreenState) appiumScreenState.textContent = `Schermo aggiornato · ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    if (appiumScreenState) appiumScreenState.textContent = `Anteprima non disponibile: ${error.message}`;
  } finally {
    appiumScreenRequestPending = false;
  }
}

function setCreativeComfyUiView(enabled) {
  agentActionDialog?.classList.toggle("agent-dialog--creative-comfyui", Boolean(enabled));
  const heading = document.querySelector("#runpod-options-heading");
  if (heading) heading.textContent = enabled ? "ComfyUI Creative Director" : "RunPod Manager";
  const hideClosest = (selector, closest = "label, .runpod-dashboard, .runpod-batch-panel, .form-grid__wide") => {
    const element = document.querySelector(selector);
    const container = element?.closest(closest);
    if (container) container.hidden = Boolean(enabled);
  };
  // Infrastructure belongs to RunPod Manager. The Creative Director receives
  // only the creative queue, workflows, media and completed output.
  hideClosest("#runpod-dashboard");
  [
    "#runpod-network-volume-id", "#runpod-data-center-id", "#runpod-template-id", "#runpod-container-image",
    "#runpod-preferred-gpu", "#runpod-max-hourly-cost", "#runpod-volume-mount-path", "#runpod-comfyui-port",
    "#runpod-idle-action", "#runpod-pod-name", "#runpod-pod-id", "#runpod-pod-picker", "#runpod-workflow-json",
    "#runpod-workflow-file",
  ].forEach((selector) => hideClosest(selector));
  ["#runpod-save-deployment", "#runpod-load-workflow"].forEach((selector) => {
    const button = document.querySelector(selector);
    if (button?.parentElement) button.parentElement.hidden = Boolean(enabled);
  });
  const watcher = document.querySelector("#runpod-gpu-watch-status")?.closest(".runpod-batch-panel");
  if (watcher) watcher.hidden = Boolean(enabled);
  const controls = document.querySelector("#runpod-refresh-pods")?.closest(".form-grid__wide");
  if (controls) {
    const infrastructureControls = controls.querySelector(".dialog-actions");
    const status = controls.querySelector("#runpod-action-status");
    if (infrastructureControls) infrastructureControls.hidden = Boolean(enabled);
    if (status) status.hidden = Boolean(enabled);
  }
}

function setRunPodWorkflowPresetOptions(workflows) {
  if (!runPodWorkflowPresetSelect) return;
  const current = String(runPodWorkflowPresetSelect.value ?? "");
  runPodWorkflowPresetSelect.replaceChildren();
  const initial = document.createElement("option");
  initial.value = "";
  initial.textContent = "Choose a saved workflow";
  runPodWorkflowPresetSelect.append(initial);
  for (const workflow of Array.isArray(workflows) ? workflows : []) {
    const option = document.createElement("option");
    option.value = String(workflow?.id ?? "");
    option.disabled = !workflow?.available;
    option.dataset.inputKind = String(workflow?.input_kind ?? "");
    option.dataset.outputKind = String(workflow?.output_kind ?? "");
    option.dataset.minVram = String(workflow?.min_vram_gb ?? "");
    option.dataset.creativePresets = JSON.stringify(Array.isArray(workflow?.creative_presets) ? workflow.creative_presets : []);
    option.textContent = `${String(workflow?.name ?? workflow?.id ?? "Workflow")}${workflow?.available ? "" : " (file missing)"}`;
    option.title = String(workflow?.description ?? "");
    runPodWorkflowPresetSelect.append(option);
  }
  if (current && Array.from(runPodWorkflowPresetSelect.options).some((option) => option.value === current && !option.disabled)) {
    runPodWorkflowPresetSelect.value = current;
  }
}

async function loadRunPodAgentConfiguration() {
  try {
    const [settings, status, dataCenterResponse, volumeResponse, workflowResponse, promptPresetResponse] = await Promise.all([
      runtimeClient.getSystemSettings(),
      runtimeClient.getRunPodStatus(),
      runtimeClient.listRunPodDataCenters(),
      runtimeClient.listRunPodNetworkVolumes(),
      runtimeClient.listRunPodWorkflows(),
      runtimeClient.listComfyUiPromptPresets(),
    ]);
    const runpod = settings.runpod ?? {};
    setRunPodDataCenterOptions(dataCenterResponse?.datacenters, runpod.data_center_id ?? "");
    setRunPodVolumeOptions(volumeResponse?.network_volumes, runpod.network_volume_id ?? "");
    applySelectedVolumeDataCenter();
    if (runPodTemplateInput) runPodTemplateInput.value = runpod.template_id ?? "";
    if (runPodContainerImageInput) runPodContainerImageInput.value = runpod.container_image ?? "";
    if (runPodMaxHourlyCostInput) runPodMaxHourlyCostInput.value = runpod.max_hourly_cost ?? 0;
    if (runPodVolumeMountInput) runPodVolumeMountInput.value = runpod.volume_mount_path ?? "/workspace";
    if (runPodComfyUiPortInput) runPodComfyUiPortInput.value = runpod.comfyui_port ?? 8188;
    if (runPodIdleActionSelect) runPodIdleActionSelect.value = runpod.idle_action ?? "stop";
    setRunPodGpuOptions([], runpod.preferred_gpu ?? "", runPodGpuSelect);
    setRunPodPodOptions(status?.pods, selectedRunPodId());
    setRunPodWorkflowPresetOptions(workflowResponse?.workflows);
    if (creativePromptPreset) {
      creativePromptPresets = Array.isArray(promptPresetResponse?.presets) ? promptPresetResponse.presets : [];
      creativePromptPreset.replaceChildren();
      for (const preset of creativePromptPresets) {
        const option = document.createElement("option"); option.value = String(preset?.id ?? ""); option.textContent = String(preset?.name ?? preset?.id ?? "Preset"); option.dataset.prompt = String(preset?.prompt ?? ""); creativePromptPreset.append(option);
      }
      if (creativePromptPreset.options.length && creativePromptText && !creativePromptText.value.trim()) creativePromptText.value = creativePromptPreset.options[0].dataset.prompt || "";
    }
    const volume = (Array.isArray(volumeResponse?.network_volumes) ? volumeResponse.network_volumes : [])
      .find((item) => String(item?.id ?? "") === String(runpod.network_volume_id ?? ""));
    const volumeDataCenter = applySelectedVolumeDataCenter();
    let gpus = [];
    if (volumeDataCenter) {
      const gpuResponse = await runtimeClient.listRunPodGpus(volumeDataCenter);
      gpus = Array.isArray(gpuResponse?.gpus) ? gpuResponse.gpus : [];
      setRunPodGpuOptions(gpus, runpod.preferred_gpu ?? "", runPodGpuSelect);
    }
    // Opening the RunPod agent is itself a live availability check; no manual
    // button press is required to see whether the tracked GPUs appeared.
    let gpuWatch = null;
    if (volumeDataCenter) {
      try {
        gpuWatch = await runtimeClient.checkRunPodGpuWatch();
        renderRunPodGpuWatch(gpuWatch);
      } catch (error) {
        if (runPodGpuWatchStatus) runPodGpuWatchStatus.textContent = `Automatic GPU check failed: ${error.message}`;
      }
    }
    runPodDashboardSnapshot = { settings, volume, gpus, gpuWatch };
    renderRunPodDashboard({ settings, status, volume, gpus });
    renderRunPodActionResult("Ready", { message: "Volume, regional GPU availability and Pod state refreshed." });
  } catch (error) {
    renderRunPodActionResult("RunPod configuration failed", { error: error.message });
  }
}

async function refreshRunPodLiveStatus() {
  if (!agentActionDialog?.open || runPodOptions?.hidden) return;
  try {
    if (!runtimeClient.connected) await runtimeClient.connect();
    const status = await runtimeClient.getRunPodStatus();
    setRunPodPodOptions(status?.pods, selectedRunPodId());
    renderRunPodDashboard({ ...runPodDashboardSnapshot, status });
  } catch {
    if (runPodCardManagerDetail) runPodCardManagerDetail.textContent = "Runtime connection lost; retrying…";
    setRunPodCardState(runPodCardManager, "error");
  }
}

function startRunPodLiveStatusRefresh() {
  if (runPodStatusRefreshTimer) clearInterval(runPodStatusRefreshTimer);
  void refreshRunPodLiveStatus();
  runPodStatusRefreshTimer = window.setInterval(() => void refreshRunPodLiveStatus(), 10_000);
}

function stopRunPodLiveStatusRefresh() {
  if (runPodStatusRefreshTimer) clearInterval(runPodStatusRefreshTimer);
  runPodStatusRefreshTimer = null;
}

function browserSessionLabel(session) {
  const parts = [
    session.project_id || "main-scraper",
    session.backend,
    session.state,
    session.current_url || "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function currentBrowserSession() {
  return browserSessionSelect?.value || selectedBrowserSessionId || "";
}

function updateBrowserStatus(message) {
  if (browserStatus) {
    browserStatus.textContent = message;
  }
}

async function refreshBrowserSessions(preferredSessionId = "") {
  if (!browserOptions || browserOptions.hidden || !runtimeClient.connected) {
    return [];
  }
  try {
    const sessions = await runtimeClient.listBrowserSessions();
    const filtered = sessions.filter((session) => !session.project_id || session.project_id === "main-scraper");
    const previous = preferredSessionId || browserSessionSelect?.value || selectedBrowserSessionId;
    if (browserSessionSelect) {
      browserSessionSelect.innerHTML = filtered
        .map((session) => `<option value="${escapeHtml(session.id)}">${escapeHtml(browserSessionLabel(session))}</option>`)
        .join("");
      browserSessionSelect.value = filtered.some((session) => session.id === previous)
        ? previous
        : filtered[0]?.id ?? "";
    }
    selectedBrowserSessionId = browserSessionSelect?.value ?? "";
    updateBrowserStatus(
      filtered.length
        ? `Sessioni browser: ${filtered.length}`
        : "Nessuna sessione browser attiva. Aprine una dal popup."
    );
    return filtered;
  } catch (error) {
    updateBrowserStatus(error.message);
    return [];
  }
}

async function openBrowserSessionFromPopup() {
  if (!runtimeClient.connected) {
    updateBrowserStatus("Runtime offline: impossibile aprire la sessione browser.");
    return;
  }
  try {
    const result = await runtimeClient.createBrowserSession({
      project_id: "main-scraper",
      backend: browserBackendSelect?.value ?? "botasaurus",
      url: browserUrlInput?.value.trim() ?? "",
      browser_mode: browserModeSelect?.value
        ?? readProjectParameterValue("browser-mode", "sessione_persistente"),
      browser_user_data_dir: readProjectParameterValue("browser-user-data-dir", ""),
      browser_profile_directory: readProjectParameterValue("browser-profile-directory", "Default"),
      refresh_browser_profile: false,
      page_text: "",
      title: "",
    });
    selectedBrowserSessionId = result.id;
    await refreshBrowserSessions(result.id);
    updateBrowserStatus(`Sessione aperta: ${result.id}`);
  } catch (error) {
    updateBrowserStatus(error.message);
  }
}

async function runBrowserPopupCommand(command, parameters = {}) {
  const sessionId = currentBrowserSession();
  if (!sessionId) {
    updateBrowserStatus("Seleziona prima una sessione browser.");
    return null;
  }
  try {
    const result = await runtimeClient.runBrowserCommand(sessionId, command, parameters);
    selectedBrowserSessionId = sessionId;
    await refreshBrowserSessions(sessionId);
    return result;
  } catch (error) {
    updateBrowserStatus(error.message);
    return null;
  }
}

function setRuntimeConnection(connected) {
  runtimeStatus.textContent = connected ? "Runtime live" : "Offline demo";
  runtimeStatus.classList.toggle("live-status--connecting", false);
  runtimeStatus.classList.toggle("live-status--offline", !connected);
}

function visibleDialogIds() {
  return Array.from(document.querySelectorAll("dialog[open]"))
    .map((dialog) => dialog.id)
    .filter(Boolean);
}

function captureGameScreenshotDataUrl() {
  try {
    if (!canvas || typeof canvas.toDataURL !== "function") {
      return "";
    }
    return canvas.toDataURL("image/png");
  } catch (_error) {
    return "";
  }
}

let reportingUiError = false;

function reportUiError(source, errorOrMessage, context = {}) {
  if (reportingUiError) {
    return;
  }
  reportingUiError = true;
  const message = typeof errorOrMessage === "string"
    ? errorOrMessage
    : (errorOrMessage?.message || String(errorOrMessage || "Unknown browser error"));
  const payload = {
    source,
    message,
    context: {
      ...context,
      selected_agent_id: selectedAgentId || "",
      selected_station_id: selectedStationId || "",
      selected_room_id: selectedRoomId || "",
      active_dialogs: visibleDialogIds(),
      project_dialog_open: Boolean(projectDialog?.open),
      project_dialog_mode: projectDialogMode,
      project_panel: projectPanel,
      runtime_connected: Boolean(runtimeClient.connected),
    },
    screenshot_data_url: captureGameScreenshotDataUrl(),
  };
  Promise.resolve(runtimeClient.reportError(payload))
    .catch(() => undefined)
    .finally(() => {
      reportingUiError = false;
    });
}

async function connectRuntime() {
  runtimeClient.onEvent(handleRuntimeEvent);
  try {
    await runtimeClient.connect();
    network.autopilotClock = Number.POSITIVE_INFINITY;
    setRuntimeConnection(true);
    try {
      const settings = await runtimeClient.getSystemSettings();
      applySystemSettingsToUi(settings);
    } catch (_error) {
      // best effort
    }
    await refreshProjectJobToasts();
    await refreshProjectJobHistory(false);
    await ensureAutoMonitoringJobs();
    if (!monitoringDashboardRefreshTimer) {
      monitoringDashboardRefreshTimer = window.setInterval(() => {
        if (runtimeClient.connected) void refreshMonitoringDashboard();
      }, 15000);
    }
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

function systemSettingsField(name) {
  return systemSettingsForm.elements.namedItem(name);
}

function modelPickerField() {
  return settingsField("model_picker");
}

function modelInputField() {
  return settingsField("model");
}

function systemModelPickerField() {
  return systemSettingsField("model_picker");
}

function systemModelInputField() {
  return systemSettingsField("model");
}

function setRunPodGpuOptions(gpus, selectedGpu = "", picker = runPodGpuSelect) {
  if (!picker) return;
  const selected = String(selectedGpu ?? "").trim();
  const list = Array.isArray(gpus) ? gpus : [];
  const known = new Set(list.map((gpu) => String(gpu?.id ?? "")));
  const options = ["<option value=\"\">Choose a GPU</option>"];
  if (selected && !known.has(selected)) {
    options.push(`<option value="${escapeHtml(selected)}">${escapeHtml(selected)} (saved selection)</option>`);
  }
  for (const gpu of list) {
    const id = String(gpu?.id ?? "").trim();
    if (!id) continue;
    const name = String(gpu?.name ?? id);
    const memory = Number(gpu?.memory_gb ?? 0);
    const secure = Number(gpu?.secure_price ?? 0);
    const community = Number(gpu?.community_price ?? 0);
    const stock = String(gpu?.stock_status ?? "").trim();
    const price = [secure > 0 ? `secure $${secure}/h` : "", community > 0 ? `community $${community}/h` : ""].filter(Boolean).join(" · ");
    const label = `${name} · ${memory} GB${stock ? ` · ${stock} stock` : ""}${price ? ` · ${price}` : ""}`;
    options.push(`<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`);
  }
  picker.innerHTML = options.join("");
  picker.value = selected;
}

function setRunPodPodOptions(pods, selectedPodId = "") {
  if (!runPodPicker) return;
  const list = Array.isArray(pods) ? pods : [];
  const runningPod = list.find((pod) => String(pod?.status ?? "").toUpperCase() === "RUNNING");
  const selected = String(selectedPodId ?? "").trim() || String(runningPod?.id ?? "").trim();
  const options = ["<option value=\"\">Choose an existing Pod</option>"];
  for (const pod of list) {
    const id = String(pod?.id ?? "").trim();
    if (!id) continue;
    const label = [pod?.name || id, pod?.status || "unknown", id].filter(Boolean).join(" · ");
    options.push(`<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`);
  }
  runPodPicker.innerHTML = options.join("");
  runPodPicker.value = selected;
  if (selected && runPodIdInput) runPodIdInput.value = selected;
}

function setRunPodDataCenterOptions(datacenters, selectedDataCenter = "") {
  if (!runPodDataCenterInput) return;
  const selected = String(selectedDataCenter ?? "").trim();
  const list = Array.isArray(datacenters) ? datacenters : [];
  const known = new Set(list.map((dataCenter) => String(dataCenter?.id ?? "")));
  const options = ["<option value=\"\">Choose a data center</option>"];
  if (selected && !known.has(selected)) {
    options.push(`<option value="${escapeHtml(selected)}">${escapeHtml(selected)} (saved, unavailable)</option>`);
  }
  for (const dataCenter of list) {
    const id = String(dataCenter?.id ?? "").trim();
    if (!id) continue;
    const name = String(dataCenter?.name ?? id);
    const location = String(dataCenter?.location ?? "").trim();
    const count = Array.isArray(dataCenter?.gpuAvailability) ? dataCenter.gpuAvailability.length : 0;
    options.push(`<option value="${escapeHtml(id)}">${escapeHtml(`${name}${location ? ` · ${location}` : ""} · ${count} GPU types`)}</option>`);
  }
  runPodDataCenterInput.innerHTML = options.join("");
  runPodDataCenterInput.value = selected;
}

function setRunPodVolumeOptions(volumes, selectedVolumeId = "") {
  if (!runPodNetworkVolumeInput) return;
  const selected = String(selectedVolumeId ?? "").trim();
  const list = Array.isArray(volumes) ? volumes : [];
  const known = new Set(list.map((volume) => String(volume?.id ?? "")));
  runPodVolumeDataCenters.clear();
  const options = ["<option value=\"\">Choose a Network Volume</option>"];
  if (selected && !known.has(selected)) {
    options.push(`<option value="${escapeHtml(selected)}">${escapeHtml(selected)} (saved, unavailable)</option>`);
  }
  for (const volume of list) {
    const id = String(volume?.id ?? "").trim();
    if (!id) continue;
    const dataCenter = String(volume?.dataCenter ?? "").trim();
    if (dataCenter) runPodVolumeDataCenters.set(id, dataCenter);
    const label = [volume?.name || id, dataCenter || "unknown region", volume?.type || "Network Volume"].filter(Boolean).join(" · ");
    options.push(`<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`);
  }
  runPodNetworkVolumeInput.innerHTML = options.join("");
  runPodNetworkVolumeInput.value = selected;
}

function applySelectedVolumeDataCenter() {
  const volumeId = String(runPodNetworkVolumeInput?.value ?? "").trim();
  const dataCenter = runPodVolumeDataCenters.get(volumeId);
  if (dataCenter && runPodDataCenterInput) {
    if (!Array.from(runPodDataCenterInput.options).some((option) => option.value === dataCenter)) {
      const option = document.createElement("option");
      option.value = dataCenter;
      option.textContent = `${dataCenter} · Network Volume region`;
      runPodDataCenterInput.append(option);
    }
    runPodDataCenterInput.value = dataCenter;
  }
  return dataCenter || "";
}

function setRunPodCardState(element, state) {
  const card = element?.closest(".runpod-card");
  if (!card) return;
  card.classList.remove("runpod-card--running", "runpod-card--stopped", "runpod-card--error");
  if (state) card.classList.add(`runpod-card--${state}`);
}

function renderRunPodDashboard({ settings, status, volume, gpus }) {
  const runpod = settings?.runpod ?? {};
  const pods = Array.isArray(status?.pods) ? status.pods : [];
  const running = pods.filter((pod) => String(pod?.status ?? "").toUpperCase() === "RUNNING");
  const selectedGpu = String(runpod.preferred_gpu ?? runPodGpuSelect?.value ?? "");
  if (runPodCardManager) runPodCardManager.textContent = status?.configured ? "Configured" : "Needs configuration";
  if (runPodCardManagerDetail) runPodCardManagerDetail.textContent = status?.error || "API key and deployment settings are ready.";
  setRunPodCardState(runPodCardManager, status?.configured && !status?.error ? "running" : "error");
  if (runPodCardVolume) runPodCardVolume.textContent = volume?.name || runpod.network_volume_id || "No volume selected";
  if (runPodCardVolumeDetail) runPodCardVolumeDetail.textContent = volume?.dataCenter ? `Region ${volume.dataCenter}` : "Choose a Network Volume.";
  setRunPodCardState(runPodCardVolume, volume?.dataCenter ? "running" : "error");
  if (runPodCardGpus) runPodCardGpus.textContent = `${Array.isArray(gpus) ? gpus.length : 0} available`;
  if (runPodCardGpusDetail) runPodCardGpusDetail.textContent = selectedGpu ? `Selected: ${selectedGpu}` : "Open the picker to refresh availability.";
  setRunPodCardState(runPodCardGpus, Array.isArray(gpus) && gpus.length ? "running" : "stopped");
  if (runPodCardPods) runPodCardPods.textContent = running.length ? `${running.length} running` : pods.length ? `${pods.length} stopped` : "No Pods";
  if (runPodCardPodsDetail) runPodCardPodsDetail.textContent = pods.length ? pods.map((pod) => `${pod.name || pod.id}: ${pod.status || "unknown"}`).join(" · ") : "Create a Pod when ready.";
  setRunPodCardState(runPodCardPods, running.length ? "running" : pods.length ? "stopped" : "");
}

function renderSecretStatus(status) {
  projectKeyStatus.textContent = `Progetto: ${status.project_configured ? "configurata" : "non configurata"}`;
  agentKeyStatus.textContent = `Agente: ${status.agent_configured ? "configurata" : "non configurata"}`;
  projectKeyStatus.classList.toggle("secret-status--configured", status.project_configured);
  agentKeyStatus.classList.toggle("secret-status--configured", status.agent_configured);
}

function renderSystemSecretStatus(status) {
  if (!systemProjectKeyStatus || !systemDiscordBotStatus || !systemAccordiAdminStatus || !systemRunPodStatus) {
    return;
  }
  systemProjectKeyStatus.textContent = `Project: ${status.project_configured ? "configured" : "not configured"}`;
  systemDiscordBotStatus.textContent = `Discord bot token: ${status.discord_bot_configured ? "configured" : "not configured"}`;
  systemAccordiAdminStatus.textContent = `Accordi admin token: ${status.accordi_admin_configured ? "configured" : "not configured"}`;
  systemRunPodStatus.textContent = `RunPod API key: ${status.runpod_configured ? "configured" : "not configured"}`;
  systemProjectKeyStatus.classList.toggle("secret-status--configured", status.project_configured);
  systemDiscordBotStatus.classList.toggle("secret-status--configured", status.discord_bot_configured);
  systemAccordiAdminStatus.classList.toggle("secret-status--configured", status.accordi_admin_configured);
  systemRunPodStatus.classList.toggle("secret-status--configured", status.runpod_configured);
}

function splitNumericIds(value) {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number(item))
    .filter((item) => Number.isInteger(item) && item > 0);
}

async function saveSelectedApiKey(snapshot) {
  if (!snapshot) {
    throw new Error("Selected agent is not available.");
  }
  const apiKey = String(settingsField("api_key").value ?? "").trim();
  if (!apiKey) {
    throw new Error("Enter an API key first.");
  }
  const scope = String(settingsField("api_key_scope").value ?? "project").trim();
  const status = scope === "agent"
    ? await runtimeClient.setAgentSecret(snapshot.id, apiKey)
    : await runtimeClient.setProjectSecret(apiKey);
  settingsField("api_key").value = "";
  renderSecretStatus(status);
  return status;
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

function renderSystemModelPicker(provider, selectedModel = "") {
  const picker = systemModelPickerField();
  const modelInput = systemModelInputField();
  const help = document.querySelector("#system-model-help");
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

function syncSystemModelFieldFromPicker() {
  const picker = systemModelPickerField();
  const modelInput = systemModelInputField();
  if (picker.hidden) {
    return;
  }
  if (picker.value === MODEL_PICKER_CUSTOM) {
    modelInput.hidden = false;
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

function updateSystemProviderControls(resetDefaults = false) {
  const provider = systemSettingsField("provider").value;
  const defaults = providerDefaults[provider];
  const currentModel = systemModelInputField().value;
  if (resetDefaults && defaults) {
    systemModelInputField().value = defaults.model;
    systemSettingsField("base_url").value = defaults.baseUrl;
  }
  renderSystemModelPicker(provider, resetDefaults && defaults ? defaults.model : currentModel);
  syncSystemModelFieldFromPicker();
}

async function openSystemSettings() {
  if (!runtimeClient.connected) {
    setBootMessage("Start the project runtime first to edit global settings.");
    return;
  }
  systemSettingsError.textContent = "";
  systemSettingsDialog.showModal();
  try {
    const [settings, status, runpodStatus] = await Promise.all([
      runtimeClient.getSystemSettings(),
      runtimeClient.getSecretStatus(""),
      runtimeClient.getRunPodStatus(),
    ]);
    systemSettingsField("provider").value = settings.model.provider;
    systemSettingsField("model").value = settings.model.model;
    systemSettingsField("base_url").value = settings.model.base_url;
    systemSettingsField("api_key_env").value = settings.model.api_key_env;
    systemSettingsField("api_key_scope").value = settings.model.api_key_scope ?? "project";
    systemSettingsField("temperature").value = settings.model.temperature;
    systemSettingsField("project_api_key").value = "";
    systemSettingsField("theme").value = settings.ui.theme;
    systemSettingsField("auto_agents").value = String(settings.ui.auto_agents);
    systemSettingsField("simulation_speed").value = String(settings.ui.simulation_speed);
    systemSettingsField("discord_enabled").value = String(Boolean(settings.discord?.enabled));
    systemSettingsField("discord_message_content").value = String(Boolean(settings.discord?.message_content));
    systemSettingsField("discord_sync_commands").value = String(settings.discord?.sync_commands !== false);
    systemSettingsField("discord_command_prefix").value = settings.discord?.command_prefix ?? "!";
    systemSettingsField("discord_default_agent_id").value = settings.discord?.default_agent_id ?? "";
    systemSettingsField("discord_allowed_guild_ids").value = (settings.discord?.allowed_guild_ids ?? []).join(", ");
    systemSettingsField("discord_allowed_channel_ids").value = (settings.discord?.allowed_channel_ids ?? []).join(", ");
    systemSettingsField("discord_bot_token").value = "";
    systemSettingsField("accordi_admin_token").value = "";
    systemSettingsField("runpod_enabled").value = String(Boolean(settings.runpod?.enabled));
    systemSettingsField("runpod_api_key").value = "";
    systemSettingsField("runpod_network_volume_id").value = settings.runpod?.network_volume_id ?? "";
    systemSettingsField("runpod_data_center_id").value = settings.runpod?.data_center_id ?? "";
    systemSettingsField("runpod_template_id").value = settings.runpod?.template_id ?? "";
    systemSettingsField("runpod_container_image").value = settings.runpod?.container_image ?? "";
    setRunPodGpuOptions([], settings.runpod?.preferred_gpu ?? "", systemSettingsField("runpod_preferred_gpu"));
    systemSettingsField("runpod_max_hourly_cost").value = settings.runpod?.max_hourly_cost ?? 0;
    systemSettingsField("runpod_volume_mount_path").value = settings.runpod?.volume_mount_path ?? "/workspace";
    systemSettingsField("runpod_comfyui_port").value = settings.runpod?.comfyui_port ?? 8188;
    systemSettingsField("runpod_idle_action").value = settings.runpod?.idle_action ?? "stop";
    systemSettingsField("discord_error_notifications").value = String(Boolean(settings.diagnostics?.discord_error_notifications));
    systemSettingsField("discord_webhook_url").value = settings.diagnostics?.discord_webhook_url ?? "";
    updateSystemProviderControls(false);
    renderSystemSecretStatus(status);
    if (systemRunPodStatus && settings.runpod?.enabled) {
      const podCount = Array.isArray(runpodStatus?.pods) ? runpodStatus.pods.length : 0;
      systemRunPodStatus.textContent = runpodStatus?.error
        ? `RunPod: ${runpodStatus.error}`
        : `RunPod: ready · ${podCount} Pod${podCount === 1 ? "" : "s"} visible`;
    }
  } catch (error) {
    systemSettingsError.textContent = error.message;
  }
}

function applySystemSettingsToUi(settings) {
  if (!settings?.ui) {
    return;
  }
  applyTheme(settings.ui.theme, { persist: true });
  setAutoAgents(Boolean(settings.ui.auto_agents));
  setSpeed(Number(settings.ui.simulation_speed) || 1);
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
        const placingPendingStation = pendingStationPlacementId === selectedStationId;
        const beforeLayout = currentLayoutState();
        const moved = agentWorld.commandMoveStation(selectedStationId, tile);
        if (moved) {
          moveStationVisual(selectedStationId);
          if (placingPendingStation) {
            pendingStationPlacementId = null;
            assignLinkedAgentToStation(selectedStationId);
          }
          saveLayoutState(beforeLayout);
          setBootMessage(
            placingPendingStation
              ? `${agentWorld.getStation(selectedStationId)?.label ?? "Workstation"} piazzata e collegata.`
              : `${agentWorld.getStation(selectedStationId)?.label ?? "Tavolo"} spostato.`
          );
        } else {
          setBootMessage("Quel tile non e disponibile per il tavolo selezionato.");
        }
      } else if (selectedAgentId) {
        const beforeLayout = currentLayoutState();
        const moved = agentWorld.commandPlaceAgent(selectedAgentId, tile, "layout move");
        if (moved) {
          saveLayoutState(beforeLayout);
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
    if (pendingAgentQuickChat?.agentId === agentId) {
      cancelPendingAgentQuickChat();
      closeQuickChat();
      openAgentActions(agentId);
    } else {
      cancelPendingAgentQuickChat();
      scheduleAgentQuickChat(agentId);
    }
  } else if (stationId) {
    selectedStationId = stationId;
    selectedRoomId = roomForTile(worldToTile(agentWorld.getStation(stationId)?.position ?? { x: 0, z: 0 }))?.id ?? selectedRoomId;
    closeQuickChat();
  } else if (tile) {
    selectedStationId = null;
    selectedRoomId = roomForTile(tile)?.id ?? selectedRoomId;
    closeQuickChat();
    const beforeLayout = currentLayoutState();
    const moved = agentWorld.commandMoveAgent(selectedAgentId, tile, "manual move");
    if (moved) {
      saveLayoutState(beforeLayout);
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
  pointerState.layoutStroke = beginLayoutStroke(event);
});

canvas.addEventListener("pointermove", (event) => {
  if (!pointerState.dragging) {
    return;
  }
  const dx = event.clientX - pointerState.x;
  const dy = event.clientY - pointerState.y;
  const total = Math.hypot(event.clientX - pointerState.startX, event.clientY - pointerState.startY);
  if (pointerState.layoutStroke) {
    const hit = objectFromPointer(event);
    if (hit?.object?.userData?.tile) applyLayoutStrokeTile(hit.object.userData.tile);
    pointerState.x = event.clientX;
    pointerState.y = event.clientY;
    return;
  }
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
  if (pointerState.layoutStroke) {
    finishLayoutStroke();
  } else if (!pointerState.panning) {
    selectFromPointer(event);
  }
  pointerState.layoutStroke = false;
  pointerState.dragging = false;
  pointerState.panning = false;
});

canvas.addEventListener("pointercancel", () => {
  finishLayoutStroke();
  pointerState.layoutStroke = false;
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
  const undoShortcut = (event.metaKey || event.ctrlKey) && event.code === "KeyZ" && !event.shiftKey;
  const redoShortcut = (event.metaKey && event.shiftKey && event.code === "KeyZ")
    || (event.ctrlKey && event.code === "KeyY");
  if (layoutMode && !editing && undoShortcut) {
    event.preventDefault();
    undoLayoutEdit();
    return;
  }
  if (layoutMode && !editing && redoShortcut) {
    event.preventDefault();
    redoLayoutEdit();
    return;
  }
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
undoLayoutButton?.addEventListener("click", undoLayoutEdit);
redoLayoutButton?.addEventListener("click", redoLayoutEdit);
roomDrawToggle?.addEventListener("click", () => setRoomDrawMode(!roomDrawMode));
doorToggle?.addEventListener("click", () => setDoorMode(!doorMode));
rotateStationButton?.addEventListener("click", rotateSelectedStation);
addRoomButton?.addEventListener("click", addLayoutRoom);
deleteRoomButton?.addEventListener("click", deleteSelectedRoom);
addWorkstationButton?.addEventListener("click", addEditorWorkstation);
workstationAgentSelect?.addEventListener("change", renderWorkstationControls);
resetLayoutButton?.addEventListener("click", resetSavedLayout);
themeToggle?.addEventListener("click", () => applyTheme(currentTheme === "light" ? "dark" : "light"));
atmosphereToggle?.addEventListener("click", cycleAtmosphere);
reportsDashboardButton?.addEventListener("click", () => {
  void openVintedReports();
});
monitoringDashboardButton?.addEventListener("click", () => {
  void openMonitoringDashboard();
});
reportRefreshButton?.addEventListener("click", () => {
  void loadVintedReport();
});
reportAiNewsRefresh?.addEventListener("click", () => { void loadAiNewsDashboard(); });
reportLinkedInRefresh?.addEventListener("click", () => { void loadLinkedInPosts(); });
reportLinkedInSearch?.addEventListener("input", () => {
  window.clearTimeout(linkedinSearchTimer);
  linkedinSearchTimer = window.setTimeout(() => { void loadLinkedInPosts(); }, 300);
});
reportLinkedInFilter?.addEventListener("change", renderLinkedInPosts);
reportLinkedInList?.addEventListener("click", (event) => {
  const row = event.target.closest("[data-linkedin-post-id]");
  if (row) void loadLinkedInDetail(row.dataset.linkedinPostId || "");
});
reportLinkedInDetail?.addEventListener("click", async (event) => {
  const sendToPublisher = event.target.closest("[data-linkedin-send-to-publisher]");
  if (sendToPublisher) {
    const body = sendToPublisher.closest(".linkedin-draft")?.querySelector("textarea")?.value || "";
    sendToPublisher.disabled = true;
    try {
      await runtimeClient.createLinkedInDraft(body, selectedLinkedInPostId);
      await loadLinkedInPublisher();
      linkedinPublisherStatus.textContent = "Bozza pronta nel Publisher: rivedila prima di pubblicarla.";
      document.querySelector(".linkedin-publisher")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      const status = reportLinkedInDetail.querySelector("#linkedin-detail-status");
      if (status) status.textContent = `Bozza non salvata: ${error.message}`;
    } finally { sendToPublisher.disabled = false; }
    return;
  }
  const copy = event.target.closest("[data-linkedin-copy]");
  if (copy) {
    const draft = copy.closest(".linkedin-draft")?.querySelector("textarea")?.value || "";
    try { await navigator.clipboard.writeText(draft); copy.textContent = "Copiato"; }
    catch (_error) { copy.textContent = "Copia non riuscita"; }
    return;
  }
  const archive = event.target.closest("[data-linkedin-archive], [data-linkedin-poster]");
  if (archive) {
    const poster = archive.hasAttribute("data-linkedin-poster");
    const index = Number(archive.dataset.linkedinArchive ?? archive.dataset.linkedinPoster);
    const status = reportLinkedInDetail.querySelector("#linkedin-detail-status");
    archive.disabled = true;
    if (status) status.textContent = "Salvataggio media in corso…";
    try {
      await runtimeClient.archiveLinkedInMedia(selectedLinkedInPostId, index, poster);
      await loadLinkedInDetail(selectedLinkedInPostId);
      const updated = reportLinkedInDetail.querySelector("#linkedin-detail-status");
      if (updated) updated.textContent = "Media salvato nel PC. Usa “Scarica file” per aprirlo o esportarlo.";
    } catch (error) {
      if (status) status.textContent = `Download non riuscito: ${error.message}`;
      archive.disabled = false;
    }
    return;
  }
  const rewrite = event.target.closest("[data-linkedin-rewrite]");
  if (rewrite) {
    const prompt = reportLinkedInDetail.querySelector("#linkedin-rewrite-prompt")?.value || "";
    linkedinRewritePromptsByPost.set(selectedLinkedInPostId, prompt);
    const status = reportLinkedInDetail.querySelector("#linkedin-detail-status");
    rewrite.disabled = true;
    if (status) status.textContent = "Generazione bozza in corso…";
    try {
      await runtimeClient.rewriteLinkedInPost(selectedLinkedInPostId, prompt);
      await loadLinkedInDetail(selectedLinkedInPostId);
    } catch (error) {
      if (status) status.textContent = `Riscrittura non riuscita: ${error.message}`;
      rewrite.disabled = false;
    }
  }
});
reportLinkedInDetail?.addEventListener("input", (event) => {
  if (!event.target.matches("#linkedin-rewrite-prompt")) return;
  linkedinRewritePromptsByPost.set(selectedLinkedInPostId, event.target.value);
});
linkedinPublisherRefresh?.addEventListener("click", () => { void loadLinkedInPublisher(); });
linkedinPublisherCreateDraft?.addEventListener("click", async () => {
  linkedinPublisherCreateDraft.disabled = true;
  try {
    await runtimeClient.createLinkedInDraft(linkedinPublisherNewBody.value, selectedLinkedInPostId);
    linkedinPublisherNewBody.value = "";
    await loadLinkedInPublisher();
    linkedinPublisherStatus.textContent = "Bozza salvata. Nessun post pubblicato.";
  } catch (error) { linkedinPublisherStatus.textContent = `Bozza non salvata: ${error.message}`; }
  finally { linkedinPublisherCreateDraft.disabled = false; }
});
linkedinPublisherDrafts?.addEventListener("click", async (event) => {
  const card = event.target.closest("[data-publication-draft-id]");
  if (!card) return;
  const draftId = Number(card.dataset.publicationDraftId);
  const body = card.querySelector("textarea")?.value || "";
  const save = event.target.closest("[data-publication-save]");
  const publish = event.target.closest("[data-publication-publish]");
  if (!save && !publish) return;
  event.target.disabled = true;
  try {
    let message = "";
    if (save) {
      await runtimeClient.updateLinkedInDraft(draftId, body);
      message = `Bozza #${draftId} aggiornata.`;
    } else {
      const stored = linkedinPublicationDrafts.find((draft) => draft.draft_id === draftId);
      if (!stored || stored.body !== body) throw new Error("Salva le modifiche prima di pubblicare.");
      if (window.prompt("Stai per pubblicare sul profilo LinkedIn aperto nel tuo Chrome standard. Scrivi PUBBLICA per confermare:", "") !== "PUBBLICA") {
        linkedinPublisherStatus.textContent = "Pubblicazione annullata.";
        return;
      }
      const result = await runtimeClient.publishLinkedInDraft(draftId, body);
      message = result.state === "published" ? `Bozza #${draftId} pubblicata.`
        : result.state === "unknown" ? `Esito incerto: controlla LinkedIn prima di riprovare. ${result.error || ""}`
        : `Pubblicazione non riuscita: ${result.error || "controlla la bozza"}`;
    }
    await loadLinkedInPublisher();
    linkedinPublisherStatus.textContent = message;
  } catch (error) { linkedinPublisherStatus.textContent = `Operazione non riuscita: ${error.message}`; }
  finally { event.target.disabled = false; }
});
reportAiNewsArchive?.addEventListener("click", (event) => {
  const entry = event.target.closest("[data-ai-news-id]");
  if (!entry) return;
  selectedAiNewsId = entry.dataset.aiNewsId || "";
  renderAiNewsDashboard();
});
reportAiNewsDetail?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-ai-news-copy]");
  if (!button) return;
  const task = aiNewsBriefings.find((item) => item.id === selectedAiNewsId);
  const script = aiNewsSections(task?.result?.summary).script;
  if (!script) return;
  try {
    await navigator.clipboard.writeText(script);
    button.textContent = "Copiato!";
    window.setTimeout(() => { if (button.isConnected) button.textContent = "Copia script"; }, 1800);
  } catch (_error) { button.textContent = "Copia non riuscita"; }
});
reportPeriod?.addEventListener("change", () => {
  void loadVintedReport();
});
reportSaleTime?.addEventListener("change", () => {
  reportSaleTimeFilter = reportSaleTime.value || "all";
  renderReportArticles();
});
reportClearSelectionButton?.addEventListener("click", () => {
  reportSelectedArticleKeys.clear();
  renderReportArticles();
});
reportSourcingSelectedButton?.addEventListener("click", () => {
  void startReportSourcingBatch();
});
reportFilterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    reportArticleFilter = button.dataset.reportFilter || "all";
    reportFilterButtons.forEach((candidate) => {
      candidate.classList.toggle("report-filter--active", candidate === button);
    });
    renderReportArticles();
  });
});
reportTabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const selectedTab = button.dataset.reportTab || "overview";
    reportTabButtons.forEach((candidate) => {
      candidate.classList.toggle("report-tab--active", candidate === button);
    });
    reportPanels.forEach((panel) => {
      panel.hidden = panel.dataset.reportPanel !== selectedTab;
    });
    if (selectedTab === "ai-news") void loadAiNewsDashboard();
    if (selectedTab === "linkedin") void loadLinkedInPosts();
    if (selectedTab === "linkedin-publisher") void loadLinkedInPublisher();
    if (selectedTab === "monitoring") void refreshMonitoringDashboard();
  });
});
monitoringRefreshButton?.addEventListener("click", () => { void refreshMonitoringDashboard(); });
monitoringJobs?.addEventListener("click", async (event) => {
  const startButton = event.target.closest("[data-monitoring-start]");
  if (startButton) {
    const definition = monitoringJobDefinitions.find((item) => item.action === startButton.dataset.monitoringStart);
    if (!definition) return;
    startButton.disabled = true;
    try {
      await startMonitoringJob(definition);
      await refreshMonitoringDashboard();
    } catch (error) {
      if (monitoringStatus) monitoringStatus.textContent = `Avvio non riuscito: ${error.message}`;
    } finally {
      startButton.disabled = false;
    }
    return;
  }
  const stopButton = event.target.closest("[data-monitoring-stop]");
  if (stopButton) {
    stopButton.disabled = true;
    try {
      await runtimeClient.cancelProjectJob(stopButton.dataset.monitoringStop);
      await refreshProjectJobHistory(false);
      await refreshMonitoringDashboard();
    } catch (error) {
      if (monitoringStatus) monitoringStatus.textContent = `Arresto non riuscito: ${error.message}`;
      stopButton.disabled = false;
    }
  }
});
reportCompetitorStatus?.addEventListener("change", () => {
  reportCompetitorStatusFilter = reportCompetitorStatus.value || "all";
  renderReportCompetitors();
});
reportProcacciatoreStatus?.addEventListener("change", () => {
  reportProcacciatoreStatusFilter = reportProcacciatoreStatus.value || "all";
  renderReportProcacciatore();
});
eventLog?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-activity-job]");
  if (!button) return;
  const job = activityJobCache.get(button.dataset.activityJob) || projectJobsCache.get(button.dataset.activityJob);
  if (!job) {
    setBootMessage("Job details are not in the local activity cache. Open Jobs & Notifications to reload history.");
    return;
  }
  if (job.agent_id && network.getAgent(job.agent_id)) selectedAgentId = job.agent_id;
  openJobOutput(job);
  updateHud();
});
reportKeywordSearch?.addEventListener("input", () => {
  const query = reportKeywordSearch.value.trim().toLowerCase();
  reportKeywords.querySelectorAll("[data-keyword-row]").forEach((row) => {
    row.hidden = !String(row.dataset.keyword || "").includes(query);
  });
});
reportOwnedForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  reportOwnedError.textContent = "";
  const submit = reportOwnedForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    await runtimeClient.saveVintedOwnedProfile(reportOwnedUrl.value, reportOwnedName.value);
    reportOwnedForm.reset();
    await loadVintedReport();
  } catch (error) {
    reportOwnedError.textContent = error.message;
    reportUiError("ui.vinted-reports.owned-profile-save", error, { phase: "save-owned-profile" });
  } finally {
    submit.disabled = false;
  }
});
reportOwnedProfiles?.addEventListener("click", async (event) => {
  const ignoreButton = event.target.closest("[data-owned-item-ignore]");
  if (ignoreButton) {
    const memberId = ignoreButton.dataset.ownedItemMember;
    const itemId = ignoreButton.dataset.ownedItemIgnore;
    if (!memberId || !itemId || !window.confirm(`Non tracciare più l'articolo ${itemId} in questo profilo? Lo storico resterà salvato.`)) return;
    ignoreButton.disabled = true;
    reportOwnedError.textContent = "";
    try {
      await runtimeClient.ignoreVintedOwnedProfileItem(memberId, itemId);
      await loadVintedReport();
    } catch (error) {
      reportOwnedError.textContent = error.message;
      reportUiError("ui.vinted-reports.owned-item-ignore", error, { phase: "ignore-owned-item", member_id: memberId, item_id: itemId });
      ignoreButton.disabled = false;
    }
    return;
  }
  const button = event.target.closest("[data-owned-profile-remove]");
  if (!button) return;
  button.disabled = true;
  reportOwnedError.textContent = "";
  try {
    await runtimeClient.removeVintedOwnedProfile(button.dataset.ownedProfileRemove);
    await loadVintedReport();
  } catch (error) {
    reportOwnedError.textContent = error.message;
    reportUiError("ui.vinted-reports.owned-profile-remove", error, { phase: "remove-owned-profile" });
    button.disabled = false;
  }
});
reportOwnedStatus?.addEventListener("change", () => {
  reportOwnedStatusFilter = reportOwnedStatus.value || "all";
  renderReportOwnedProfiles();
});
reportOwnedSearch?.addEventListener("input", () => {
  reportOwnedSearchFilter = reportOwnedSearch.value.trim().toLowerCase();
  renderReportOwnedProfiles();
});
reportDialog?.querySelectorAll("[data-report-close]").forEach((button) => {
  button.addEventListener("click", () => reportDialog.close());
});
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

roomDetails?.addEventListener("click", (event) => {
  const jobButton = event.target.closest("[data-room-job]");
  if (jobButton) {
    const job = activityJobCache.get(jobButton.dataset.roomJob) || projectJobsCache.get(jobButton.dataset.roomJob);
    if (job) openJobOutput(job);
    return;
  }
  const agentButton = event.target.closest("[data-room-agent]");
  if (!agentButton) return;
  const agent = network.getAgent(agentButton.dataset.roomAgent);
  if (!agent) return;
  selectedAgentId = agent.id;
  selectedStationId = null;
  const position = agentWorld.getAgentPosition(agent.id);
  cameraTarget.set(position.x, 0, position.z);
  updateCamera();
  updateHud();
});

addAgentButton.addEventListener("click", () => {
  agentFormError.textContent = "";
  if (!runtimeClient.connected) {
    setBootMessage("Start the project with run.command to create persistent agents.");
    return;
  }
  renderWorkstationPresetOptions(agentWorkstationPreset, agentForm.elements.namedItem("role")?.value ?? "specialist");
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
for (const button of quickChatTabs) {
  button.addEventListener("click", () => setQuickChatView(button.dataset.quickChatTab || "chat"));
}

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
  quickChatStatus.textContent = "Assigning...";
  quickChatStatus.classList.remove("agent-quick-chat__status--error");
  try {
    const task = await createAgentChatTask(agentId, message, { title: message.slice(0, 160), priority: 3 });
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
    quickChatStatus.textContent = `Assigned: ${task.id}`;
  } catch (error) {
    quickChatStatus.textContent = error.message;
    quickChatStatus.classList.add("agent-quick-chat__status--error");
    runtimeClient.logClient("error", error.message, { operation: "quickChat", agentId });
  } finally {
    submitButton.disabled = false;
    quickChatInput.focus();
  }
});

memoryCoreChatButton?.addEventListener("click", () => {
  if (!runtimeClient.connected) {
    setBootMessage("Runtime offline.");
    return;
  }
  openQuickChat("memory");
});

taskThreadList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-task-thread]");
  if (!button) {
    return;
  }
  selectedTaskThreadId = button.dataset.taskThread || "";
  renderTaskThreadList();
  renderSelectedTaskThread();
});

refreshTaskThreadsButton?.addEventListener("click", () => {
  void refreshTaskThreads();
});

memoryCoreSettingsButton?.addEventListener("click", () => {
  if (!runtimeClient.connected) {
    setBootMessage("Runtime offline.");
    return;
  }
  selectedAgentId = "memory";
  openAgentSettings();
});

agentActionDialog.querySelectorAll("[data-agent-action-close]").forEach((button) => {
  button.addEventListener("click", () => agentActionDialog.close());
});
agentActionDialog.addEventListener("close", () => {
  stopRunPodLiveStatusRefresh();
  stopAppiumScreenPolling("Anteprima in pausa mentre la finestra dell’agente è chiusa.");
  // Closing this popup restores autonomy only for the agent it belongs to.
  const agent = network.getAgent(selectedAgentId);
  if (agent) agentWorld.resumeAutoAgent(agent);
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
browserSessionSelect?.addEventListener("change", () => {
  selectedBrowserSessionId = browserSessionSelect.value;
  updateBrowserStatus(browserSessionSelect.value ? `Sessione selezionata: ${browserSessionSelect.value}` : "Nessuna sessione selezionata.");
});
browserRefreshSessionsButton?.addEventListener("click", () => {
  void refreshBrowserSessions();
});
browserOpenSessionButton?.addEventListener("click", () => {
  void openBrowserSessionFromPopup();
});
browserCurrentUrlButton?.addEventListener("click", () => {
  void (async () => {
    const result = await runBrowserPopupCommand("current_url", {});
    if (result?.url) {
      browserUrlInput.value = result.url;
      updateBrowserStatus(`URL attuale: ${result.url}`);
    }
  })();
});
browserSnapshotButton?.addEventListener("click", () => {
  void (async () => {
    const result = await runBrowserPopupCommand("snapshot", {});
    if (result) {
      updateBrowserStatus(`Snapshot: ${JSON.stringify(result).slice(0, 180)}`);
    }
  })();
});
browserGotoButton?.addEventListener("click", () => {
  void runBrowserPopupCommand("goto", { url: browserUrlInput?.value.trim() ?? "" });
});
browserClickTextButton?.addEventListener("click", () => {
  void runBrowserPopupCommand("click_text", { text: browserTextInput?.value.trim() ?? "" });
});
browserClickSelectorButton?.addEventListener("click", () => {
  void runBrowserPopupCommand("click_selector", { selector: browserSelectorInput?.value.trim() ?? "" });
});
browserTypeButton?.addEventListener("click", () => {
  void runBrowserPopupCommand("type", {
    selector: browserSelectorInput?.value.trim() ?? "",
    value: browserValueInput?.value ?? "",
  });
});
browserExtractButton?.addEventListener("click", () => {
  void (async () => {
    const result = await runBrowserPopupCommand("extract", {
      selector: browserSelectorInput?.value.trim() ?? "body",
      mode: "text",
    });
    if (result) {
      updateBrowserStatus(`Extract: ${JSON.stringify(result).slice(0, 180)}`);
    }
  })();
});
browserCloseButton?.addEventListener("click", () => {
  void (async () => {
    const sessionId = currentBrowserSession();
    if (!sessionId) {
      updateBrowserStatus("Seleziona prima una sessione browser.");
      return;
    }
    try {
      await runtimeClient.closeBrowserSession(sessionId);
      selectedBrowserSessionId = "";
      await refreshBrowserSessions();
      updateBrowserStatus(`Sessione chiusa: ${sessionId}`);
    } catch (error) {
      updateBrowserStatus(error.message);
    }
  })();
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
projectJobFilterButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    projectJobFilter = button.dataset.jobFilter || "all";
    syncProjectJobFilterButtons();
    await refreshProjectJobHistory(false);
  });
});
refreshWikiProposalsButton?.addEventListener("click", () => {
  void refreshWikiProposals();
});
wikiProposalList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-wiki-action]");
  if (button) {
    void resolveWikiProposalFromButton(button);
  }
});
refreshWikiPagesButton?.addEventListener("click", () => {
  void refreshWikiPages();
});
searchWikiPagesButton?.addEventListener("click", () => {
  void searchWikiPages();
});
wikiSearchQuery?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    void searchWikiPages();
  }
});
runWikiMaintenanceButton?.addEventListener("click", (event) => {
  void runWikiMaintenanceFromUi(event.currentTarget);
});
wikiPageList?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-wiki-page]");
  if (button) {
    void openWikiPage(button.dataset.wikiPage);
  }
});
jobNotificationsButton?.addEventListener("click", async () => {
  if (!projectDialog.open) {
    await openProjectGateway({ panel: "finished", mode: "notifications" });
    if (!projectDialog.open) {
      return;
    }
  }
  projectDialogMode = "notifications";
  projectJobFilter = "all";
  syncProjectDialogMode();
  syncProjectJobFilterButtons();
  setProjectPanel("finished");
});
activeWorkAllButton?.addEventListener("click", () => jobNotificationsButton?.click());
activeWorkList?.addEventListener("click", (event) => {
  const stopButton = event.target.closest("[data-active-work-stop]");
  if (stopButton) {
    event.stopPropagation();
    stopButton.disabled = true;
    void stopProjectJob(stopButton.dataset.activeWorkStop, stopButton);
    return;
  }
  const button = event.target.closest("[data-active-work-job]");
  if (!button) return;
  const job = activeProjectJobs.get(button.dataset.activeWorkJob);
  if (job) {
    projectDialogMode = "gateway";
    syncProjectDialogMode();
    openJobOutput(job);
  }
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

agentForm.elements.namedItem("role")?.addEventListener("change", (event) => {
  renderWorkstationPresetOptions(agentWorkstationPreset, event.target.value);
});

agentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(agentForm);
  const name = String(formData.get("name") ?? "").trim();
  const capabilities = splitValues(String(formData.get("capabilities") ?? ""));
  const workstationPresetId = String(formData.get("workstation_preset") ?? "");
  const createButton = document.querySelector("#create-agent");
  createButton.disabled = true;
  agentFormError.textContent = "";
  try {
    const snapshot = await runtimeClient.createAgent({
      id: `${slugify(name)}-${Date.now().toString(36).slice(-4)}`,
      name,
      role: String(formData.get("role") ?? "specialist"),
      color: String(formData.get("color") ?? "#5ee7f2"),
      capabilities,
      toolsets: splitValues(String(formData.get("toolsets") ?? "")),
      protocols: ["agent-lifecycle", "task-contract"],
      memory_scope: "agent",
    });
    const agent = ensureRuntimeAgent(snapshot);
    agentForm.reset();
    agentDialog.close();
    createLinkedWorkstation(agent, workstationPresetId, { reason: "Agente creato, workstation pronta" });
  } catch (error) {
    agentFormError.textContent = error.message;
  } finally {
    createButton.disabled = false;
  }
});

configureAgentButton.addEventListener("click", openAgentSettings);
systemSettingsButton?.addEventListener("click", () => {
  void openSystemSettings();
});

agentSettingsDialog.querySelectorAll("[data-settings-close]").forEach((button) => {
  button.addEventListener("click", () => agentSettingsDialog.close());
});
systemSettingsDialog?.querySelectorAll("[data-system-settings-close]").forEach((button) => {
  button.addEventListener("click", () => systemSettingsDialog.close());
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
    if (value("api_key")) {
      await saveSelectedApiKey(snapshot);
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
systemSettingsField("provider")?.addEventListener("change", () => {
  updateSystemProviderControls(true);
});

modelPickerField().addEventListener("change", () => {
  syncModelFieldFromPicker();
});
systemModelPickerField()?.addEventListener("change", () => {
  syncSystemModelFieldFromPicker();
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

document.querySelector("#save-api-key").addEventListener("click", async () => {
  const snapshot = runtimeSnapshots.get(selectedAgentId);
  if (!snapshot) {
    return;
  }
  const saveKeyButton = document.querySelector("#save-api-key");
  saveKeyButton.disabled = true;
  agentSettingsError.textContent = "";
  try {
    await saveSelectedApiKey(snapshot);
    setBootMessage(
      String(settingsField("api_key_scope").value) === "agent"
        ? `Saved API key for ${snapshot.name}.`
        : "Saved project API key."
    );
  } catch (error) {
    agentSettingsError.textContent = error.message;
  } finally {
    saveKeyButton.disabled = false;
  }
});

function renderRunPodActionResult(label, result) {
  if (runPodActionStatus) {
    const error = String(result?.error ?? "").trim();
    const message = String(result?.message ?? "").trim();
    const id = String(result?.id ?? "").trim();
    const promptId = String(result?.prompt_id ?? result?.promptId ?? "").trim();
    const status = String(result?.status ?? "").trim();
    const details = error || message || [id && `Pod ${id}`, status, promptId && `workflow ${promptId}`].filter(Boolean).join(" · ") || "Complete";
    runPodActionStatus.textContent = `${label}: ${details}`;
  }
}

function restoreRunPodJobs() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(runPodJobsStorageKey) || "[]");
    runPodJobs = Array.isArray(saved) ? saved.filter((job) => job?.podId && job?.promptId).slice(0, 12) : [];
  } catch {
    runPodJobs = [];
  }
  renderRunPodJobs();
}

function persistRunPodJobs() {
  try {
    window.localStorage.setItem(runPodJobsStorageKey, JSON.stringify(runPodJobs.slice(0, 12)));
  } catch {
    // Local display persistence is optional; never block an active ComfyUI job for it.
  }
}

function runPodOutputUrl(job, output) {
  const port = Number(runPodDashboardSnapshot?.settings?.runpod?.comfyui_port ?? 8188) || 8188;
  const url = new URL(`https://${encodeURIComponent(job.podId)}-${port}.proxy.runpod.net/view`);
  url.searchParams.set("filename", String(output.filename ?? ""));
  url.searchParams.set("subfolder", String(output.subfolder ?? ""));
  url.searchParams.set("type", String(output.type ?? "output"));
  return url.href;
}

function collectRunPodOutputs(history, promptId) {
  const record = history?.[promptId] || Object.values(history || {})[0];
  if (!record || typeof record !== "object") return { status: "Waiting to start", done: false, outputs: [], error: "" };
  const status = String(record?.status?.status_str ?? "Running");
  const done = Boolean(record?.status?.completed) || ["success", "error"].includes(status.toLowerCase());
  const messages = Array.isArray(record?.status?.messages) ? record.status.messages : [];
  const failure = messages.find((message) => Array.isArray(message) && String(message[0]).includes("execution_error"));
  const error = failure ? JSON.stringify(failure[1] ?? failure).slice(0, 1000) : "";
  const found = [];
  const seen = new Set();
  for (const nodeOutput of Object.values(record?.outputs ?? {})) {
    if (!nodeOutput || typeof nodeOutput !== "object") continue;
    for (const property of ["images", "gifs", "videos"]) {
      for (const output of Array.isArray(nodeOutput[property]) ? nodeOutput[property] : []) {
        if (!output?.filename) continue;
        const key = [output.filename, output.subfolder ?? "", output.type ?? "output"].join("/");
        if (seen.has(key)) continue;
        seen.add(key);
        found.push({ filename: String(output.filename), subfolder: String(output.subfolder ?? ""), type: String(output.type ?? "output") });
      }
    }
  }
  return { status, done, outputs: found, error };
}

function isVideoOutput(filename) {
  return /\.(mp4|webm|mov|mkv|avi)$/i.test(filename);
}

function renderRunPodJobs() {
  if (!runPodJobResults) return;
  runPodJobResults.replaceChildren();
  if (!runPodJobs.length) {
    const empty = document.createElement("small");
    empty.textContent = "No workflow has been queued from this browser yet.";
    runPodJobResults.append(empty);
    return;
  }
  for (const job of runPodJobs) {
    const card = document.createElement("article");
    card.className = "runpod-job";
    const title = document.createElement("strong");
    title.textContent = `${job.workflowName || "ComfyUI workflow"} · ${job.promptId}`;
    const status = document.createElement("span");
    status.className = "runpod-job__status";
    status.textContent = job.status || "Queued";
    card.append(title, status);
    if (job.error) {
      const error = document.createElement("span");
      error.className = "runpod-job__error";
      error.textContent = job.error;
      card.append(error);
    }
    if (Array.isArray(job.outputs) && job.outputs.length) {
      const outputs = document.createElement("div");
      outputs.className = "runpod-job__outputs";
      for (const output of job.outputs) {
        const url = runPodOutputUrl(job, output);
        if (isVideoOutput(output.filename)) {
          const video = document.createElement("video");
          video.controls = true;
          video.preload = "metadata";
          video.src = url;
          outputs.append(video);
        } else {
          const image = document.createElement("img");
          image.loading = "lazy";
          image.alt = output.filename;
          image.src = url;
          outputs.append(image);
        }
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `Download ${output.filename}`;
        outputs.append(link);
      }
      card.append(outputs);
    }
    runPodJobResults.append(card);
  }
}

async function pollRunPodJobs() {
  const activeJobs = runPodJobs.filter((job) => !job.done);
  if (!activeJobs.length) {
    if (runPodJobPollTimer) window.clearInterval(runPodJobPollTimer);
    runPodJobPollTimer = null;
    return;
  }
  try {
    if (!runtimeClient.connected) await runtimeClient.connect();
    await Promise.all(activeJobs.map(async (job) => {
      try {
        const history = await runtimeClient.getRunPodComfyUiHistory(job.podId, job.promptId);
        const update = collectRunPodOutputs(history, job.promptId);
        Object.assign(job, update);
      } catch (error) {
        job.status = "Waiting for ComfyUI history";
        job.error = error.message;
      }
    }));
    persistRunPodJobs();
    renderRunPodJobs();
  } catch {
    // The status panel already exposes runtime connectivity; keep jobs for the next polling cycle.
  }
}

function startRunPodJobPolling() {
  void pollRunPodJobs();
  if (runPodJobPollTimer) return;
  runPodJobPollTimer = window.setInterval(() => void pollRunPodJobs(), 3000);
}

function batchOutputUrl(batch, item, outputIndex) {
  return `/api/runpod/batches/${encodeURIComponent(batch.id)}/items/${encodeURIComponent(item.id)}/outputs/${outputIndex}`;
}

function renderRunPodBatches(batches) {
  if (!runPodBatchResults) return;
  runPodBatchResults.replaceChildren();
  if (!Array.isArray(batches) || !batches.length) {
    const empty = document.createElement("small");
    empty.textContent = "No batch created from this browser yet.";
    runPodBatchResults.append(empty);
    return;
  }
  for (const batch of batches.slice(0, 8)) {
    const card = document.createElement("article");
    card.className = "runpod-batch";
    const title = document.createElement("strong");
    title.textContent = `${batch.id} · ${batch.status}`;
    const detail = document.createElement("small");
    const counts = batch.counts && typeof batch.counts === "object" ? batch.counts : {};
    detail.textContent = `Pod: ${batch.pod_id || "deploying automatically"} · ${counts.completed || 0} completed · ${counts.processing || 0} processing · ${counts.queued || 0} queued · ${counts.failed || 0} failed`;
    card.append(title, detail);
    if (batch.error) {
      const error = document.createElement("span");
      error.className = "runpod-job__error";
      error.textContent = String(batch.error);
      card.append(error);
    }
    const items = Array.isArray(batch.items) ? batch.items : [];
    const list = document.createElement("div");
    list.className = "runpod-batch__items";
    for (const item of items) {
      const line = document.createElement("div");
      line.textContent = `${item.ordinal}. ${item.filename} — ${item.status}${item.error ? ` (${item.error})` : ""}`;
      list.append(line);
      for (const [outputIndex, output] of (Array.isArray(item.outputs) ? item.outputs : []).entries()) {
        if (!output?.filename) continue;
        const link = document.createElement("a");
        link.href = output.local_path ? batchOutputUrl(batch, item, outputIndex) : runPodOutputUrl({ podId: batch.pod_id }, output);
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `Output: ${output.filename}`;
        list.append(link);
      }
    }
    card.append(list);
    if (["starting", "waiting_for_gpu", "waiting_for_comfyui", "running"].includes(String(batch.status))) {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "button";
      cancel.textContent = "Stop batch";
      cancel.addEventListener("click", async () => {
        await runRunPodAction("Stopping automatic batch", async () => runtimeClient.cancelRunPodBatch(batch.id));
        void refreshRunPodBatches();
      });
      card.append(cancel);
    }
    runPodBatchResults.append(card);
  }
}

async function refreshRunPodBatches() {
  if (!runtimeClient.connected) await runtimeClient.connect();
  const response = await runtimeClient.listRunPodBatches();
  const batches = Array.isArray(response?.batches) ? response.batches : [];
  renderRunPodBatches(batches);
  const active = batches.some((batch) => ["starting", "waiting_for_gpu", "waiting_for_comfyui", "running"].includes(String(batch?.status)));
  if (!active && runPodBatchPollTimer) {
    window.clearInterval(runPodBatchPollTimer);
    runPodBatchPollTimer = null;
  }
  return batches;
}

function startRunPodBatchPolling() {
  void refreshRunPodBatches().catch(() => {});
  if (runPodBatchPollTimer) return;
  runPodBatchPollTimer = window.setInterval(() => void refreshRunPodBatches().catch(() => {}), 5000);
}

async function readMediaAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

restoreRunPodJobs();

function selectedRunPodId() {
  return String(runPodIdInput?.value ?? "").trim();
}

function requireRunPodId() {
  const podId = selectedRunPodId();
  if (!podId) {
    renderRunPodActionResult("RunPod action failed", { error: "Enter or select a Target Pod ID first." });
  }
  return podId;
}

async function runRunPodAction(label, action) {
  if (!runtimeClient.connected) {
    renderRunPodActionResult("Reconnecting to runtime", { message: "Trying the local runtime…" });
    try {
      await runtimeClient.connect();
    } catch (error) {
      renderRunPodActionResult(`${label} unavailable`, { error: "The local runtime is offline. Refresh the page after starting it." });
      return null;
    }
  }
  renderRunPodActionResult(label, { status: "working" });
  try {
    const result = await action();
    if (result?.id && runPodIdInput) {
      runPodIdInput.value = result.id;
    }
    if (result?.id && result?.status && runPodCardPods) {
      const state = String(result.status).toUpperCase();
      runPodCardPods.textContent = state === "RUNNING" ? "1 running" : state;
      if (runPodCardPodsDetail) runPodCardPodsDetail.textContent = `${result.name || result.id}: ${state}`;
      setRunPodCardState(runPodCardPods, state === "RUNNING" ? "running" : "stopped");
    }
    renderRunPodActionResult(label, result);
    return result;
  } catch (error) {
    renderRunPodActionResult(`${label} failed`, { error: error.message });
    reportUiError("ui.runpod.action", error, { action: label });
    return null;
  }
}

runPodRefreshPodsButton?.addEventListener("click", async () => {
  const status = await runRunPodAction("Refreshing RunPod inventory", async () => runtimeClient.getRunPodStatus());
  setRunPodPodOptions(status?.pods, selectedRunPodId());
});

runPodListVolumesButton?.addEventListener("click", async () => {
  const result = await runRunPodAction("Refreshing Network Volumes", async () => runtimeClient.listRunPodNetworkVolumes());
  const volumes = Array.isArray(result?.network_volumes) ? result.network_volumes : [];
  setRunPodVolumeOptions(volumes, String(runPodNetworkVolumeInput?.value ?? ""));
  const dataCenter = applySelectedVolumeDataCenter();
  renderRunPodActionResult("Network Volume picker updated", {
    volumes: volumes.length,
    selected_volume: String(runPodNetworkVolumeInput?.value ?? "") || "Choose a Network Volume",
    volume_data_center: dataCenter || "Select a volume to derive its data center.",
  });
});

runPodListDataCentersButton?.addEventListener("click", async () => {
  const result = await runRunPodAction("Refreshing RunPod regions", async () => runtimeClient.listRunPodDataCenters());
  const dataCenters = Array.isArray(result?.datacenters) ? result.datacenters : [];
  setRunPodDataCenterOptions(dataCenters, String(runPodDataCenterInput?.value ?? ""));
  renderRunPodActionResult("Region picker updated", {
    available_regions: dataCenters.length,
    next_step: "Select the data center hosting the Network Volume, then press List GPUs.",
  });
});

runPodPicker?.addEventListener("change", () => {
  if (runPodIdInput && runPodPicker.value) runPodIdInput.value = runPodPicker.value;
});

runPodNetworkVolumeInput?.addEventListener("change", () => {
  const dataCenter = applySelectedVolumeDataCenter();
  if (dataCenter) {
    renderRunPodActionResult("Network Volume selected", {
      volume_data_center: dataCenter,
      next_step: "Press List GPUs to see GPUs available for this exact volume region.",
    });
  }
});

async function refreshRunPodGpuChoices(announce = true) {
  const dataCenterId = String(runPodDataCenterInput?.value ?? "").trim();
  if (!dataCenterId) {
    if (announce) renderRunPodActionResult("List GPUs failed", { error: "Select a Network Volume first." });
    return [];
  }
  const result = await runRunPodAction("Listing available GPUs", async () => runtimeClient.listRunPodGpus(dataCenterId));
  const gpus = Array.isArray(result?.gpus) ? result.gpus : [];
  const selected = String(runPodGpuSelect?.value ?? "");
  setRunPodGpuOptions(gpus, selected, runPodGpuSelect);
  if (runPodCardGpus) runPodCardGpus.textContent = `${gpus.length} available`;
  if (runPodCardGpusDetail) runPodCardGpusDetail.textContent = selected ? `Selected: ${selected}` : "Choose one to deploy.";
  setRunPodCardState(runPodCardGpus, gpus.length ? "running" : "stopped");
  if (announce) renderRunPodActionResult(`GPU picker updated for ${dataCenterId}`, {
    message: `${gpus.length} compatible GPU types ready to select.`,
  });
  return gpus;
}

runPodListGpusButton?.addEventListener("click", async () => {
  await refreshRunPodGpuChoices(true);
});

runPodGpuSelect?.addEventListener("focus", () => {
  void refreshRunPodGpuChoices(false);
});

runPodSaveDeploymentButton?.addEventListener("click", async () => {
  await runRunPodAction("Saving RunPod deployment configuration", async () => {
    const settings = await runtimeClient.getSystemSettings();
    const nextRunPod = {
      ...(settings.runpod ?? {}),
      network_volume_id: String(runPodNetworkVolumeInput?.value ?? "").trim(),
      data_center_id: String(runPodDataCenterInput?.value ?? "").trim(),
      template_id: String(runPodTemplateInput?.value ?? "").trim(),
      container_image: String(runPodContainerImageInput?.value ?? "").trim(),
      preferred_gpu: String(runPodGpuSelect?.value ?? "").trim(),
      max_hourly_cost: Number(runPodMaxHourlyCostInput?.value ?? 0),
      volume_mount_path: String(runPodVolumeMountInput?.value ?? "/workspace").trim() || "/workspace",
      comfyui_port: Number(runPodComfyUiPortInput?.value ?? 8188),
      idle_action: String(runPodIdleActionSelect?.value ?? "stop"),
    };
    const updated = await runtimeClient.updateSystemSettings({ ...settings, runpod: nextRunPod });
    return { ok: true, runpod: updated.runpod };
  });
});

appiumSaveButton?.addEventListener("click", async () => {
  if (appiumSaveButton) appiumSaveButton.disabled = true;
  if (appiumActionStatus) appiumActionStatus.textContent = "Saving Appium settings…";
  try {
    const settings = await runtimeClient.getSystemSettings();
    const updated = await runtimeClient.updateSystemSettings({
      ...settings,
      appium: {
        ...(settings.appium ?? {}),
        enabled: appiumEnabledSelect?.value === "true",
        server_url: String(appiumServerUrlInput?.value ?? "http://127.0.0.1:4723").trim(),
        adb_path: String(appiumAdbPathInput?.value ?? "adb").trim() || "adb",
        ios_device_tool: String(appiumIosToolInput?.value ?? "idevice_id").trim() || "idevice_id",
      },
    });
    if (appiumActionStatus) appiumActionStatus.textContent = "Settings saved. Checking the configured server…";
    await refreshAppiumStatus();
    if (appiumActionStatus) appiumActionStatus.textContent = `Settings saved. Appium checks ${updated.appium?.enabled ? "enabled" : "disabled"}.`;
  } catch (error) {
    if (appiumActionStatus) appiumActionStatus.textContent = error.message;
    runtimeClient.logClient("error", error.message, { operation: "appium.save-settings" });
  } finally {
    if (appiumSaveButton) appiumSaveButton.disabled = false;
  }
});

appiumRefreshButton?.addEventListener("click", () => { void refreshAppiumStatus().catch(() => {}); });
appiumStartButton?.addEventListener("click", () => { void startAppiumServer(); });
appiumStopButton?.addEventListener("click", () => { void stopAppiumServer(); });
appiumListAppsButton?.addEventListener("click", () => { void listAppiumInstalledApps(); });
appiumLaunchAppButton?.addEventListener("click", () => { void launchAppiumSelectedApp(); });
appiumEndSessionButton?.addEventListener("click", () => { void endAppiumDeviceSession(); });

runPodCreatePodButton?.addEventListener("click", async () => {
  if (!window.confirm("Create a billed RunPod Pod using the saved configuration?")) return;
  await runRunPodAction("Creating RunPod Pod", async () => runtimeClient.createRunPodPod({
    name: String(runPodNameInput?.value ?? "Agent Lab ComfyUI").trim(),
    gpuId: String(runPodGpuSelect?.value ?? "").trim(),
  }));
});

runPodStartPodButton?.addEventListener("click", async () => {
  const podId = requireRunPodId();
  if (!podId) return;
  await runRunPodAction("Starting RunPod Pod", async () => runtimeClient.startRunPodPod(podId));
});

runPodStopPodButton?.addEventListener("click", async () => {
  const podId = requireRunPodId();
  if (!podId) return;
  if (!window.confirm(`Stop Pod ${podId}?`)) return;
  await runRunPodAction("Stopping RunPod Pod", async () => runtimeClient.stopRunPodPod(podId));
});

runPodTerminatePodButton?.addEventListener("click", async () => {
  const podId = requireRunPodId();
  if (!podId) return;
  if (!window.confirm(`Terminate Pod ${podId}? This may delete its local disk.`)) return;
  await runRunPodAction("Terminating RunPod Pod", async () => runtimeClient.terminateRunPodPod(podId));
});

runPodComfyUiHealthButton?.addEventListener("click", async () => {
  const podId = requireRunPodId();
  if (!podId) return;
  await runRunPodAction("Checking ComfyUI", async () => runtimeClient.getRunPodComfyUiHealth(podId));
});

function applyRunPodWorkflow(workflow, sourceLabel, suppliedLoaders = null) {
  if (!workflow || typeof workflow !== "object" || Array.isArray(workflow) || Array.isArray(workflow.nodes) || Array.isArray(workflow.links)) {
    throw new Error("This is a visual/canvas workflow. Export it from ComfyUI as API format first.");
  }
  const derivedLoaders = Object.entries(workflow).flatMap(([id, node]) => {
    const classType = String(node?.class_type ?? "");
    const inputs = node?.inputs && typeof node.inputs === "object" ? node.inputs : {};
    const normalized = classType.toLowerCase();
    if (normalized.includes("loadimage")) return [{ id, class_type: classType, kind: "image", input: "image", current: String(inputs.image ?? "") }];
    if (normalized.includes("loadvideo")) {
      const input = Object.prototype.hasOwnProperty.call(inputs, "video_name") && !Object.prototype.hasOwnProperty.call(inputs, "video") ? "video_name" : "video";
      return [{ id, class_type: classType, kind: "video", input, current: String(inputs[input] ?? "") }];
    }
    return [];
  });
  runPodWorkflowLoaders = Array.isArray(suppliedLoaders) && suppliedLoaders.length
    ? suppliedLoaders.map((loader) => ({
      id: String(loader.id ?? ""), class_type: String(loader.class_type ?? loader.classType ?? ""), kind: String(loader.kind ?? ""), input: String(loader.input ?? ""), current: String(loader.current ?? ""),
    })).filter((loader) => loader.id && ["image", "video"].includes(loader.kind))
    : derivedLoaders;
  if (!runPodWorkflowLoaders.length) {
    throw new Error("The workflow has no LoadImage or LoadVideo node, so uploaded media cannot be inserted automatically.");
  }
  if (runPodWorkflowInput) runPodWorkflowInput.value = JSON.stringify(workflow, null, 2);
  if (runPodMediaLoaderSelect) {
    runPodMediaLoaderSelect.replaceChildren();
    for (const loader of runPodWorkflowLoaders) {
      const option = document.createElement("option");
      option.value = loader.id;
      option.dataset.kind = loader.kind;
      option.textContent = `Node ${loader.id} · ${loader.class_type} · ${loader.kind} · ${loader.current || "no file selected"}`;
      runPodMediaLoaderSelect.append(option);
    }
  }
  const imageLoaders = runPodWorkflowLoaders.filter((loader) => loader.kind === "image").length;
  const videoLoaders = runPodWorkflowLoaders.filter((loader) => loader.kind === "video").length;
  if (runPodWorkflowStatus) {
    const inputs = [imageLoaders ? `${imageLoaders} image loader${imageLoaders === 1 ? "" : "s"}` : "", videoLoaders ? `${videoLoaders} video loader${videoLoaders === 1 ? "" : "s"}` : ""].filter(Boolean).join(" · ");
    runPodWorkflowStatus.textContent = `${sourceLabel} loaded: ${inputs}. Choose matching media, upload it, then Queue Workflow.`;
  }
  renderRunPodActionResult("Workflow loaded", { source: sourceLabel, image_loaders: imageLoaders, video_loaders: videoLoaders });
}

runPodLoadWorkflowButton?.addEventListener("click", () => {
  void (async () => {
    try {
      const file = runPodWorkflowFileInput?.files?.[0];
      if (!file) {
        if (runPodWorkflowStatus) runPodWorkflowStatus.textContent = "Choose a ComfyUI API JSON workflow first.";
        return;
      }
      const text = await file.text();
      const workflow = JSON.parse(text);
      applyRunPodWorkflow(workflow, file.name);
    } catch (error) {
      if (runPodWorkflowStatus) runPodWorkflowStatus.textContent = error.message;
      renderRunPodActionResult("Workflow load failed", { error: error.message });
    }
  })();
});

runPodLoadWorkflowPresetButton?.addEventListener("click", () => {
  void (async () => {
    try {
      const presetId = String(runPodWorkflowPresetSelect?.value ?? "").trim();
      if (!presetId) throw new Error("Choose a saved workflow first.");
      const preset = await runtimeClient.getRunPodWorkflow(presetId);
      applyRunPodWorkflow(preset.workflow, String(preset.name ?? presetId), preset.loaders);
    } catch (error) {
      if (runPodWorkflowStatus) runPodWorkflowStatus.textContent = error.message;
      renderRunPodActionResult("Saved workflow load failed", { error: error.message });
    }
  })();
});

creativePromptPreset?.addEventListener("change", () => {
  const prompt = creativePromptPreset.selectedOptions?.[0]?.dataset?.prompt || "";
  if (creativePromptText) creativePromptText.value = prompt;
});
runPodWorkflowPresetSelect?.addEventListener("change", () => void (async () => {
  const option = runPodWorkflowPresetSelect.selectedOptions?.[0];
  const workflowId = String(option?.value ?? "");
  if (!workflowId) return;
  const allowed = JSON.parse(String(option?.dataset?.creativePresets ?? "[]"));
  if (creativePromptPreset) {
    creativePromptPreset.replaceChildren();
    for (const preset of creativePromptPresets.filter((item) => !allowed.length || allowed.includes(item.id))) {
      const item = document.createElement("option"); item.value = String(preset.id); item.textContent = String(preset.name); item.dataset.prompt = String(preset.prompt ?? ""); creativePromptPreset.append(item);
    }
    if (creativePromptText) creativePromptText.value = creativePromptPreset.selectedOptions?.[0]?.dataset?.prompt || "";
  }
  if (creativePromptStatus) creativePromptStatus.textContent = `Checking compatible GPU for ${option.textContent}…`;
  try {
    const availability = await runtimeClient.getRunPodWorkflowAvailability(workflowId);
    const gpus = Array.isArray(availability.available) ? availability.available : [];
    if (creativePromptStatus) creativePromptStatus.textContent = gpus.length
      ? `${option.textContent} · ${availability.min_vram_gb} GB minimum · compatible now: ${gpus.map((gpu) => gpu.name).join(", ")}`
      : `${option.textContent} · Waiting for a compatible ${availability.min_vram_gb} GB GPU in ${availability.region}.`;
  } catch (error) { if (creativePromptStatus) creativePromptStatus.textContent = error.message; }
})());
creativeGeneratePrompt?.addEventListener("click", () => void (async () => {
  try {
    const file = creativePromptImage?.files?.[0];
    if (!file) throw new Error("Choose a reference image first.");
    if (creativePromptStatus) creativePromptStatus.textContent = "Analysing image with the configured OpenAI-compatible provider…";
    const result = await runtimeClient.generateComfyUiPrompt({ filename: file.name, imageBase64: await readMediaAsDataUrl(file) });
    if (creativePromptText) creativePromptText.value = String(result.prompt || "");
    if (creativePromptStatus) creativePromptStatus.textContent = `Prompt generated with ${result.model || "configured model"}.`;
  } catch (error) { if (creativePromptStatus) creativePromptStatus.textContent = error.message; }
})());

runPodQueueWorkflowButton?.addEventListener("click", async () => {
  const podId = requireRunPodId();
  if (!podId) return;
  const raw = String(runPodWorkflowInput?.value ?? "").trim();
  if (!raw) {
    renderRunPodActionResult("Queue workflow failed", { error: "Paste a ComfyUI workflow JSON before queuing it." });
    return;
  }
  let workflow;
  try {
    workflow = JSON.parse(raw);
  } catch (error) {
    renderRunPodActionResult("Queue workflow failed", { error: `Workflow JSON is invalid: ${error.message}` });
    return;
  }
  const result = await runRunPodAction("Queuing ComfyUI workflow", async () => runtimeClient.queueRunPodComfyUiPrompt(podId, workflow, {
    mediaName: runPodUploadedMedia.name,
    mediaKind: runPodUploadedMedia.kind,
    mediaLoaderId: String(runPodMediaLoaderSelect?.value ?? "").trim(),
  }));
  const promptId = String(result?.prompt_id ?? result?.promptId ?? "").trim();
  if (promptId) {
    const selectedPreset = runPodWorkflowPresetSelect?.selectedOptions?.[0];
    const workflowName = String(selectedPreset?.value ? selectedPreset.textContent : runPodWorkflowFileInput?.files?.[0]?.name ?? "ComfyUI workflow").trim();
    runPodJobs = [{
      podId,
      promptId,
      workflowName,
      status: "Queued · waiting for ComfyUI",
      done: false,
      outputs: [],
      error: "",
      createdAt: new Date().toISOString(),
    }, ...runPodJobs.filter((job) => !(job.podId === podId && job.promptId === promptId))].slice(0, 12);
    persistRunPodJobs();
    renderRunPodJobs();
    startRunPodJobPolling();
  }
  if (result && runPodUploadedMedia.name && runPodUploadStatus) {
    const count = Number(result.media_injected_nodes ?? 0);
    runPodUploadStatus.textContent = count
      ? `Queued: inserted ${runPodUploadedMedia.name} into ${count} compatible ${runPodUploadedMedia.kind} loader node${count === 1 ? "" : "s"}.`
      : `Queued. No compatible loader node was found for ${runPodUploadedMedia.kind} media.`;
  }
});

runPodUploadMediaButton?.addEventListener("click", () => {
  void (async () => {
    try {
      const podId = requireRunPodId();
      if (!podId) return;
      const file = runPodMediaFileInput?.files?.[0];
      if (!file) {
        if (runPodUploadStatus) runPodUploadStatus.textContent = "Choose an image or video first.";
        return;
      }
      if (file.size > 25 * 1024 * 1024) {
        if (runPodUploadStatus) runPodUploadStatus.textContent = "Media is larger than the 25 MB upload limit.";
        return;
      }
      const mediaKind = file.type.startsWith("video/") ? "video" : "image";
      const selectedLoader = runPodWorkflowLoaders.find((loader) => loader.id === String(runPodMediaLoaderSelect?.value ?? ""));
      if (selectedLoader && selectedLoader.kind !== mediaKind) {
        throw new Error(`Choose a ${mediaKind === "video" ? "LoadVideo" : "LoadImage"} node before uploading this ${mediaKind}.`);
      }
      if (runPodUploadStatus) runPodUploadStatus.textContent = `Reading ${file.name}…`;
      const dataBase64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("Could not read the selected media."));
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.readAsDataURL(file);
      });
      if (runPodUploadStatus) runPodUploadStatus.textContent = `Uploading ${file.name} to ComfyUI…`;
      const result = await runRunPodAction("Uploading media to ComfyUI", async () => runtimeClient.uploadRunPodComfyUiMedia(podId, {
        filename: file.name,
        dataBase64,
      }));
      if (!result) return;
      const workflowName = [String(result.subfolder ?? "").trim(), String(result.name ?? file.name)].filter(Boolean).join("/");
      runPodUploadedMedia = { name: workflowName, kind: mediaKind };
      const loader = mediaKind === "video" ? "LoadVideo" : "LoadImage";
      if (runPodUploadStatus) runPodUploadStatus.textContent = `Uploaded ${mediaKind}. It will be inserted into compatible ${loader} nodes when you queue the workflow.`;
      renderRunPodActionResult("Media uploaded", { message: `${workflowName} is ready for automatic ${loader} injection.` });
    } catch (error) {
      if (runPodUploadStatus) runPodUploadStatus.textContent = error.message;
      renderRunPodActionResult("Media upload failed", { error: error.message });
    }
  })();
});

runPodRefreshBatchesButton?.addEventListener("click", () => {
  void runRunPodAction("Refreshing automatic batches", refreshRunPodBatches);
});

runPodStartBatchButton?.addEventListener("click", () => {
  void (async () => {
    try {
      const raw = String(runPodWorkflowInput?.value ?? "").trim();
      if (!raw) throw new Error("Load a ComfyUI API workflow before starting a batch.");
      const workflow = JSON.parse(raw);
      const files = Array.from(runPodBatchFilesInput?.files ?? []);
      if (!files.length) throw new Error("Select one or more images/videos for the batch.");
      if (files.some((file) => file.size > 25 * 1024 * 1024)) throw new Error("Each batch file must be 25 MB or smaller.");
      const selectedLoader = runPodWorkflowLoaders.find((loader) => loader.id === String(runPodMediaLoaderSelect?.value ?? ""));
      if (!selectedLoader) throw new Error("Choose the target LoadImage or LoadVideo node first.");
      const incompatible = files.find((file) => (file.type.startsWith("video/") ? "video" : "image") !== selectedLoader.kind);
      if (incompatible) throw new Error(`${incompatible.name} does not match selected ${selectedLoader.kind === "video" ? "LoadVideo" : "LoadImage"} node.`);
      runPodStartBatchButton.disabled = true;
      renderRunPodActionResult("Creating automatic batch", { message: `Saving ${files.length} file(s) locally before deployment…` });
      if (!runtimeClient.connected) await runtimeClient.connect();
      const batch = await runtimeClient.createRunPodBatch({
        workflow,
        mediaLoaderId: selectedLoader.id,
        autoDeploy: true,
        autoShutdown: true,
        minVramGb: Number(runPodWorkflowPresetSelect?.selectedOptions?.[0]?.dataset?.minVram || 0),
        workflowId: String(runPodWorkflowPresetSelect?.value ?? ""),
        creativePrompt: String(creativePromptText?.value ?? "").trim(),
      });
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        renderRunPodActionResult("Preparing automatic batch", { message: `Saving ${index + 1}/${files.length}: ${file.name}` });
        await runtimeClient.addRunPodBatchItem(batch.id, { filename: file.name, dataBase64: await readMediaAsDataUrl(file) });
      }
      const started = await runtimeClient.startRunPodBatch(batch.id);
      renderRunPodActionResult("Automatic batch started", { message: `${batch.id} · ${files.length} item(s). Pod deployment and cleanup are automatic.` });
      if (runPodBatchFilesInput) runPodBatchFilesInput.value = "";
      renderRunPodBatches([started]);
      startRunPodBatchPolling();
    } catch (error) {
      renderRunPodActionResult("Automatic batch failed", { error: error.message });
      reportUiError("ui.runpod.batch", error, {});
    } finally {
      if (runPodStartBatchButton) runPodStartBatchButton.disabled = false;
    }
  })();
});

function renderRunPodGpuWatch(watch) {
  if (!runPodGpuWatchStatus) return;
  const gpus = watch?.gpus && typeof watch.gpus === "object" ? Object.values(watch.gpus) : [];
  const available = gpus.filter((gpu) => gpu?.available).map((gpu) => gpu.name).join(", ");
  runPodGpuWatchStatus.textContent = watch?.error
    ? `Watcher error: ${watch.error}`
    : `Watcher ${watch?.enabled ? "active" : "inactive"} · last check ${watch?.last_check || "never"} · ${available ? `available: ${available}` : "no tracked GPU available"}`;
  void refreshRunPodGpuHistorySummary();
}

async function refreshRunPodGpuHistorySummary() {
  const target = document.querySelector("#runpod-gpu-history-summary");
  if (!target || !runtimeClient.connected) return;
  try {
    const result = await runtimeClient.getRunPodGpuHistorySummary();
    const hours = Array.isArray(result.hours) ? result.hours : [];
    if (!hours.length) {
      target.textContent = "Availability history will appear after the first regional check.";
      return;
    }
    const leaders = hours.slice(0, 4).map((entry) =>
      `${String(entry.hour).padStart(2, "0")}:00 · avg ${entry.average_available} GPU(s) (${entry.checks} checks)`
    );
    target.textContent = `Best local-time availability windows · ${leaders.join(" | ")}`;
  } catch (error) {
    target.textContent = `Could not load GPU history: ${error.message}`;
  }
}

runPodGpuWatchEnable?.addEventListener("click", async () => {
  const gpuIds = Array.from(runPodGpuWatchGpus?.selectedOptions ?? []).map((option) => option.value);
  const result = await runRunPodAction("Enabling GPU availability watcher", async () => runtimeClient.configureRunPodGpuWatch({ enabled: true, gpuIds, intervalSeconds: Number(runPodGpuWatchInterval?.value ?? 60) }));
  renderRunPodGpuWatch(result);
});

runPodGpuWatchCheck?.addEventListener("click", async () => {
  const result = await runRunPodAction("Checking tracked GPU availability", async () => runtimeClient.checkRunPodGpuWatch());
  renderRunPodGpuWatch(result);
});

systemSettingsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  syncSystemModelFieldFromPicker();
  const value = (name) => String(systemSettingsField(name).value ?? "").trim();
  const saveButton = document.querySelector("#save-system-settings");
  saveButton.disabled = true;
  systemSettingsError.textContent = "";
  try {
    const settings = await runtimeClient.updateSystemSettings({
      configured: true,
      model: {
        provider: value("provider"),
        model: value("model"),
        base_url: value("base_url"),
        api_key_env: value("api_key_env").toUpperCase(),
        api_key_scope: value("api_key_scope"),
        temperature: Number(value("temperature")),
      },
      ui: {
        theme: value("theme"),
        auto_agents: value("auto_agents") === "true",
        simulation_speed: Number(value("simulation_speed")),
      },
      discord: {
        enabled: value("discord_enabled") === "true",
        command_prefix: value("discord_command_prefix") || "!",
        default_agent_id: value("discord_default_agent_id"),
        allowed_guild_ids: splitNumericIds(value("discord_allowed_guild_ids")),
        allowed_channel_ids: splitNumericIds(value("discord_allowed_channel_ids")),
        message_content: value("discord_message_content") === "true",
        sync_commands: value("discord_sync_commands") === "true",
      },
      diagnostics: {
        discord_error_notifications: value("discord_error_notifications") === "true",
        discord_webhook_url: value("discord_webhook_url"),
      },
      runpod: {
        enabled: value("runpod_enabled") === "true",
        network_volume_id: value("runpod_network_volume_id"),
        data_center_id: value("runpod_data_center_id"),
        template_id: value("runpod_template_id"),
        container_image: value("runpod_container_image"),
        preferred_gpu: value("runpod_preferred_gpu"),
        max_hourly_cost: Number(value("runpod_max_hourly_cost") || 0),
        volume_mount_path: value("runpod_volume_mount_path") || "/workspace",
        comfyui_port: Number(value("runpod_comfyui_port") || 8188),
        idle_action: value("runpod_idle_action") || "stop",
      },
    });
    if (value("project_api_key")) {
      const status = await runtimeClient.setProjectSecret(value("project_api_key"));
      renderSystemSecretStatus(status);
      systemSettingsField("project_api_key").value = "";
    }
    if (value("discord_bot_token")) {
      const status = await runtimeClient.setDiscordBotSecret(value("discord_bot_token"));
      renderSystemSecretStatus(status);
      systemSettingsField("discord_bot_token").value = "";
    }
    if (value("accordi_admin_token")) {
      const status = await runtimeClient.setAccordiAdminSecret(value("accordi_admin_token"));
      renderSystemSecretStatus(status);
      systemSettingsField("accordi_admin_token").value = "";
    }
    if (value("runpod_api_key")) {
      const status = await runtimeClient.setRunPodSecret(value("runpod_api_key"));
      renderSystemSecretStatus(status);
      systemSettingsField("runpod_api_key").value = "";
    }
    applySystemSettingsToUi(settings);
    const agents = await runtimeClient.listAgents();
    for (const agent of agents) {
      ensureRuntimeAgent(agent);
      runtimeSnapshots.set(agent.id, agent);
    }
    renderWorkstationControls();
    systemSettingsDialog.close();
    setBootMessage("Global system settings saved and applied to all agents.");
  } catch (error) {
    systemSettingsError.textContent = error.message;
    reportUiError("ui.system-settings.save", error, { phase: "save-system-settings" });
  } finally {
    saveButton.disabled = false;
  }
});

window.addEventListener("resize", resize);
window.addEventListener("error", (event) => {
  runtimeClient.logClient("error", event.message || "Unhandled browser error", {
    source: event.filename,
    line: event.lineno,
    column: event.colno,
  });
  reportUiError("ui.window.error", event.error || event.message || "Unhandled browser error", {
    source_file: event.filename || "",
    line: event.lineno || 0,
    column: event.colno || 0,
  });
});
window.addEventListener("unhandledrejection", (event) => {
  runtimeClient.logClient("error", event.reason?.message ?? String(event.reason), {
    operation: "unhandledrejection",
  });
  reportUiError("ui.unhandledrejection", event.reason?.message ?? String(event.reason), {
    operation: "unhandledrejection",
  });
});

setupDraggablePopups();
applyTheme(currentTheme, { persist: false });
applyAtmosphere(currentAtmosphereMode, { persist: false });
updateWorldClock();
window.setInterval(updateWorldClock, 1000);
document.addEventListener("visibilitychange", updateWorldClock);
buildScene();
resize();
setSpeed(1);
setAutoAgents(true);
setBootMessage("");
window.__agentLabBooted = true;
renderJobNotificationBadge();
updateLayoutHistoryControls();
connectRuntime();
requestAnimationFrame(animate);
