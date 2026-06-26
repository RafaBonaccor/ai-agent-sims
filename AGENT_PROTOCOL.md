# Agent Protocol Lab

Questa demo trasforma la base browser in una visualizzazione 3D di agenti AI, relazioni e messaggi di protocollo. La forma visuale e una piccola stanza/laboratorio a blocchi: gli agenti stanno su caselle, si muovono tile-by-tile tra postazioni, lavorano e comunicano.

## Struttura

- `index.html`: shell dell'app, controlli, inspector e log.
- `styles.css`: interfaccia operativa responsive.
- `app.mjs`: renderer Three.js, camera isometrica, selezione, HUD e comunicazioni animate.
- `src/agentWorld.mjs`: stato del mondo di gioco, griglia di blocchi, postazioni, pathfinding, target manuali e lavori degli agenti.
- `src/scenarios.mjs`: scenario modificabile con agenti, relazioni, protocolli e intenti.
- `src/agentProtocol.mjs`: motore logico di messaggistica, scheduling e regole di protocollo.

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

Per aggiungere un agente, modifica `agents` in `src/scenarios.mjs` e collega almeno una `relation`. Per aggiungere un protocollo, inserisci un nuovo oggetto in `protocols` con `messageTypes` e `rules`, poi usa il suo `protocolId` nelle relazioni o negli intenti.

Le regole supportano destinatari flessibili:

- `sender`: risponde a chi ha inviato il messaggio.
- `all-connected`: invia a tutti gli agenti collegati.
- `capability`: invia agli agenti che espongono una capacita.

## Prossimi step

- Persistenza dello scenario in JSON modificabile dall'interfaccia.
- Adattatori verso agenti reali tramite WebSocket o HTTP.
- Validazione formale dei protocolli con schema JSON.
- Timeline ispezionabile con replay e filtri per protocollo.
- Politiche di sicurezza per autorizzazioni, rate limit e isolamento dei tool.
