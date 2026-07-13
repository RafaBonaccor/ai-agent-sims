# Agent Protocol Lab

Questa applicazione combina un runtime agenti nativo in Python con una visualizzazione 3D di agenti, task e messaggi di protocollo. La stanza Three.js e un control plane: mostra eventi prodotti dal runtime, ma non decide il comportamento degli agenti.

## Struttura

- `index.html`: shell dell'app, controlli, inspector e log.
- `styles.css`: interfaccia operativa responsive.
- `app.mjs`: renderer Three.js, camera isometrica, selezione, HUD e comunicazioni animate.
- `src/agentWorld.mjs`: stato del mondo di gioco, griglia di blocchi, stanze, postazioni, pathfinding, target manuali e lavori degli agenti.
- `src/scenarios.mjs`: scenario modificabile con agenti, relazioni, protocolli e intenti.
- `src/agentProtocol.mjs`: motore logico di messaggistica, scheduling e regole di protocollo.
- `src/runtimeClient.mjs`: client REST/WebSocket del runtime nativo.
- `agent_runtime/models.py`: contratti validati per agenti, task, messaggi ed eventi.
- `agent_runtime/engine.py`: state machine, routing e ciclo di esecuzione.
- `agent_runtime/execution.py`: provider model, tool registry e tool loop.
- `agent_runtime/browser_control.py`: session manager ibrido per browser live.
- `agent_runtime/protocols.py`: tipi messaggio e transizioni ammesse.
- `agent_runtime/storage.py`: persistenza SQLite di agenti, task ed event log.
- `agent_runtime/scheduler.py`: primitive condivise per `at`, `cron`, repeat giornaliero/weekday e runner async.
- `agent_runtime/server.py`: API FastAPI, WebSocket e hosting del frontend.
- `agent_runtime/discord_gateway.py`: bot Discord opzionale per creare task chat verso gli agenti.
- `agent_runtime/briefings.py`: scheduler del briefing mattutino AI come task agentico standard.
- `config/agents.json`: definizioni degli agenti iniziali.

## Runtime nativo

Il flusso principale e:

```text
Browser 3D -> REST (comandi) -> AgentRuntime
Browser 3D <- WebSocket (eventi) <- AgentRuntime
Discord -> slash command -> DiscordGateway -> AgentRuntime
Discord <- risposta canale <- DiscordGateway <- RuntimeEvent
AgentRuntime -> RuntimeStore -> SQLite
Scheduler -> TaskCreate(channel=chat) -> AgentRuntime
```

Il personaggio `Scheduler` e un agente decisionale: interpreta richieste di
orario, propone timestamp/cron/follow-up e coordina con orchestrator/memory. Non
esegue timer direttamente; i timer reali restano in `agent_runtime/scheduler.py`.

Il layout della casa e modificabile dal frontend: stanze, tavoli e posizioni
agenti vengono salvati in `localStorage`. Questo non cambia la definizione
runtime degli agenti in SQLite; cambia solo la rappresentazione spaziale del
gioco. Anche il tema `dark`/`white` e locale al browser: aggiorna UI e palette
Three.js senza cambiare dati runtime.

Gli stati agente sono `idle`, `receiving`, `planning`, `executing`, `waiting`,
`verifying`, `blocked`, `failed` e `stopped`.

Il task contract applica la sequenza:

```text
created -> announced -> awarded -> accepted -> running -> verifying -> completed
```

Le transizioni non dichiarate vengono rifiutate. Il runtime attuale usa un executor simulato, intenzionalmente separato dal protocollo: un provider LLM o un tool executor reale potra sostituirlo senza modificare UI, persistenza o state machine.

## API

