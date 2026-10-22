export const JOB_NOTIFICATION_STORAGE_KEY = "agent-protocol-lab-job-notifications-v2";

function normalizedId(value) {
  return String(value ?? "").trim();
}

function timestamp(value) {
  const parsed = Date.parse(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function isTerminal(job) {
  return job?.state === "completed" || job?.state === "failed";
}

export class JobNotificationState {
  constructor(storage = globalThis.localStorage, key = JOB_NOTIFICATION_STORAGE_KEY) {
    this.storage = storage;
    this.key = key;
    this.state = this.read();
  }

  read() {
    try {
      const value = JSON.parse(this.storage?.getItem(this.key) ?? "null");
      if (value?.version === 2) {
        return {
          initialized: Boolean(value.initialized),
          lastObservedAt: timestamp(value.lastObservedAt),
          knownIds: new Set(Array.isArray(value.knownIds) ? value.knownIds.map(normalizedId).filter(Boolean) : []),
          unreadIds: new Set(Array.isArray(value.unreadIds) ? value.unreadIds.map(normalizedId).filter(Boolean) : []),
        };
      }
      // Migrate the old seen-id list without treating the entire job history as unread.
      const legacySeen = JSON.parse(this.storage?.getItem("agent-protocol-lab-job-notifications-v1") ?? "[]");
      return {
        initialized: false,
        lastObservedAt: 0,
        knownIds: new Set(Array.isArray(legacySeen) ? legacySeen.map(normalizedId).filter(Boolean) : []),
        unreadIds: new Set(),
      };
    } catch (_error) {
      return { initialized: false, lastObservedAt: 0, knownIds: new Set(), unreadIds: new Set() };
    }
  }

  persist() {
    try {
      this.storage?.setItem(this.key, JSON.stringify({
        version: 2,
        initialized: this.state.initialized,
        lastObservedAt: this.state.lastObservedAt,
        knownIds: [...this.state.knownIds].slice(-1000),
        unreadIds: [...this.state.unreadIds].slice(-500),
      }));
    } catch (_error) {
      // Notifications still work in memory when browser storage is unavailable.
    }
  }

  observe(jobs = []) {
    const terminalJobs = jobs.filter(isTerminal);
    const observedAt = Date.now();
    if (!this.state.initialized) {
      for (const job of terminalJobs) {
        const id = normalizedId(job.id);
        if (id) this.state.knownIds.add(id);
      }
      this.state.initialized = true;
      this.state.lastObservedAt = observedAt;
      this.persist();
      return this.unreadIds;
    }

    for (const job of terminalJobs) {
      const id = normalizedId(job.id);
      if (!id || this.state.knownIds.has(id)) continue;
      this.state.knownIds.add(id);
      if (timestamp(job.updated_at ?? job.created_at) >= this.state.lastObservedAt) {
        this.state.unreadIds.add(id);
      }
    }
    this.state.lastObservedAt = Math.max(this.state.lastObservedAt, observedAt);
    this.persist();
    return this.unreadIds;
  }

  markUnread(jobId) {
    const id = normalizedId(jobId);
    if (!id || this.state.knownIds.has(id)) return false;
    this.state.knownIds.add(id);
    this.state.unreadIds.add(id);
    this.state.initialized = true;
    this.state.lastObservedAt = Math.max(this.state.lastObservedAt, Date.now());
    this.persist();
    return true;
  }

  acknowledge(jobIds = []) {
    for (const jobId of jobIds) this.state.unreadIds.delete(normalizedId(jobId));
    this.persist();
  }

  get unreadIds() {
    return this.state.unreadIds;
  }
}
