# Agent Protocol Lab 3D

Prototype 3D per visualizzare una rete di agenti AI come una piccola simulazione di gioco: gli agenti stanno su blocchi, camminano cella per cella tra postazioni, lavorano, ricevono task e comunicano con messaggi animati.

La demo browser usa Three.js via CDN e il motore logico locale in `src/`. Puoi selezionare agenti e postazioni, ruotare la camera, osservare i messaggi in transito e attivare intenti come task, sync memoria e review.

## Run

Su Windows puoi avviare direttamente:

```powershell
.\run.bat
```

Oppure usa manualmente un piccolo server locale dalla root del progetto:

```powershell
python -m http.server 8000
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
- `AGENT_PROTOCOL.md`: note architetturali ed estensione.

## Controlli

- Clicca un agente per ispezionarlo.
- Clicca un blocco libero per muovere manualmente l'agente selezionato.
- Trascina sul pavimento per spostare la camera.
- Usa la rotella del mouse per lo zoom.
- Usa `Q` / `E` o i pulsanti camera per ruotare.
- Usa `Auto` / `Manuale` per abilitare o bloccare gli spostamenti automatici.
- Usa `Task`, `Memoria`, `Review` per generare lavoro e comunicazioni.
- Usa `Pausa` e `1x/2x/4x` per controllare la simulazione.

## Prestazioni

Le impostazioni leggere sono in `app.mjs`, costante `PERFORMANCE`:

- `maxFps`: frame cap, ora 30 FPS.
- `maxPixelRatio`: risoluzione interna massima, ora 1.25.
- `shadows`: ombre dinamiche, ora disattivate.
- `fog`: nebbia shader, ora disattivata.

## Java Port

La precedente sandbox Java2D/voxel resta in `java/`.

- source: `java/src/blockforge`
- build and run steps: `java/README.md`