- `GET /api/health`: stato runtime.
- `GET|POST /api/agents`: elenco e creazione agenti.
- `PUT /api/agents/{id}`: modifica completa della configurazione agente.
- `GET|PUT /api/agents/{id}/memory`: memoria privata persistente.
- `GET|POST /api/tasks`: elenco e avvio task.
- `GET /api/events`: event log persistente.
- `GET /api/briefings/ai-news`: stato briefing mattutino AI.
- `POST /api/briefings/ai-news/run`: crea manualmente il task briefing AI.
- `GET /api/tools`: catalogo tool registrati e livello di rischio.
- `GET /api/browser/sessions`: elenco sessioni browser live.
- `POST /api/browser/sessions`: apertura sessione via backend `botasaurus` o `mock`.
- `POST /api/browser/sessions/{id}/commands`: comando live (`goto`, `extract`, `type`, ecc.).
- `DELETE /api/browser/sessions/{id}`: chiusura sessione.
- `GET /api/protocols`: protocolli e message type ammessi.
- `WS /ws/events`: snapshot iniziale ed eventi live.

## Gateway Discord

`DiscordGateway` e un adapter opzionale avviato dal lifespan FastAPI solo quando
`AGENT_LAB_DISCORD_TOKEN` e presente. Il gateway non introduce un secondo runtime:
crea normali `TaskCreate(channel="chat")` con `requested_agent_id` impostato
sull'agente scelto e resta in ascolto degli stessi `RuntimeEvent` usati dal
frontend.

Comandi supportati:

- `/agents`: lista agenti runtime.
- `/ask agent:<id> prompt:<testo>`: crea un task chat per l'agente.
- `/use agent:<id>`: imposta un default in memoria per quel canale Discord.

Il supporto ai messaggi prefissati (`!agents`, `!use`, `!ask`) e disabilitato di
default per evitare di richiedere il Message Content Intent. Si abilita con
`AGENT_LAB_DISCORD_MESSAGE_CONTENT=1`.

## Scheduler runtime

La logica di scheduling e centralizzata in `agent_runtime/scheduler.py`.
Project Gateway e briefing agentici usano lo stesso calcolo per:

- `immediate`, `at`, `cron`;
- normalizzazione timezone UTC per esecuzione interna;
- repeat `daily` e `weekdays`;
- runner async cancellabile durante shutdown.

Il briefing AI non e un percorso speciale: lo scheduler crea un normale
`TaskCreate(channel="chat", requested_agent_id="ai-news-navigator")`, quindi
provider, memoria, wiki, Web search e error handling restano quelli del runtime.
L'agente `Scheduler` puo preparare o revisionare questi schedule, ma la
registrazione temporale rimane una responsabilita runtime.

## Provider e tool

Ogni agente sceglie un provider indipendente:

- `simulated`: executor deterministico locale usato per sviluppo e test.
- `openai-compatible`: endpoint Chat Completions configurabile per agente.

La chiave API non viene salvata negli agent document o nel database runtime. La
configurazione puo usare una variabile d'ambiente, per esempio `MODEL_API_KEY`,
oppure lo secret store locale: macOS Keychain su macOS, Windows DPAPI su Windows.
`data/secrets.json` contiene solo riferimenti/metadati dello store.

Il tool registry nativo espone inizialmente:

- `runtime_time` (`runtime`): lettura ora UTC.
- `task_context` (`tasks`): lettura task assegnato.
- `memory_read` (`memory`): lettura memoria privata agente.
- `memory_append` (`memory`): aggiunta di un fatto durevole.
- `browser_open` (`browser`): apre una sessione live tramite Botasaurus o mock test.
- `browser_current_url` (`browser`): legge l'URL corrente.
- `browser_goto` (`browser`): naviga a un URL.
- `browser_click_text` / `browser_click_selector` (`browser`): interagiscono con la pagina.
- `browser_type` (`browser`): compila un campo.
- `browser_extract` / `browser_snapshot` (`browser`): estraggono contesto dalla pagina.
- `browser_close` (`browser`): chiude la sessione.

