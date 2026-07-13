export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function round(value, decimals = 2) {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function seededPick(items, index) {
  return items[index % items.length];
}

export class AgentNetwork {
  constructor(scenario) {
    this.scenario = scenario;
    this.time = 0;
    this.messageCounter = 0;
    this.eventCounter = 0;
    this.intentCounter = 0;
    this.autopilotClock = 2.4;
    this.messages = [];
    this.scheduled = [];
    this.events = [];

    this.agentMap = new Map(
      scenario.agents.map((agent) => [
        agent.id,
        {
          ...agent,
          position: { ...agent.position },
          runtime: {
            load: agent.runtime?.load ?? 0.22,
            inbox: 0,
            outbox: 0,
            status: agent.runtime?.status ?? "idle",
            lastProtocol: null,
          },
        },
      ])
    );

    this.relationMap = new Map(
      scenario.relations.map((relation) => [
        relation.id,
        {
          latency: 1,
          trust: 0.7,
          bandwidth: 1,
          bidirectional: true,
          ...relation,
        },
      ])
    );

    this.protocolMap = new Map(scenario.protocols.map((protocol) => [protocol.id, protocol]));
    this.log("Scenario agenti caricato.");
  }

  get agents() {
    return [...this.agentMap.values()];
  }

  get relations() {
    return [...this.relationMap.values()];
  }

  get protocols() {
    return [...this.protocolMap.values()];
  }

  getAgent(id) {
    return this.agentMap.get(id);
  }

  getRelation(id) {
    return this.relationMap.get(id);
  }

  getProtocol(id) {
    return this.protocolMap.get(id);
  }

  registerAgent(agent) {
    if (this.agentMap.has(agent.id)) {
      return this.agentMap.get(agent.id);
    }
    const registered = {
      reliability: 0.82,
      capabilities: [],
      ...agent,
      position: { ...(agent.position ?? { x: 0.5, y: 0.5 }) },
      runtime: {
        load: agent.runtime?.load ?? 0.08,
        inbox: agent.runtime?.inbox ?? 0,
        outbox: agent.runtime?.outbox ?? 0,
        status: agent.runtime?.status ?? "idle",
        lastProtocol: agent.runtime?.lastProtocol ?? null,
      },
    };
    this.agentMap.set(registered.id, registered);
    this.log(`${registered.label} joined the runtime.`);
    return registered;
  }

  registerRelation(relation) {
    if (this.relationMap.has(relation.id)) {
      return this.relationMap.get(relation.id);
    }
    const registered = {
      latency: 0.8,
      trust: 0.8,
      bandwidth: 2,
      bidirectional: true,
      ...relation,
    };
    this.relationMap.set(registered.id, registered);
    return registered;
  }

  moveAgent(id, position) {
    const agent = this.getAgent(id);
    if (!agent) {
      return;
    }
    agent.position.x = clamp(position.x, 0.05, 0.95);
    agent.position.y = clamp(position.y, 0.08, 0.92);
  }

  registerProtocol(protocol) {
    this.protocolMap.set(protocol.id, protocol);
    this.log(`Protocollo registrato: ${protocol.label}.`);
  }

  triggerIntent(intentId) {
    const recipe = this.scenario.intents[intentId];
    if (!recipe) {
      this.log(`Intent sconosciuto: ${intentId}.`);
      return;
    }

    this.intentCounter += 1;
    const payload = this.buildIntentPayload(recipe);
    for (const message of recipe.messages) {
      const recipients = this.resolveRecipients(message);
      for (const recipient of recipients) {
        this.enqueue({
          from: message.from,
          to: recipient,
          protocolId: message.protocolId,
          type: message.type,
          payload,
          priority: message.priority ?? recipe.priority ?? 2,
        });
      }
    }
  }

  tick(deltaSeconds) {
    const delta = Math.min(deltaSeconds, 0.16);
    this.time += delta;

    this.autopilotClock -= delta;
    if (this.autopilotClock <= 0) {
      const intent = seededPick(["task", "schedule", "memory-sync", "review"], this.intentCounter);
      this.triggerIntent(intent);
      this.autopilotClock = 3.4 + (this.intentCounter % 3) * 0.8;
    }

    for (const agent of this.agents) {
      agent.runtime.load = clamp(agent.runtime.load - delta * 0.035, 0.08, 1);
    }

    this.deliverScheduled();
    this.advanceMessages(delta);
  }

  resolveRecipients(messageRecipe) {
    if (messageRecipe.to === "capability") {
      return this.agents
        .filter((agent) => agent.capabilities.includes(messageRecipe.capability))
        .map((agent) => agent.id);
    }
    if (messageRecipe.to === "all-connected") {
      return this.relations
        .filter((relation) => relation.from === messageRecipe.from || relation.to === messageRecipe.from)
        .map((relation) => (relation.from === messageRecipe.from ? relation.to : relation.from));
    }
    return Array.isArray(messageRecipe.to) ? messageRecipe.to : [messageRecipe.to];
  }

  buildIntentPayload(recipe) {
    const item = seededPick(recipe.payloads, this.intentCounter);
    return {
      ...item,
      intentId: recipe.id,
      run: this.intentCounter,
      createdAt: round(this.time),
    };
  }

  enqueue(messageInput) {
    const from = this.getAgent(messageInput.from);
    const to = this.getAgent(messageInput.to);
    const protocol = this.getProtocol(messageInput.protocolId);
    if (!from || !to || !protocol) {
      return null;
    }

    const relation = this.findRelation(from.id, to.id, protocol.id);
    if (!relation) {
      this.log(`Nessun canale ${from.label} -> ${to.label} per ${protocol.label}.`);
      return null;
    }

    const messageType = protocol.messageTypes[messageInput.type];
    if (!messageType) {
      this.log(`Tipo messaggio non valido: ${messageInput.type}.`);
      return null;
    }

    this.messageCounter += 1;
    from.runtime.outbox += 1;
    from.runtime.load = clamp(from.runtime.load + 0.055, 0, 1);
    from.runtime.status = `invio ${messageType.shortLabel}`;
    from.runtime.lastProtocol = protocol.id;

    const priority = messageInput.priority ?? messageType.priority ?? 2;
    const message = {
      id: `msg-${this.messageCounter}`,
      from: from.id,
      to: to.id,
      protocolId: protocol.id,
      relationId: relation.id,
      type: messageInput.type,
      payload: messageInput.payload ?? {},
      external: messageInput.external ?? false,
      color: messageType.color ?? protocol.color,
      priority,
      progress: 0,
      elapsed: 0,
      duration: clamp(relation.latency * (1.25 - priority * 0.11), 0.28, 4.2),
    };

    this.messages.push(message);
    this.log(`${from.label} -> ${to.label}: ${messageType.label}.`);
    return message;
  }

  schedule(delaySeconds, messageInput) {
    this.scheduled.push({
      dueAt: this.time + delaySeconds,
      messageInput,
    });
  }

  deliverScheduled() {
    const ready = this.scheduled.filter((item) => item.dueAt <= this.time);
    this.scheduled = this.scheduled.filter((item) => item.dueAt > this.time);
    for (const item of ready) {
      this.enqueue(item.messageInput);
    }
  }

  advanceMessages(delta) {
    const delivered = [];
    for (const message of this.messages) {
      message.elapsed += delta;
      message.progress = clamp(message.elapsed / message.duration, 0, 1);
      if (message.progress >= 1) {
        delivered.push(message);
      }
    }

    if (delivered.length === 0) {
      return;
    }

    this.messages = this.messages.filter((message) => !delivered.includes(message));
    for (const message of delivered) {
      this.deliver(message);
    }
  }

  deliver(message) {
    const recipient = this.getAgent(message.to);
    const protocol = this.getProtocol(message.protocolId);
    const messageType = protocol.messageTypes[message.type];
    recipient.runtime.inbox += 1;
    recipient.runtime.load = clamp(recipient.runtime.load + 0.08 + message.priority * 0.02, 0, 1);
    recipient.runtime.status = `ricevuto ${messageType.shortLabel}`;
    recipient.runtime.lastProtocol = protocol.id;

    if (!message.external) {
      this.applyProtocolRules(protocol, message, recipient);
    }
  }

  applyProtocolRules(protocol, message, recipient) {
    for (const rule of protocol.rules ?? []) {
      if (rule.on !== message.type) {
        continue;
      }
      if (rule.requiresCapability && !recipient.capabilities.includes(message.payload.capability)) {
        continue;
      }
      if (rule.recipientRole && recipient.role !== rule.recipientRole) {
        continue;
      }

      const delay = Array.isArray(rule.delay)
        ? rule.delay[0] + ((this.messageCounter + this.eventCounter) % 5) * ((rule.delay[1] - rule.delay[0]) / 4)
        : rule.delay ?? 0.35;

      const nextPayload = {
        ...message.payload,
        previousType: message.type,
        responder: recipient.id,
        confidence: rule.addConfidence ? round(0.62 + recipient.reliability * 0.3, 2) : undefined,
      };

      const targets = rule.to === "sender" ? [message.from] : this.resolveRuleTargets(rule, recipient);
      for (const target of targets) {
        this.schedule(delay, {
          from: recipient.id,
          to: target,
          protocolId: rule.protocolId ?? protocol.id,
          type: rule.type,
          payload: nextPayload,
          priority: rule.priority,
        });
      }
    }
  }

  resolveRuleTargets(rule, recipient) {
    if (rule.to === "capability") {
      return this.agents
        .filter((agent) => agent.id !== recipient.id && agent.capabilities.includes(rule.capability))
        .map((agent) => agent.id);
    }
    if (rule.to === "all-connected") {
      return this.relations
        .filter((relation) => relation.from === recipient.id || relation.to === recipient.id)
        .map((relation) => (relation.from === recipient.id ? relation.to : relation.from));
    }
    return Array.isArray(rule.to) ? rule.to : [rule.to];
  }

  findRelation(fromId, toId, protocolId) {
    return this.relations.find((relation) => {
      const sameProtocol = relation.protocolId === protocolId;
      const forward = relation.from === fromId && relation.to === toId;
      const backward = relation.bidirectional && relation.from === toId && relation.to === fromId;
      return sameProtocol && (forward || backward);
    });
  }

  log(text) {
    this.eventCounter += 1;
    this.events.unshift({
      id: `event-${this.eventCounter}`,
      timeLabel: formatTime(this.time),
      text,
    });
    this.events = this.events.slice(0, 80);
  }
}
