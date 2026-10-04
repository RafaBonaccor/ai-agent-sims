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

`AI News Navigator` e l'agente dedicato alla navigazione web. Usa provider
`OpenAI`, toolset `web`/`browser` e istruzioni focalizzate su fonti recenti,
citazioni e distinzione tra fatti, rumor e analisi.

`Scheduler` e l'agente dedicato alla pianificazione temporale. Nel gioco appare
alla postazione `Schedule Desk`; nella UI puoi premere `Schedule` per chiedergli
di proporre orari, cron e follow-up. L'agente decide e spiega lo schedule, mentre
il timer effettivo resta nel runtime nativo.

## Indice

- [Visione](#visione)
- [Architettura](#architettura)
- [Run](#run)
- [Setup macOS completo](#setup-macos-completo)
- [Layout del gioco](#layout-del-gioco)
- [Agenti e provider](#agenti-e-provider)
- [Shared LLM Wiki Memory](#shared-llm-wiki-memory)
- [RecursiveMAS-style collaboration](#recursivemas-style-collaboration)
- [Integrazione Discord](#integrazione-discord)
- [Progetti esterni](#progetti-esterni)
- [The Main Scraper](#the-main-scraper)
- [Browser ibrido](#browser-ibrido-scraper-batch--controllo-live)
- [Vast.ai e ComfyUI media generation](#vastai-e-comfyui-media-generation)
- [File principali](#file-principali)
- [Controlli](#controlli)

## Visione

Agent Protocol Lab e un control plane visuale per agenti AI. L'obiettivo non e
soltanto avere una chat con piu personaggi, ma rendere osservabile il lavoro
agentico: chi prende un task, quale provider usa, quali strumenti invoca, dove
finiscono i risultati, come la memoria viene aggiornata e quando serve intervento
umano.

Il gioco 3D e quindi la superficie operativa del sistema:

- gli agenti sono oggetti persistenti, configurabili e osservabili;
- le workstation rappresentano ruoli e responsabilita;
- il Project Gateway collega gli agenti a software reali come The Main Scraper;
- la memoria wiki trasforma conversazioni e task in conoscenza revisionabile;
- Discord permette di usare gli stessi agenti da fuori l'interfaccia 3D.

La direzione architetturale e Hermes-like: agenti specializzati, routing
multilingua, memoria condivisa, strumenti espliciti, job esterni e comunicazione
visibile tra agenti. Il progetto non incorpora Hermes, ma ne prende ispirazione
per costruire un runtime controllabile e modificabile localmente.

## Architettura

Il sistema e composto da quattro livelli principali.

| Livello | Responsabilita | File principali |
| --- | --- | --- |
| Frontend 3D | scena, agenti, stanze, popup, notifiche, Project Gateway UI | `index.html`, `app.mjs`, `styles.css`, `src/agentWorld.mjs` |
| Runtime API | FastAPI, WebSocket, lifecycle agenti, task, settings, secrets | `agent_runtime/server.py`, `agent_runtime/engine.py`, `agent_runtime/storage.py` |
| Execution layer | provider LLM, tool registry, browser tools, memory tools | `agent_runtime/execution.py`, `agent_runtime/router.py`, `agent_runtime/browser_control.py` |
| Integrazioni | scraper, Discord, Codex bridge, ComfyUI/Vast helper | `agent_runtime/project_gateway.py`, `agent_runtime/discord_gateway.py`, `integrations/`, `catalog_server_vast.py` |

Flusso tipico:

```text
UI 3D / Discord
  -> Runtime API
  -> agent/router/provider/tool
  -> Project Gateway o Browser Control
  -> risultato/evento/log
  -> chat agente, notifiche, memoria wiki
```

Gli eventi live passano da WebSocket e vengono usati dal gioco per aggiornare
stato agenti, job, notifiche, chat e output. Lo stato persistente resta in
SQLite, mentre file locali come `config/projects.local.json` e `data/secrets.json`
contengono configurazioni specifiche della macchina.

## Agenti e provider

Gli agenti iniziali sono definiti in `config/agents.json`, ma possono essere
creati e modificati dalla UI. Ogni agente puo avere:

- provider e modello;
- toolset disponibili;
- budget e policy;
- prompt/istruzioni;
- memoria privata;
- workstation nel mondo 3D;
- routing verso altri agenti.

La risoluzione delle API key segue questa precedenza:

1. chiave specifica dell'agente;
2. chiave globale di progetto;
3. variabili ambiente compatibili col provider.

Questo permette di configurare una sola key globale e farla usare anche dagli
agenti che non hanno una chiave dedicata.

## Shared LLM Wiki Memory

The runtime now has a wiki-style shared memory path inspired by the `llm wiki`
pattern. Agent prompts can retrieve relevant markdown sections from
`data/wiki`, while private facts and preferences stay in each agent's SQLite
memory.

Completed non-chat tasks create reviewable markdown proposals in
`data/wiki/proposals`. Each proposal includes the source task, agent, target
page, confidence score, conflict flag and proposed durable knowledge. From the
game UI, click `Sync memory` to open the `Memory` tab, review pending proposals,
then approve or reject them.
If a proposal is marked as conflicting, approval requires an explicit reviewer
reason containing `override conflict`; this prevents accidental promotion of
contradictory project knowledge.

When a proposal is approved, it is archived under
`data/wiki/proposals/reviewed` and appended into its canonical target page, for
example `data/wiki/knowledge-analysis.md`. Rejected proposals are archived only,
so they do not affect future agent prompts.

The same `Memory` tab can browse canonical wiki pages, search reviewed wiki
sections and run maintenance. Maintenance deduplicates repeated sections and
regenerates `data/wiki/index.md`. You can also run it through:

```bash
curl -X POST http://localhost:8000/api/wiki/maintenance/run
```

For long-running sessions, optional scheduled maintenance is available:

```bash
AGENT_LAB_WIKI_MAINTENANCE_INTERVAL_SECONDS=3600 ./run.command --no-browser
```

Retrieval is local and deterministic: it uses section-level TF-IDF-style scoring
with phrase boosts, so it works offline without vector database or embedding API.

## RecursiveMAS-style collaboration

Il paper RecursiveMAS propone una collaborazione ricorsiva tra agenti tramite
stati latenti invece di messaggi testuali. Con API chiuse non abbiamo accesso
agli hidden states dei modelli, quindi il progetto implementa la parte applicabile
come recursive structured collaboration: gli agenti si passano stato strutturato,
non solo chat libera.

La versione pratica per questo runtime e:

- un agente riceve intent e contesto utente;
- il router decide se restare sull'agente corrente, consultare un altro agente o
  delegare un job;
- gli agenti producono state packet con obiettivo, evidenze, incertezze, azioni
  suggerite e riferimenti memoria;
- Memory Core conserva cio che puo diventare conoscenza durevole;
- il gioco mostra messaggi e notifiche quando gli agenti si consultano.

Questa impostazione non replica RecursiveMAS a livello latente, ma ne riprende
la logica utile per il prodotto: collaborazione iterativa, riduzione del testo
inutile, memoria centrale e miglioramento progressivo dello stato di lavoro.

## Layout del gioco

La barra superiore include il pulsante `Editor`. Quando lo premi, la UI passa a
un piccolo pannello di modifica layout:

- `+ Stanza`: aggiunge una nuova stanza in uno spazio libero della griglia.
- `Modella stanza`: modella la stanza selezionata cliccando i quadrati della griglia.
- `Porte`: aggiunge/rimuove celle porta o corridoio tra stanze.
- `+ Workstation`: inserisce una workstation da preset e la collega a un agente.
- `Rimuovi stanza`: elimina la stanza selezionata se e vuota e non e l'ultima.
- `Reset`: resetta il layout salvato e ricarica la scena.
- `White`/`Dark`: cambia tema tra modalita scura e chiara.

Con l'editor aperto, clicca un agente o un tavolo/postazione e poi clicca un tile
di pavimento per spostarlo. Le posizioni di stanze, tavoli e agenti vengono
salvate in `localStorage`, quindi restano dopo un refresh del browser. I task e
gli agenti runtime restano invece persistiti nel backend/SQLite.
Per creare forme tipo editor di The Sims, seleziona una stanza dal pannello
`Stanze`, attiva `Modella stanza` e clicca le celle della griglia per aggiungerle
o rimuoverle. Le stanze restano contigue: una cella nuova deve toccare la stanza
selezionata e una rimozione non puo spezzarla in isole. Le celle non possono
sovrapporsi a un'altra stanza e non puoi rimuovere una cella occupata da agenti
o tavoli.
Con `Porte`, clicca una cella per trasformarla in porta/corridoio: quella cella
diventa attraversabile dagli agenti e puo collegare stanze altrimenti separate.
Il pannello Editor include anche preset di workstation: scegli il tipo di
postazione, scegli l'agente collegato e premi `+ Workstation`. La postazione
viene creata, selezionata e l'app ti chiede di cliccare il tile dove piazzarla.
Quando crei un nuovo agente dal dialog `+ Agent`, scegli anche il preset della
sua workstation; dopo il salvataggio l'Editor si apre automaticamente per
piazzarla nel mondo.
L'inspector mostra anche la sezione `Stanze`: ogni stanza indica quanti agenti
contiene e il pulsante `Porta qui` sposta nella stanza l'agente o la postazione
attualmente selezionata. Questo permette di controllare visivamente dove si
trovano gli agenti senza dover mirare manualmente un tile.
Il tema visuale viene salvato nello stesso browser e aggiorna sia UI che scena
3D: background, fog, pavimento, tile, muri e pannelli. In modalita chiara i log
e gli output restano in testo nero per mantenere leggibilita.

La chat rapida e persistente per agente: ogni messaggio viene salvato come task con
canale `chat`, mentre risposte, errori e fonti sono ricostruiti da SQLite quando il
popup viene riaperto. Le conversazioni di agenti diversi restano separate.
Se l'agente usa il provider `simulated`, la chat non chiama Codex o API esterne:
mostra un fallback deterministico che spiega di configurare un provider reale
quando vuoi risposte generative.
I popup principali sono spostabili: trascina la barra superiore/intestazione di
chat rapida, editor o dialog. Se trascini la chat rapida, resta nella posizione
scelta invece di seguire automaticamente l'agente finche non la riapri.
L'agente browser espone nello stesso popup le sessioni live del Main Scraper e
i comandi browser principali: apri sessione, naviga, leggi URL, fai snapshot,
click text, click selector, type, extract e chiudi sessione.

## Integrazione Discord

Il runtime puo avviare un bot Discord opzionale per parlare con gli agenti dagli
stessi canali Discord. Se `AGENT_LAB_DISCORD_TOKEN` non e configurato,
l'integrazione resta spenta e il runtime continua normalmente.

Installa le dipendenze aggiornate:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Configura il bot:

```bash
export AGENT_LAB_DISCORD_TOKEN="discord-bot-token"
export AGENT_LAB_DISCORD_ALLOWED_GUILDS="123456789012345678"
export AGENT_LAB_DISCORD_DEFAULT_AGENT="researcher"
./run.command --no-browser
```

Invita l'app nel server Discord con gli scope `bot` e `applications.commands`;
assegna al bot permesso di leggere e inviare messaggi nel canale scelto.

Comandi slash disponibili:

- `/agents`: mostra gli agenti disponibili.
- `/ask agent:<id> prompt:<messaggio>`: invia un messaggio chat a un agente.
- `/use agent:<id>`: imposta l'agente predefinito del canale.
- `/codex prompt:<messaggio>`: invia una richiesta al bridge Codex CLI, quando
  configurato.

Il bot pubblica la risposta nello stesso canale quando il task agentico termina.
La risposta passa dallo stesso runtime della UI: provider, memoria, wiki,
toolset, API key e errori sono quelli configurati sull'agente selezionato.

Per usare anche messaggi testuali tipo `!agents`, `!use researcher` e
`!ask researcher ciao`, abilita esplicitamente:

```bash
export AGENT_LAB_DISCORD_MESSAGE_CONTENT=1
```

Questo richiede il Message Content Intent nel Developer Portal Discord. Senza
questa variabile restano attivi gli slash command, che sono il percorso
consigliato.

Comandi testuali principali:

- `!agents`: lista agenti.
- `!use researcher`: imposta agente predefinito del canale.
- `!ask researcher <messaggio>`: parla con un agente specifico.
- `!chat <messaggio>`: parla con l'agente predefinito.
- `!codex <messaggio>`: invia una richiesta al Codex bridge.
- `!codex-model show|set|clear`: legge o modifica il modello usato dal Codex
  bridge per quel canale.
- `!upload` / `!upload-ai-photo`: prepara upload Vinted da foto e testo.
- `!accordi`: crea un prodotto su Accordi Jewelry usando foto, prezzo e AI
  vision per nome, descrizione, categoria e materiale.
- `!script-eleven`: genera uno script breve per voiceover/social a partire da
  una foto gioiello, pronto da usare con ElevenLabs.

`!script-eleven` richiede almeno una foto allegata e usa la key OpenAI di progetto.
Puoi aggiungere contesto libero, per esempio:

```text
!script-eleven prezzo 14,90 focus regalo
```

La risposta include hook, script entro circa 30 secondi, testo a schermo, CTA e
tre hook alternativi.

Per Accordi Jewelry, configura il token admin dal pannello impostazioni del gioco
oppure con variabile ambiente `ADMIN_API_TOKEN`. Il bot invia `multipart/form-data`
con campo file reale `file`, non base64 e non URL obbligatorio.

## Briefing mattutino AI

Il runtime crea automaticamente un task giornaliero per `ai-news-navigator` alle
08:00 Europe/Rome. Il task chiede un riepilogo in italiano sulle ultime notizie AI
con TL;DR, 5-8 notizie, fonti/link, distinzione fatti/rumor/analisi e trend da
monitorare.

Variabili utili:

```bash
AGENT_LAB_AI_NEWS_BRIEFING=1
AGENT_LAB_AI_NEWS_TIME=08:00
AGENT_LAB_AI_NEWS_TIMEZONE=Europe/Rome
AGENT_LAB_AI_NEWS_AGENT=ai-news-navigator
```

Di default il runtime non recupera automaticamente un briefing perso se lo avvii
dopo l'orario. Per farlo:

```bash
AGENT_LAB_AI_NEWS_RUN_MISSED=1
```

Endpoint di controllo:

- `GET /api/briefings/ai-news`: stato scheduler e prossimo run.
- `POST /api/briefings/ai-news/run`: crea subito il task del briefing per test.

Per ottenere notizie reali serve una API key valida nello scope scelto
dall'agente. Se la key manca o non e valida, il task viene creato ma fallisce con
un errore provider leggibile.

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
Su macOS, l'azione `Apri interfaccia scraper` viene aperta tramite Terminal:
il launch headless diretto dal backend faceva abortire il processo Tk della GUI.

## The Main Scraper

Nella GUI Vinted di The Main Scraper puoi salvare e riusare termini o URL di
ricerca. I valori vengono persistiti nel file
`projects/main-scraper/output/_saved_search_terms.json`, separati dalle run
archiviate nel database SQLite.
La GUI espone anche categorie rapide Vinted per cercare direttamente in:
accessori donna, accessori uomo, gioielli donna, scarpe donna e scarpe uomo;
se abbini una keyword, costruisce automaticamente l'URL della categoria con
`search_text`.
Le nuove ricerche Vinted escludono di default gli annunci gia analizzati nel DB,
con checkbox dedicata per riattivarli quando serve.
La GUI Vinted include ora anche una modalita `Procacciatore affari`: ruota in
loop una lista di keyword (per esempio charm, bracciali, pandora, collane,
gioielli), entra nei candidati con almeno una soglia like configurabile
(default 70), conferma la data dal dettaglio annuncio e tiene nei risultati
solo gli articoli entro la finestra oraria configurata (default 24 ore). Il
procacciatore usa un profilo rapido dedicato: pausa azioni 0,25s, attesa pagina
1,0s e pausa loop default 5s. Se un annuncio e gia nel DB con `item_id`, prezzo
e descrizione, il dettaglio viene riusato dalla cache e la pagina annuncio non
viene riaperta. Anche l'estrazione descrizioni Vinted usa il profilo rapido e
timeout navigazione 15s.
L'offerta Vinted automatica usa una percentuale configurabile direttamente dalla
GUI, non piu solo il valore fisso del 15%. Le offerte possono partire anche
mentre il procacciatore sta lavorando: girano in un processo separato e il loop
continua.
Le offerte gia inviate vengono registrate nello stesso DB Vinted e vengono
saltate automaticamente nelle esecuzioni successive; gli annunci con offerta
inviata non restano piu in `da valutare assolutamente`.
Nella tabella risultati, gli annunci con offerta gia inviata vengono anche
spostati in fondo alla lista e colorati in modo dedicato, anche dopo i cambi di
ordinamento.

L'estrazione descrizioni Vinted usa ora un profilo piu rapido dedicato
(`0,15s` pausa azioni, `0,6s` attesa pagina) e una singola lettura JS del
dettaglio annuncio per titolo, prezzo, spedizione, caricato, offerta e testo.
Anche il procacciatore usa ora navigazione Vinted `Wait.SHORT` quando apre
catalogo, dettaglio, pagine successive e ritorno post-login, per evitare attese
lunghe prima del parsing.
Nel procacciatore, un annuncio viene confermato come affare solo se rispetta
tutti i vincoli attivi: like minimi, eta massima, prezzo massimo e spedizione
non oltre `2,99 €`.
Puoi anche attivare l'invio Discord via webhook dal pannello del procacciatore:
ogni nuovo affare confermato viene inviato una sola volta al canale configurato,
con deduplica persistente nel DB SQLite.
Il badge stato nell'header del main scraper e colorato: grigio `Idle`, verde
`Running`, rosso `Stopping...`, rosso scuro `Error`.

### Upload Vinted

L'upload Vinted puo partire dalla GUI dello scraper, da CLI o da Discord. Il
flusso supporta:

- piu foto per annuncio;
- analisi AI della foto per titolo, descrizione e categoria;
- prezzo passato dall'utente;
- valori predefiniti per brand, condizioni e materiale;
- salvataggio bozza o pubblicazione;
- riuso del browser/profilo Vinted quando possibile;
- login assistito con marker account e notifiche quando l'accesso manca.

Da Discord, `!upload` usa la foto allegata e il prezzo scritto nel messaggio.
`!upload-ai-photo` genera prima varianti AI della foto e poi usa quelle per il
caricamento.

### Accordi Jewelry

`!accordi` crea o aggiorna prodotti su `accordijewelry.com` usando la API admin.
Il comando usa OpenAI vision per compilare i campi prodotto quando l'utente passa
solo foto e prezzo.

Esempio:

```text
!accordi prezzo 20
```

con una foto allegata. Il runtime genera:

- `name`;
- `slug`;
- `description`;
- `price_cents`;
- `category`;
- `material`;
- `featured`;
- `file` multipart.

Se lo slug esiste gia, il backend Accordi puo rifiutare la creazione. In quel
caso serve usare un update con product id oppure generare uno slug diverso.

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

Smoke test navigazione:

```bash
.venv/bin/python scripts/test_browser_navigation.py --backend mock
.venv/bin/python scripts/test_browser_navigation.py --backend botasaurus
.venv/bin/python scripts/test_agent_browser_tools.py --backend mock
.venv/bin/python scripts/test_agent_browser_tools.py --backend botasaurus
```

Il backend `mock` valida il contratto runtime senza aprire Chrome. Il backend
`botasaurus` apre una sessione reale e richiede Google Chrome installato sul Mac.
`test_agent_browser_tools.py` passa dal loop agente -> tool registry -> browser
control, quindi verifica il percorso che useranno gli agenti con toolset
`browser`.

## Vast.ai e ComfyUI media generation

La root include `catalog_server_vast.py`, un MVP autonomo per generare cataloghi
media su Vast.ai usando ComfyUI. E pensato per essere copiato su una istanza Vast
con ComfyUI gia presente, lanciato da terminale Jupyter e usato tramite una
piccola UI web.

Il file si occupa da solo del bootstrap Python:

- se `flask` e `requests` non sono disponibili, crea un venv locale;
- installa le dipendenze dentro `/workspace/catalog-venv`;
- si riavvia nel Python del venv;
- non modifica il Python di sistema Debian.

Avvio tipico quando ComfyUI e gia acceso e i modelli sono gia presenti:

```bash
python3 catalog_server_vast.py \
  --comfyui /workspace/ComfyUI \
  --port 8000 \
  --password "scegli-una-password" \
  --no-start-comfyui \
  --skip-model-downloads
```

Avvio lasciando allo script il tentativo di partire con ComfyUI:

```bash
python3 catalog_server_vast.py \
  --comfyui /workspace/ComfyUI \
  --port 8000 \
  --password "scegli-una-password" \
  --skip-model-downloads
```

Il server espone:

- `GET /`: UI web per upload reference e scelta template;
- `POST /generate`: crea un job;
- `GET /status/<job_id>`: stato avanzamento;
- `GET /download/<job_id>`: ZIP finale;
- `GET /health`: stato server e socket ComfyUI.

I template inclusi coprono ecommerce white, modella, reference modella, mano,
jewelry stand, luxury fabric, marble, black luxury, macro, Capri, sunset, gift e
social ad. Il template `model_reference` richiede una seconda immagine reference.

Lo script resta un MVP: i job sono in memoria e vengono persi se il processo si
riavvia. Gli output e gli upload vengono comunque salvati sotto
`/workspace/catalog_jobs` o nella directory parent del path ComfyUI configurato.

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