Il provider vede solo tool appartenenti ai toolset abilitati per l'agente. Prima
dell'esecuzione il runtime controlla anche il risk level contro la approval policy.
Toolset come `web`, `files` e `terminal` sono configurabili separatamente dai
tool browser. Il browser live non sostituisce il Project Gateway: per sorgenti
note conviene usare le azioni batch dello scraper, mentre il browser live serve
per login, ispezione, recupero contesto e fallback interattivo.

## Browser Control

Il controllo browser e ibrido:

```text
Agent tool loop
  -> ToolRegistry (`browser_*`)
    -> BrowserControl
      -> backend mock per test
      -> backend botasaurus via integrations/main-scraper/botasaurus_bridge.py
```

Il bridge Botasaurus parla JSONL su stdin/stdout. Il runtime mantiene la sessione
viva finche l'agente non chiama `browser_close` o finche il runtime non termina.
Questa scelta mantiene indipendente The Main Scraper: il batch scraper resta nel
submodule, mentre il contratto live vive nell'integrazione.

Rischi:

- `browser-read`: navigazione/lettura pagina.
- `browser-write`: click, typing e close; puo essere inserito nella approval
  policy di un agente se vuoi bloccare azioni interattive prima di approvarle.

## Configurazione oggetti

Seleziona qualsiasi agente 3D e premi `Configure`. Il pannello permette di vedere
e modificare identita, ruolo, istruzioni, capacita, protocolli, provider, modello,
toolset, budget, approval policy e memoria privata. Le modifiche vengono persistite
e pubblicate live come `agent.updated` e `memory.updated`.

## Modello logico

Un agente ha identita, ruolo, capacita, posizione 2D e stato runtime. Una relazione collega due agenti e dichiara protocollo, latenza, fiducia, banda e direzionalita.

Un protocollo e composto da:

- `messageTypes`: tipi ammessi e priorita visiva/logica.
- `rules`: reazioni dichiarative quando un messaggio viene consegnato.
- `color` e `label`: metadati usati dal renderer.

Un intento e un comando alto livello che genera uno o piu messaggi iniziali. La simulazione include gia:

- `task`: contratto task/proposta/assegnazione/stato.
- `memory-sync`: scrittura e broadcast dello stato condiviso.
- `review`: richiesta review, finding e patch.

## Mondo 3D

`src/agentWorld.mjs` mappa gli agenti logici su comportamenti visibili:

- ogni ruolo ha una postazione naturale;
- ogni cambio di stato runtime puo spostare un agente verso una postazione;
- ogni agente ha una tile corrente, una tile destinazione, un path a blocchi, un lavoro corrente, una fase di camminata e una bolla di stato;
- il click manuale su un blocco assegna una destinazione all'agente selezionato e sospende temporaneamente l'automazione;
- i messaggi del protocollo vengono renderizzati in `app.mjs` come archi luminosi tra le posizioni correnti degli agenti.

## Estensione

Per aggiungere un agente durante l'esecuzione, usa il pulsante `+ Agent`. Il runtime valida la definizione, la salva in SQLite e pubblica `agent.created`; il frontend crea immediatamente il personaggio e il canale verso l'orchestrator.

Gli agenti iniziali sono in `config/agents.json` e vengono importati solo quando il database e vuoto. Per aggiungere un protocollo runtime, registra tipi messaggio e transizioni in `agent_runtime/protocols.py`. `src/scenarios.mjs` resta il fallback demo quando il backend non e disponibile.

Le regole supportano destinatari flessibili:

- `sender`: risponde a chi ha inviato il messaggio.
- `all-connected`: invia a tutti gli agenti collegati.
- `capability`: invia agli agenti che espongono una capacita.

## Prossimi step

- Adapter sandbox per tool web, file e terminal.
- Approval queue interattiva per operazioni bloccate.
- Skill procedurali a caricamento progressivo.
- Delegazione con contesti isolati e budget per child agent.
- Timeline ispezionabile con replay e filtri per protocollo.
- Sandbox tool, rate limit e cancellazione task.
