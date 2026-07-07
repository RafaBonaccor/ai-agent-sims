# Agent Protocol Lab 3D

Prototype 3D per visualizzare una rete di agenti AI come una piccola simulazione di gioco: gli agenti stanno su blocchi, camminano cella per cella tra postazioni, lavorano, ricevono task e comunicano con messaggi animati.

La demo browser usa Three.js via CDN e il motore logico locale in `src/`. Puoi selezionare agenti e postazioni, ruotare la camera, osservare i messaggi in transito e attivare intenti come task, sync memoria e review.

Il runtime Python gestisce agenti dinamici, task, protocolli tipizzati, state machine,
eventi live e persistenza SQLite. Ogni agente puo usare il simulatore locale oppure
un endpoint OpenAI-compatible e dispone di configurazione, toolset, budget, policy
e memoria privata modificabili dall'interfaccia.

## Run

Su macOS fai doppio clic su:

```text
run.command
```

Su Windows fai doppio clic su:

```powershell
.\run.bat
```

Al primo avvio, il launcher crea `.venv`, installa `requirements.txt`, apre il
browser e avvia il runtime agenti locale con API REST e WebSocket.

Oppure avvia manualmente il runtime dalla root del progetto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m agent_runtime.server
```

Poi apri:

```text
http://localhost:8000
```

## File principali

- `index.html`: UI dell'app.
- `app.mjs`: rendering Three.js, camera, blocchi cliccabili, interazioni e animazioni 3D.
- `src/agentProtocol.mjs`: motore logico agenti/protocolli.
- `src/agentWorld.mjs`: mondo di gioco a griglia con stanza, postazioni, path tile-by-tile e lavori.
- `src/scenarios.mjs`: scenario modificabile.
- `agent_runtime/`: runtime Python, API, protocolli, state machine e persistenza.
- `config/agents.json`: agenti iniziali modificabili.
- `config/projects.json`: registro dei progetti esterni disponibili agli agenti.
- `integrations/`: manifest, permessi e adapter dei progetti esterni.
- `projects/main-scraper`: The Main Scraper, mantenuto come Git submodule.
- `data/runtime.db`: stato persistente SQLite creato al primo avvio.
- `AGENT_PROTOCOL.md`: note architetturali ed estensione.

## Progetti esterni

I progetti controllabili dagli agenti sono registrati in `config/projects.json`.
Il loro codice vive in `projects/`, mentre la configurazione specifica del gioco
resta in `integrations/`. Dopo un clone inizializza i submodule con:

```powershell
git submodule update --init --recursive
```

The Main Scraper espone solo le azioni dichiarate in
`integrations/main-scraper/adapter.json`. Le azioni che preparano o inviano
contatti richiedono approvazione esplicita.

I percorsi dipendenti dalla macchina, incluso l'interprete Python dello scraper,
sono configurati in `config/projects.local.json`, escluso da Git.

Dal gioco clicca un agente, premi `Dai un lavoro`, poi `Progetti`; scegli l'azione
dello scraper e compilane i parametri.
Il runtime avvia la CLI in background e mostra risultato o errore nel dialogo; lo
stato dell'agente selezionato passa a `executing` durante il job. Le azioni di
contatto richiedono una conferma esplicita prima dell'avvio.

Le richieste HTTP, gli errori frontend e il ciclo dei job vengono salvati in
`runtime/agent-lab.log`, con rotazione automatica. Gli ultimi eventi sono disponibili
anche da `GET /api/diagnostics/logs`; i valori dei parametri non vengono loggati.

L'azione predefinita `Apri interfaccia scraper` avvia la GUI desktop come processo
separato. `Controlla configurazione` esegue invece soltanto il comando CLI `status`.

## Controlli

- Clicca un agente per ispezionarlo.
- Premi `Configure` per modificare tutte le impostazioni e la memoria dell'agente selezionato.
- Premi `+ Agent` per creare e persistere un nuovo agente.
- Clicca un blocco libero per muovere manualmente l'agente selezionato.
- Trascina sul pavimento per spostare la camera.
- Usa la rotella del mouse per lo zoom.
- Usa `Q` / `E` o i pulsanti camera per ruotare.
- Usa `Auto` / `Manuale` per abilitare o bloccare gli spostamenti automatici.
- Usa `Task`, `Memoria`, `Review` per generare lavoro e comunicazioni.
- Usa `Pausa` e `1x/2x/4x` per controllare la simulazione.

## Prestazioni

Le impostazioni leggere sono in `app.mjs`, costante `PERFORMANCE`:

- `maxFps`: frame cap, ora 45 FPS.
- `maxPixelRatio`: risoluzione interna massima, ora 1.5.
- `shadows`: ombre dinamiche, ora attivate.
- `fog`: nebbia shader, ora attivata.

## Java Port

La precedente sandbox Java2D/voxel resta in `java/`.

- source: `java/src/blockforge`
- build and run steps: `java/README.md`
