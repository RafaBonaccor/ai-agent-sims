# Agent Protocol Lab 3D

Prototype 3D per visualizzare una rete di agenti AI come una piccola simulazione di gioco: gli agenti stanno su blocchi, camminano cella per cella tra postazioni, lavorano, ricevono task e comunicano con messaggi animati.

La demo browser usa Three.js via CDN e il motore logico locale in `src/`. Puoi selezionare agenti e postazioni, ruotare la camera, osservare i messaggi in transito e attivare intenti come task, sync memoria e review.

Il runtime Python gestisce agenti dinamici, task, protocolli tipizzati, state machine,
eventi live e persistenza SQLite. Ogni agente puo usare il simulatore locale oppure
un endpoint OpenAI-compatible e dispone di configurazione, toolset, budget, policy
e memoria privata modificabili dall'interfaccia.

Le API key dei provider possono essere configurate per tutto il progetto oppure
solo per un agente. Su macOS vengono salvate in Keychain; su Windows usano DPAPI.
`data/secrets.json` resta escluso da Git e contiene solo metadati/riferimenti, non
le chiavi in chiaro; il browser riceve solamente lo stato configurata/non
configurata. Le chiavi devono avere almeno 8 caratteri; gli errori di validazione
vengono mostrati nel frontend con campo e messaggio leggibili. Un errore `HTTP
401` durante la chat indica che il provider ha rifiutato la key configurata:
controlla scope progetto/agente, provider selezionato e modello.

Provider disponibili: simulatore nativo, OpenAI Responses API, endpoint
OpenAI-compatible, Anthropic Messages API, Google Gemini e Ollama locale. Il
function calling degli strumenti agentici e attualmente disponibile tramite il
provider OpenAI-compatible; gli altri adapter eseguono task testuali.

Gli agenti con provider `OpenAI` e toolset `web` possono usare il tool hosted
`web_search` della Responses API. Fonti e citazioni vengono normalizzate nel
risultato del task e mostrate come link cliccabili nella chat dell'agente.

La chat rapida e persistente per agente: ogni messaggio viene salvato come task con
canale `chat`, mentre risposte, errori e fonti sono ricostruiti da SQLite quando il
popup viene riaperto. Le conversazioni di agenti diversi restano separate.
Se l'agente usa il provider `simulated`, la chat non chiama Codex o API esterne:
mostra un fallback deterministico che spiega di configurare un provider reale
quando vuoi risposte generative.

## Run

Su macOS fai doppio clic su:

```text
run.command
```

Su Windows fai doppio clic su:

```powershell
.\run.bat
```

Al primo avvio su macOS, il launcher esegue `scripts/setup_macos.sh`: prepara
`.venv`, inizializza The Main Scraper, crea `projects/main-scraper/.venv`,
installa Botasaurus, aggiorna `config/projects.local.json`, apre il browser e
avvia il runtime agenti locale con API REST e WebSocket.

Opzioni utili da terminale:

```bash
./run.command --no-browser
./run.command --skip-install
./run.command --skip-setup
AGENT_LAB_PORT=8010 ./run.command --no-browser
```

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

## Setup macOS completo

Per preparare runtime, submodule The Main Scraper, venv dedicato dello scraper e
`config/projects.local.json` in un solo passaggio:

```bash
scripts/setup_macos.sh
```

Prerequisiti macOS consigliati:

```bash
brew install python@3.12 python-tk@3.12
```

Lo script crea:

- `.venv` per il runtime principale;
- `projects/main-scraper/.venv` per Botasaurus e le dipendenze dello scraper;
- `config/projects.local.json` con `main-scraper.pythonExecutable` puntato al
  Python dello scraper.

Se vuoi solo creare venv/config senza installare pacchetti via rete:

```bash
scripts/setup_macos.sh --skip-install
```

Le dipendenze dello scraper usate dal setup sono in
`integrations/main-scraper/requirements.txt`.

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
- `agent_runtime/browser_control.py`: manager ibrido per sessioni browser live.
- `integrations/main-scraper/botasaurus_bridge.py`: bridge JSONL che espone Botasaurus agli agenti.
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
sono configurati in `config/projects.local.json`, escluso da Git. Usa
`config/projects.local.example.json` come template.

Dal gioco clicca un agente, premi `Dai un lavoro`, poi `Progetti`; scegli l'azione
dello scraper e compilane i parametri.
Il runtime avvia la CLI in background e mostra risultato o errore nel dialogo; lo
stato dell'agente selezionato passa a `executing` durante il job. Le azioni di
contatto richiedono una conferma esplicita prima dell'avvio.

Le configurazioni ricorrenti possono essere salvate come preset dal Project Gateway.
Un preset conserva progetto, azione e parametri in SQLite; le approvazioni delle
azioni rischiose non vengono memorizzate e devono essere confermate a ogni avvio.

Le richieste HTTP, gli errori frontend e il ciclo dei job vengono salvati in
`runtime/agent-lab.log`, con rotazione automatica. Gli ultimi eventi sono disponibili
anche da `GET /api/diagnostics/logs`; i valori dei parametri non vengono loggati.

L'azione predefinita `Apri interfaccia scraper` avvia la GUI desktop come processo
separato. `Controlla configurazione` esegue invece soltanto il comando CLI `status`.

## Browser ibrido: scraper batch + controllo live

Il sistema ora distingue due superfici:

- **Project Gateway batch**: lancia azioni complete di The Main Scraper, per esempio
  `google_maps.search`, `vinted.search` o `subito.contact.prepare`, e legge il JSON
  finale dalla CLI.
- **Browser Control live**: apre una sessione browser persistente e permette agli
  agenti con toolset `browser` di eseguire step granulari come `browser_goto`,
  `browser_click_text`, `browser_type`, `browser_extract`, `browser_snapshot` e
  `browser_close`.

Il backend reale e `botasaurus`: il runtime avvia
`integrations/main-scraper/botasaurus_bridge.py` come processo JSONL dentro
`projects/main-scraper`, riusando la stessa logica profili di The Main Scraper
(`sessione_persistente`, `chrome_normale`, `profilo_personalizzato`, `isolated`).

Per test automatici esiste anche il backend `mock`, che implementa lo stesso
contratto senza aprire Chrome. Questo evita test fragili e permette di validare
end-to-end il loop modello -> tool -> sessione browser.

Endpoint runtime:

- `GET /api/browser/sessions`: sessioni live.
- `POST /api/browser/sessions`: apre una sessione.
- `POST /api/browser/sessions/{id}/commands`: invia un comando JSONL.
- `DELETE /api/browser/sessions/{id}`: chiude una sessione.

Per usare Botasaurus davvero su macOS serve un ambiente Python del submodule con
`botasaurus` installato e Chrome disponibile. Se l'interprete non e configurato in
`config/projects.local.json`, il runtime prova i venv del progetto e poi
l'interprete del runtime corrente. Copia `config/projects.local.example.json` in
`config/projects.local.json` e aggiorna `pythonExecutable` con il venv dello
scraper quando vuoi avviare sessioni Botasaurus reali.

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
