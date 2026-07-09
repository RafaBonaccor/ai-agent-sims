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
- memoria separata per agente o condivisa di progetto
- job in coda, completati e notifiche
- scheduling dei job
- output leggibili nel gioco
- integrazione con progetti esterni tramite project gateway
- supporto a provider e modelli configurabili

## Stato attuale

Queste sono le cose gia presenti o in corso:
- visualizzazione dei job nel pannello gioco
- storico dei job finiti
- notifiche quando un job termina
- popup rapido sopra l'agente per scrivere messaggi
- memoria persistente per non perdere la conversazione
- configurazione API key per agente singolo o per tutto il progetto
- scelta del tipo di modello e del provider
- pianificazione con data/ora, ripetizione giornaliera o giorni specifici
- output strutturato per risultati tabellari, file o riepiloghi
- fallback testuale per output non strutturati
- supporto al lancio di progetti esterni dal gioco

### Scheda per il video

- cosa funziona già:
  - selezione agente dalla scena
  - popup rapido sopra la testa dell'agente
  - chat persistente per singolo agente
  - job con stato, coda, completamento e notifiche
  - output leggibile nel gioco con fallback testuale
  - project gateway per lanciare progetti esterni
  - scheduling con data, ora e ripetizione

- cosa ho implementato:
  - vista output generica riusabile per piu tipi di risultato
  - preview tabellare per `rows`
  - preview lista per `files` o `exported_files`
  - preview sintetica per `summary` e `meta_summary`
  - pannello job finiti
  - notifiche job in alto
  - memoria persistente e wiki persistente

- cosa si vede a schermo:
  - mondo 3D con agenti che si muovono
  - nome e ruolo dell'agente visibili
  - popup di messaggio vicino all'agente
  - pannello di configurazione agente
  - pannello progetto con output e pianificazione
  - lista job e notifiche quando finiscono

- quali agenti esistono:
  - Orchestrator
  - Planner
  - Researcher
  - Builder
  - Critic
  - Memory

- che workflow fanno:
  - Orchestrator: assegna e coordina i compiti
  - Planner: spezza un obiettivo in passi
  - Researcher: raccoglie informazioni e fonti
  - Builder: implementa cambiamenti e patch
  - Critic: controlla errori, rischi e regressioni
  - Memory: conserva contesto e fatti stabili

- che parte è ancora mock/prototipo:
  - diversi agenti usano ancora provider simulato
  - il comportamento del mondo e ancora in evoluzione
  - alcune risposte e output sono ancora semplificati per UI e test
  - il routing verso progetti esterni sta diventando stabile ma non e ancora definitivo

- prossimo step:
  - rendere i workflow piu espliciti in UI
  - aggiungere preview dedicate per altri tipi di output
  - rafforzare la memoria condivisa e la wiki per agente
  - mostrare meglio lo stato dei job lunghi e dei job schedulati
  - collegare sempre meglio il gioco ai progetti esterni reali

## Cosa deve raccontare il video

Il video deve mostrare:
- come gli agenti vengono selezionati e comandati
- come si apre il popup sopra la testa dell'agente
- come parte un job o un progetto esterno
- come si vede lo stato in tempo reale
- come appare l'output dentro al gioco
- come viene salvata la memoria e lo storico
- come il sistema resta estensibile per altri progetti e altri tipi di output

## Regola per gli aggiornamenti

Da ora in poi questo file va tenuto aggiornato ogni volta che lavoriamo su un prompt per il videolog.

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
