# Video Script Log

Questo file e la base aggiornata per i video del progetto.
Quando mi chiedi qualcosa per un videolog, aggiorno prima questo file con lo stato attuale, poi continuo da li.

## Progetto

Agent AI Game e una simulazione 3D in stile gioco per controllare agenti AI in modo visivo.
L'obiettivo e vedere gli agenti muoversi, lavorare, comunicare, ricevere job e lanciare progetti esterni senza uscire dal mondo di gioco.

Il progetto include:
- scena 3D con agenti e interazioni
- popup sopra l'agente per dare comandi
- chat persistente per singolo agente
- popup e finestre spostabili manualmente
- memoria separata per agente o condivisa di progetto
- job in coda, completati e notifiche
- scheduling dei job
- output leggibili nel gioco
- integrazione con progetti esterni tramite project gateway
- supporto a provider e modelli configurabili
- editor visuale per stanze, porte, corridoi, agenti e postazioni
- popup dedicato per l'agente browser con sessioni live e comandi del Main Scraper

## Stato attuale

Queste sono le cose gia presenti o in corso:
- visualizzazione dei job nel pannello gioco
- storico dei job finiti
- notifiche quando un job termina
- popup rapido sopra l'agente per scrivere messaggi
- popup browser con lista sessioni e comandi live del Main Scraper
- memoria persistente per non perdere la conversazione
- configurazione API key per agente singolo o per tutto il progetto
- scelta del tipo di modello e del provider
- pianificazione con data/ora, ripetizione giornaliera o giorni specifici
- output strutturato per risultati tabellari, file o riepiloghi
- fallback testuale per output non strutturati
- supporto al lancio di progetti esterni dal gioco
- editor layout aperto dal pulsante `Editor`
- stanze modellabili a celle come in un editor tipo The Sims
- porte/corridoi che collegano stanze e diventano attraversabili dal pathfinding
- spostamento visuale di agenti e postazioni tra stanze
- preset workstation inseribili dall'Editor e collegabili agli agenti
- creazione agente con scelta del preset workstation e piazzamento guidato
- popup trascinabili dalla barra superiore
- chat agente che segue l'agente finche non viene trascinata manualmente, poi diventa detached
- log e output leggibili anche in light mode con testo nero

### Scheda per il video

- cosa funziona già:
  - selezione agente dalla scena
  - popup rapido sopra la testa dell'agente
  - chat persistente per singolo agente
  - popup rapido che segue l'agente e si stacca solo se spostato manualmente
  - job con stato, coda, completamento e notifiche
  - output leggibile nel gioco con fallback testuale
  - project gateway per lanciare progetti esterni
  - scheduling con data, ora e ripetizione
  - editor stanza/porta con griglia di celle
  - spostamento visivo di agenti e tavoli/postazioni
  - workstation dedicate per agente
  - modalita dark e white
  - log leggibili in tema chiaro

- cosa ho implementato:
  - vista output generica riusabile per piu tipi di risultato
  - preview tabellare per `rows`
  - preview lista per `files` o `exported_files`
  - preview sintetica per `summary` e `meta_summary`
  - pannello job finiti
  - notifiche job in alto
  - memoria persistente e wiki persistente
  - mini editor `Editor` per modificare il mondo senza riempire la toolbar
  - aggiunta e rimozione stanze
  - modellazione stanze con celle contigue
  - porte e corridoi come celle camminabili reali
  - preset workstation collegabili agli agenti
  - piazzamento workstation richiesto durante creazione agente
  - popup trascinabili per chat, editor e dialog
  - comportamento detached della chat solo dopo un vero drag
  - correzione dei colori log/output in light mode

- cosa si vede a schermo:
  - mondo 3D con agenti che si muovono
  - nome e ruolo dell'agente visibili
  - popup di messaggio vicino all'agente
  - popup che puo essere trascinato e lasciato in posizione libera
  - pannello di configurazione agente
  - pannello progetto con output e pianificazione
  - lista job e notifiche quando finiscono
  - select preset workstation nell'Editor e nel dialog `+ Agent`
  - richiesta visuale di cliccare un tile per piazzare la workstation
  - mini editor per aggiungere stanze, modellarle, mettere porte e rimuoverle
  - stanze multiple con agenti e tavoli controllabili visivamente
  - log e output scuri/neri quando il tema e chiaro

- quali agenti esistono:
  - Orchestrator
  - Planner
  - Researcher
  - Builder
  - Critic
  - Memory
  - Scheduler

- che workflow fanno:
  - Orchestrator: assegna e coordina i compiti
  - Planner: spezza un obiettivo in passi
  - Researcher: raccoglie informazioni e fonti
  - Builder: implementa cambiamenti e patch
  - Critic: controlla errori, rischi e regressioni
  - Memory: conserva contesto e fatti stabili
  - Scheduler: prepara scheduling, follow-up e riepiloghi temporizzati

- che parte è ancora mock/prototipo:
  - diversi agenti usano ancora provider simulato
  - il comportamento del mondo e ancora in evoluzione
  - alcune risposte e output sono ancora semplificati per UI e test
  - il routing verso progetti esterni sta diventando stabile ma non e ancora definitivo
  - l'editor e funzionante, ma puo ancora evolvere verso strumenti piu avanzati tipo selezione multi-cella/paint

- prossimo step:
  - rendere i workflow piu espliciti in UI
  - aggiungere preview dedicate per altri tipi di output
  - rafforzare la memoria condivisa e la wiki per agente
  - mostrare meglio lo stato dei job lunghi e dei job schedulati
  - collegare sempre meglio il gioco ai progetti esterni reali
  - migliorare il controllo visuale degli agenti nelle stanze
  - rendere l'editor ancora piu simile a un builder da gioco

## Cosa deve raccontare il video

Il video deve mostrare:
- come gli agenti vengono selezionati e comandati
- come si apre il popup sopra la testa dell'agente
- come la chat segue l'agente e diventa detached solo quando viene trascinata
- come parte un job o un progetto esterno
- come si vede lo stato in tempo reale
- come appare l'output dentro al gioco
- come viene salvata la memoria e lo storico
- come si apre l'editor, si aggiungono stanze, si modellano celle e si collegano porte
- come il sistema resta estensibile per altri progetti e altri tipi di output

## Regola per gli aggiornamenti

Da ora in poi questo file va tenuto aggiornato ogni volta che lavoriamo su una feature visibile o narrabile nel videolog, non solo quando viene chiesto esplicitamente uno script.

Formato da mantenere:
- richiesta
- cosa ho fatto
- file toccati
- stato attuale
- nota utile per il video

## Registro

### Episodio 01

Richiesta:
- creare una base visiva per agenti AI in 3D

Stato:
- base di gioco avviata con agenti, interazioni e struttura di progetto

Nota video:
- il progetto parte come simulazione controllabile, non come semplice dashboard

### Episodio 02

Richiesta:
- rendere il mondo piu controllabile visivamente
- aggiungere piu stanze
- permettere di spostare agenti e tavoli/postazioni
- collegare le stanze con porte
- creare stanze tramite griglia di celle in stile editor The Sims
- sostituire i pulsanti sparsi con un piccolo `Editor`
- rendere popup e finestre spostabili
- fare in modo che la chat agente segua l'agente finche non viene trascinata manualmente

Cosa ho fatto:
- aggiunto pannello `Editor` per entrare in modalita modifica mondo
- aggiunte azioni `+ Stanza`, `Modella stanza`, `Porte`, `Rimuovi stanza`, `Reset`
- trasformate le stanze da semplici rettangoli a insiemi contigui di celle
- aggiunte porte/corridoi come celle realmente camminabili dal pathfinding
- aggiunto controllo stanza nell'inspector con conteggio agenti/celle e azione `Porta qui`
- aggiunto drag per chat rapida, editor e dialog
- corretto il comportamento della chat: resta agganciata all'agente e diventa detached solo dopo un vero trascinamento

File toccati:
- `app.mjs`
- `src/agentWorld.mjs`
- `index.html`
- `styles.css`
- `README.md`
- `AGENT_PROTOCOL.md`

Stato attuale:
- il gioco permette di costruire una piccola mappa di stanze e corridoi
- agenti e tavoli possono essere spostati visualmente
- il layout viene salvato nel browser
- la chat agente e piu simile a un dialog di gioco, ma puo diventare finestra libera se spostata

Nota utile per il video:
- mostrare prima l'agente con chat che lo segue, poi trascinare la chat per far vedere il detach
- mostrare l'apertura di `Editor`, la creazione di una stanza, la modifica a celle e l'aggiunta di una porta/corridoio
- sottolineare che non e solo estetica: porte e celle influenzano davvero dove gli agenti possono camminare

### Episodio 03

Richiesta:
- migliorare la leggibilita dei log in light mode

Cosa ho fatto:
- impostato testo nero per event log, job toast summary/output e project result quando il tema e chiaro
- mantenuto background chiaro per contrasto
- aggiornato README e video script log

File toccati:
- `styles.css`
- `README.md`
- `VIDEO_SCRIPT_LOG.md`

Stato attuale:
- in white mode i log non restano piu grigi/chiari su sfondo chiaro
- gli output testuali sono piu leggibili durante demo e registrazione

Nota utile per il video:
- se mostri il tema chiaro, inquadrare anche i log o l'output per far vedere che ora il contrasto e corretto

### Episodio 04

Richiesta:
- quando creo un agente deve chiedermi dove piazzare la sua workstation
- nell'Editor devono esserci preset di workstation inseribili e collegabili a un agente

Cosa ho fatto:
- aggiunti preset workstation condivisi nel modello del mondo
- aggiunto select `Workstation` nel dialog `+ Agent`
- dopo la creazione agente, viene creata una workstation dedicata e l'Editor chiede di cliccare il tile dove piazzarla
- aggiunta sezione preset workstation nel mini Editor
- aggiunto collegamento workstation -> agente
- gli agenti con workstation dedicata la usano come destinazione preferita
- le workstation custom vengono salvate nel layout locale

File toccati:
- `src/agentWorld.mjs`
- `app.mjs`
- `index.html`
- `styles.css`
- `README.md`
- `AGENT_PROTOCOL.md`
- `VIDEO_SCRIPT_LOG.md`

Stato attuale:
- il mondo puo avere workstation statiche e workstation custom
- ogni agente puo avere una workstation dedicata
- il layout salva anche le workstation create da preset

Nota utile per il video:
- mostrare la creazione di un nuovo agente, la scelta del preset workstation, poi il click nel mondo per piazzarla
- mostrare l'Editor con preset workstation e collegamento ad agente esistente
