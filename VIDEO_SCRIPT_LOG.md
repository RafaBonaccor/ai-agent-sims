# Video Script Log

Questo file e il registro ufficiale per i contenuti video.

## Descrizione del progetto

Blockforge Java e un sandbox voxel in stile Minecraft pensato anche come progetto narrativo per video a episodi.
L'obiettivo non e solo far funzionare il gioco, ma costruire una sequenza chiara di problemi, scelte tecniche,
fix e miglioramenti che possano diventare facilmente script, voiceover e struttura del contenuto.

Da ora in poi, a ogni tua richiesta aggiungero:
- cosa hai chiesto
- cosa ho fatto
- file e linee chiave toccate
- una nota breve utile per lo script video

Nota: i numeri di linea sono fotografati subito dopo quella modifica e possono spostarsi nelle versioni successive.

## Parte 01 - Morte nel vuoto e base Java

Richiesta:
- se cado nel vuoto devo morire
- inizia a scriverlo in Java

Cosa ho fatto:
- ho aggiunto morte nel vuoto, conto morti e respawn
- ho avviato la base Java con finestra Swing e loop di gioco

File e linee chiave:
- `java/src/blockforge/GamePanel.java:164-193` logica di tick, morte nel vuoto e respawn
- `java/src/blockforge/GamePanel.java:577-585` HUD di morte e timer di respawn
- `java/src/blockforge/World.java:126-143` ricerca del punto di spawn

Nota script video:
- "La prima regola del mondo e semplice: se cadi nel vuoto, muori e riparti."

## Parte 02 - Focus Java e interazione di base

Richiesta:
- focalizza il progetto su Java

Cosa ho fatto:
- ho consolidato il loop Java come base principale
- ho collegato selezione, mining, placing e hotbar nel pannello di gioco

File e linee chiave:
- `java/src/blockforge/GamePanel.java:404-431` selezione del blocco in vista superiore e prima persona
- `java/src/blockforge/GamePanel.java:444-497` rimozione e piazzamento blocchi
- `java/src/blockforge/GamePanel.java:534-612` HUD e hotbar

Nota script video:
- "Da qui in avanti il progetto smette di essere un test e diventa una base giocabile in Java."

## Parte 03 - Due viste sullo stesso mondo

Richiesta:
- lascia la vista superiore ma voglio anche la prima persona come Minecraft

Cosa ho fatto:
- ho mantenuto la vista superiore
- ho aggiunto la prima persona sullo stesso stato del mondo
- ho separato i renderer isometrico e first-person

File e linee chiave:
- `java/src/blockforge/GamePanel.java:151-157` switch di rendering tra le due camere
- `java/src/blockforge/GamePanel.java:358-367` cambio vista e messaggi di stato
- `java/src/blockforge/IsometricWorldRenderer.java:67-116` renderer vista superiore
- `java/src/blockforge/FirstPersonWorldRenderer.java:19-94` renderer prima persona

Nota script video:
- "Lo stesso mondo ora si puo raccontare in due modi: dall'alto e dagli occhi del player."

## Parte 04 - Avvio del gioco con script

Richiesta:
- come lo faccio partire
- crea uno script per farlo partire facilmente

Cosa ho fatto:
- ho preparato avvio automatico con compilazione e run
- ho gestito il fallback verso Amazon Corretto se `java` o `javac` non sono nel PATH

File e linee chiave:
- `run-java.ps1:1-43` compile + run in PowerShell
- `run-java.bat:1-64` compile + run in batch Windows

Nota script video:
- "Prima di complicare il gioco, dovevo rendere banale avviarlo."

## Parte 05 - Mouse lock e controlli coerenti

Richiesta:
- il mouse non viene attaccato bene al puntatore
- il movimento e invertito

Cosa ho fatto:
- ho agganciato meglio il mouse in prima persona
- ho corretto rotazione e gestione del lock/unlock
- ho lasciato `Esc` per liberare o riagganciare il mouse

File e linee chiave:
- `java/src/blockforge/GamePanel.java:78-140` gestione input mouse e focus
- `java/src/blockforge/GamePanel.java:196-233` movimento mouse e aggiornamento yaw/pitch
- `java/src/blockforge/GamePanel.java:370-389` cattura del mouse e ricentraggio
- `java/src/blockforge/GamePanel.java:653-659` toggle del mouse lock con `Esc`

Nota script video:
- "La prima persona non funziona se il mouse non si comporta come una vera camera."

## Parte 06 - Prima persona meno finta e meno pixelata

Richiesta:
- guardare in alto o in basso non funziona
- si vede tutto pixelato

Cosa ho fatto:
- ho portato la prima persona su un renderer prospettico a facce
- ho smesso di trattare la scena come semplici colonne verticali sullo schermo

File e linee chiave:
- `java/src/blockforge/FirstPersonWorldRenderer.java:19-94` disegno delle facce visibili
- `java/src/blockforge/FirstPersonWorldRenderer.java:286-391` proiezione prospettica, profondita e fog

Nota script video:
- "Qui il progetto smette di sembrare un mock e inizia ad avere una vera profondita."

## Parte 07 - Architettura piu pulita

Richiesta:
- inizia a strutturare bene l'architettura del progetto

Cosa ho fatto:
- ho separato i renderer dal pannello principale
- ho reso `GamePanel` il punto di orchestrazione di input, fisica e HUD
- ho documentato i moduli attuali

File e linee chiave:
- `java/src/blockforge/GamePanel.java:44-68` composizione degli oggetti principali
- `java/src/blockforge/IsometricWorldRenderer.java:12-269` renderer superiore dedicato
- `java/src/blockforge/FirstPersonWorldRenderer.java:11-415` renderer first-person dedicato
- `java/ARCHITECTURE.md:1-23` mappa dell'architettura

Nota script video:
- "Prima di crescere ancora, il progetto aveva bisogno di una struttura leggibile."

## Parte 08 - Voxel veri: ogni blocco lavora singolarmente

Richiesta:
- ogni blocco deve lavorare singolarmente
- se aggiungo un blocco sopra l'altro non deve comportarsi come una torre unica

Cosa ho fatto:
- ho sostituito il vecchio modello a colonne con storage voxel `x,y,z`
- ho separato selezione del blocco colpito e posizione del blocco da piazzare
- mining e placing ora agiscono su un singolo voxel

File e linee chiave:
- `java/src/blockforge/World.java:10-19` storage 3D dei blocchi
- `java/src/blockforge/World.java:50-75` lettura, piazzamento e rimozione di un singolo blocco
- `java/src/blockforge/World.java:100-114` supporto fisico cercato per blocco e non per colonna
- `java/src/blockforge/SelectionTarget.java:5-15` target con blocco colpito e blocco di piazzamento
- `java/src/blockforge/CellProjection.java:5-5` proiezione per singolo blocco
- `java/src/blockforge/GamePanel.java:302-347` movimento e gravita sul nuovo supporto voxel
- `java/src/blockforge/GamePanel.java:404-431` selezione del blocco attuale
- `java/src/blockforge/GamePanel.java:444-497` mining e placing per singolo blocco
- `java/src/blockforge/IsometricWorldRenderer.java:19-84` raccolta e draw dei blocchi visibili
- `java/src/blockforge/IsometricWorldRenderer.java:144-203` draw delle facce del cubo
- `java/src/blockforge/FirstPersonWorldRenderer.java:105-143` raycast del blocco selezionato

Nota script video:
- "Questo e il salto vero: non sto piu modificando colonne, ma blocchi indipendenti nello spazio."

## Parte 09 - Camera verticale quasi completa

Richiesta:
- devo poter guardare anche il blocco sotto di me

Cosa ho fatto:
- ho allargato il limite verticale della camera first-person quasi fino alla verticale

File e linee chiave:
- `java/src/blockforge/GamePanel.java:41-41` nuovo limite del pitch verticale
- `java/src/blockforge/GamePanel.java:209-227` applicazione del pitch al mouse
- `java/src/blockforge/GamePanel.java:244-248` applicazione del pitch ai tasti freccia
- `java/src/blockforge/FirstPersonWorldRenderer.java:105-143` raycast coerente col nuovo pitch

Nota script video:
- "La camera ora puo piegarsi quasi del tutto, quindi posso davvero guardare sotto i piedi."

## Parte 10 - Registro per script video

Richiesta:
- crea un file dove vai scrivendo cosa ho chiesto e cosa hai aggiustato con linee di codice cambiate

Cosa ho fatto:
- ho creato questo file come log ufficiale per i contenuti video
- da qui in poi aggiornero questo file a ogni nuova richiesta

File e linee chiave:
- `VIDEO_SCRIPT_LOG.md:1-137` registro delle parti video e dei cambi tecnici

Nota script video:
- "Da questo punto in poi ogni modifica entra anche nel diario di produzione, pronto per diventare voce narrante."

## Parte 11 - Collisione vera del corpo con i blocchi

Richiesta:
- metti anche una bella descrizione
- quando mi avvicino troppo a un blocco la visuale entra dentro il blocco
- non devo riuscire a vedere attraverso il blocco

Cosa ho fatto:
- ho aggiunto una descrizione piu forte in testa a questo file per usarlo meglio nei video
- ho dato al player un raggio fisico reale, cosi la camera non puo infilarsi nei voxel lateralmente
- ho bloccato il movimento se il corpo andrebbe a sovrapporsi a un blocco
- ho protetto anche salto, caduta e piazzamento per evitare compenetrazioni col corpo

File e linee chiave:
- `java/src/blockforge/GamePanel.java:41-42` dimensioni fisiche del player per la collisione
- `java/src/blockforge/GamePanel.java:303-327` movimento orizzontale con test di occupazione reale
- `java/src/blockforge/GamePanel.java:329-360` gravita e salto bloccati se il corpo entra in un blocco
- `java/src/blockforge/GamePanel.java:511-519` controllo di piazzamento contro il volume del player
- `java/src/blockforge/GamePanel.java:624-679` test AABB del corpo contro i voxel solidi

Nota script video:
- "La camera non e piu un fantasma: adesso ha un corpo, sbatte contro i blocchi e smette di trapassare il mondo."

## Parte 12 - Prompt stabile per il creatore di script

Richiesta:
- dammi un prompt per il mio creatore di script
- deve seguire bene il passo del progetto
- deve fare script congrui a quello che stiamo costruendo

Cosa ho fatto:
- ho creato un prompt riutilizzabile per il tuo generatore di script
- gli ho imposto di usare `VIDEO_SCRIPT_LOG.md` come fonte primaria
- ho definito regole anti-allucinazione, struttura narrativa e formato di output

File e linee chiave:
- `SCRIPT_CREATOR_PROMPT.md:1-88` prompt principale per il creatore di script
- `SCRIPT_CREATOR_PROMPT.md:90-102` esempio pratico di utilizzo

Nota script video:
- "Per raccontare bene un progetto iterativo non basta costruire il gioco: serve anche una macchina narrativa che resti fedele a ogni passo reale."

## Parte 13 - Menu pausa e salvataggio locale

Richiesta:
- inserire un menu di pausa
- aggiungere una logica di salvataggio

Cosa ho fatto:
- ho aggiunto uno stato di pausa reale al gioco Java
- quando la pausa e attiva il game loop smette di aggiornare movimento, gravita, respawn e selezione
- ho introdotto un sistema di salvataggio locale in formato properties
- il salvataggio conserva mondo modificato, posizione player, camera, blocco selezionato e morti
- ho aggiunto caricamento rapido e salvataggio rapido
- ho aggiornato il README Java con i nuovi controlli

File e linee chiave:
- `java/src/blockforge/GamePanel.java` gestione pausa, input, save/load e overlay
- `java/src/blockforge/SaveGame.java` formato di salvataggio locale
- `java/src/blockforge/World.java` esportazione/importazione dei blocchi del mondo
- `java/README.md` controlli e posizione del file di salvataggio

Nota script video:
- "Il gioco smette di essere solo un prototipo volatile: adesso il mondo puo essere fermato, salvato e ripreso."

## Parte 14 - Restyling del menu pausa con pulsanti

Richiesta:
- migliorare l'estetica del menu pausa
- aggiungere pulsanti
- fare in modo che il gioco si fermi davvero e non legga piu il mouse quando e pausato

Cosa ho fatto:
- ho sostituito il vecchio menu testuale con un pannello piu curato
- ho aggiunto pulsanti cliccabili per Riprendi, Salva partita e Carica
- ho aggiunto hover sui pulsanti del menu
- ho separato il mouse del menu dal mouse del gameplay
- in pausa il mouse non aggiorna piu camera, mira o selezione
- in pausa il mouse-look viene sganciato e il cursore torna visibile

File e linee chiave:
- `java/src/blockforge/GamePanel.java:218` il mouse in pausa aggiorna solo hover/click del menu
- `java/src/blockforge/GamePanel.java:647-735` nuovo menu pausa con pulsanti
- `java/src/blockforge/GamePanel.java:747-765` stato pausa, stop input e rilascio mouse-look
- `java/src/blockforge/GamePanel.java:982-986` azioni del menu pausa

Nota script video:
- "La pausa ora sembra una vera schermata di gioco: non una scritta buttata sopra, ma un menu con pulsanti, salvataggio e blocco completo dell'azione."

## Parte 15 - Primo passo tecnico: chunk e culling

Richiesta:
- iniziare a introdurre tecniche consigliate come greedy mesh, ambient occlusion, depth order e frustum culling

Cosa ho fatto:
- ho iniziato dal prerequisito strutturale: dividere il mondo in chunk 8x8
- `World` ora espone chunk e metodi per recuperare solo quelli vicini al player
- il renderer isometrico non scorre piu direttamente tutte le celle nel raggio, ma passa dai chunk visibili
- il renderer in prima persona usa i chunk vicini e scarta quelli chiaramente fuori dalla direzione della camera
- il culling e volutamente conservativo, cosi evita pop-in aggressivo ai bordi della visuale
- ho aggiunto un primo greedy meshing reale sulle superfici superiori esposte in prima persona
- le top faces adiacenti dello stesso tipo vengono fuse in rettangoli piu grandi prima della proiezione
- ho aggiunto una ambient occlusion leggera sulle superfici greedy, basata sui blocchi piu alti attorno ai bordi
- ho esteso il greedy meshing anche a bottom faces e facce laterali esposte
- il renderer in prima persona non disegna piu le facce laterali per-blocco
- ho aggiunto una cache mesh per chunk nel renderer in prima persona
- `World` ora mantiene una revision per chunk e marca dirty il chunk modificato piu eventuali chunk confinanti
- quando piazzi, rimuovi, carichi o svuoti blocchi, le mesh dei chunk interessati vengono ricostruite automaticamente
- ho aggiornato il README per chiarire che il greedy completo e la cache dirty sono attivi in prima persona
- dopo il primo test, il gioco laggava perche Java2D proiettava, clippava, allocava e ordinava troppe facce greedy ogni frame
- ho ridotto il raggio di rendering in prima persona da 18 a 14 celle
- ho aggiunto culling economico per singola faccia mesh prima della proiezione Java2D
- ho spostato il calcolo dell'ambient occlusion dentro la cache del chunk, quindi non viene piu ricalcolato ogni frame

File e linee chiave:
- `java/src/blockforge/World.java:7` dimensione chunk 8x8
- `java/src/blockforge/World.java:56-80` recupero dei chunk vicini e bounding box del chunk
- `java/src/blockforge/World.java:278-285` record `WorldChunk`
- `java/src/blockforge/IsometricWorldRenderer.java:29` rendering isometrico basato sui chunk
- `java/src/blockforge/FirstPersonWorldRenderer.java:23-25` culling dei chunk in prima persona
- `java/src/blockforge/FirstPersonWorldRenderer.java:109-129` test conservativo a cono sulla camera
- `java/src/blockforge/GreedyMesher.java:10-69` costruzione greedy delle top faces
- `java/src/blockforge/FirstPersonWorldRenderer.java:34-49` inserimento delle superfici greedy nel rendering
- `java/src/blockforge/FirstPersonWorldRenderer.java:145-169` ambient occlusion leggera sulle top faces
- `java/src/blockforge/GreedyMesher.java:10-18` costruzione della mesh greedy completa del chunk
- `java/src/blockforge/GreedyMesher.java:137-245` greedy meshing delle facce est/ovest
- `java/src/blockforge/GreedyMesher.java:247-356` greedy meshing delle facce nord/sud
- `java/src/blockforge/FirstPersonWorldRenderer.java:21-22` cache mesh per chunk
- `java/src/blockforge/FirstPersonWorldRenderer.java:95-103` ricostruzione cache solo se la revision del chunk cambia
- `java/src/blockforge/World.java:88-89` revision dei chunk
- `java/src/blockforge/World.java:233-259` invalidazione dirty del chunk modificato e dei vicini
- `java/src/blockforge/FirstPersonWorldRenderer.java:20-21` raggio prima persona ridotto e soglia di culling facce
- `java/src/blockforge/FirstPersonWorldRenderer.java:133-152` culling distanza/cone prima della proiezione
- `java/src/blockforge/GreedyMesher.java:380-426` colore e ambient occlusion calcolati nella mesh cached

Nota script video:
- "Prima ho diviso il mondo in chunk, poi ho iniziato a fonderne le superfici: non piu una faccia per ogni blocco visibile, ma rettangoli piu grandi, filtrati dalla camera e leggermente scuriti dove il mondo crea ombra."

## Parte 5 - Collisioni e bordi del personaggio

Richiesta:
- ripartire dalla Parte 5 secondo la nuova numerazione dei video
- risolvere il problema del player che a volte resta bloccato nel vuoto
- definire meglio gli oggetti nello spazio
- evitare conflitti tra bordi del player, blocchi e vuoto

Cosa ho fatto:
- ho individuato il problema principale: la gravita e lo step cercavano supporto usando solo la cella centrale del player
- ho sostituito quel controllo con un supporto basato sull'intera impronta del corpo
- ora i piedi del player controllano tutti i blocchi realmente sovrapposti al raggio del personaggio
- se sotto l'AABB del player non c'e un blocco reale, il gioco non inventa piu un pavimento
- dopo il test, il player poteva ancora restare appeso se una piccola parte dell'impronta toccava il blocco di partenza
- ho stretto la regola: per essere a terra serve un blocco sotto il centro dei piedi e una superficie minima reale sotto l'impronta
- questo impedisce l'effetto "corda invisibile" con il blocco da cui il player si e buttato
- il bug era ancora presente perche la caduta usava `canOccupy(nextY)` come freno generico
- quel controllo poteva fermare la gravita anche quando il player sfiorava lateralmente il blocco di partenza
- ho separato atterraggio e collisione laterale: durante la discesa si atterra solo con un supporto valido sotto i piedi
- dopo questa correzione il player poteva rimanere incastrato perche `canOccupy` controllava anche un volume camera piu grande del corpo
- ho separato la camera dalla fisica: il movimento ora dipende solo dall'AABB reale del corpo del player
- rimaneva un blocco nello step-up: per salire di un livello il centro del player e ancora sulla cella vecchia quando il bordo del corpo tocca il blocco nuovo
- il sistema con area minima non era abbastanza stabile e continuava a generare casi strani
- ho semplificato la fisica: la caduta usa supporto sotto il centro dei piedi, mentre lo step prova ad alzare il corpo e lascia poi alla gravita il riappoggio
- avevo aggiunto un piccolo unstuck automatico, ma al bordo dei blocchi causava rimbalzi indesiderati
- ho rimosso l'unstuck automatico: una normale collisione laterale non deve mai trasformarsi in una spinta verticale
- al bordo di un blocco lo step poteva attivarsi a ogni frame e causare un saltellamento rapido
- ho aggiunto un controllo di ostacolo salibile: lo step parte solo se davanti c'e davvero un blocco entro altezza step
- il saltellamento al bordo e stato affrontato rimuovendo la spinta verticale automatica
- quando il player scendeva da un blocco poteva fare un piccolo salto perche lo step aggiungeva sempre `STEP_HEIGHT`
- ho sostituito lo step fisso con uno step snap: il player sale esattamente alla quota superiore del blocco davanti
- per scelta di design, l'auto-step non deve essere sempre attivo
- ho reso l'auto-step una impostazione opzionale, disattivata di default
- ho aggiunto un pulsante nel menu pausa per attivare/disattivare Auto-step
- l'impostazione viene salvata e caricata insieme alla partita
- quando il player entrava in mezzo agli angoli tra due blocchi poteva bloccarsi
- ho aggiunto un corner slide: se il movimento principale e bloccato, il corpo prova un piccolo scorrimento laterale sull'asse libero
- lo slide viene provato prima dell'auto-step, cosi gli angoli non vengono risolti con salti o salite automatiche
- ho uniformato gli epsilon di collisione per evitare conflitti quando il player e esattamente sul bordo di un blocco
- il piazzamento dentro al player e il test di occupazione usano lo stesso margine fisico
- ho aggiornato il README per rimuovere il limite vecchio della collisione centrata su una sola cella
- il problema rimasto era ancora nella caduta: il corpo poteva entrare lateralmente nel bordo del blocco e poi restare compenetrato
- ho aggiunto una risoluzione orizzontale post-caduta: se l'AABB del player interseca un blocco, viene spinta fuori solo su X/Z
- questa correzione non cambia la quota Y, quindi non reintroduce il salto automatico o il rimbalzo al bordo
- la separazione viene ripetuta per pochi step, cosi funziona anche negli angoli tra piu blocchi
- il resolver AABB non era sufficiente: un corpo quadrato puo ancora agganciarsi agli angoli dei voxel durante la caduta
- ho rifatto la logica del volume fisico del player come cilindro verticale: altezza su Y, impronta circolare su X/Z
- `canOccupy`, step opzionale, piazzamento blocchi e anti-incastro usano tutti la stessa impronta circolare
- la risoluzione dei bordi ora e cerchio-vs-blocco: quando il player entra nel lato o nell'angolo, viene spinto fuori lungo la normale corretta
- se piu blocchi tengono il player incastrato, dopo le spinte iterative il gioco cerca la posizione libera piu vicina sul piano X/Z
- la correzione anti-incastro viene eseguita anche prima del movimento, quindi uno stato sporco non blocca i comandi del frame successivo

File e linee chiave:
- `java/src/blockforge/GamePanel.java:45-51` raggio fisico, epsilon, iterazioni e fallback anti-incastro
- `java/src/blockforge/GamePanel.java:207` correzione anti-incastro prima del movimento
- `java/src/blockforge/GamePanel.java:334-386` movimento X/Z, corner slide e auto-step opzionale
- `java/src/blockforge/GamePanel.java:395-426` step opzionale basato sulla stessa impronta circolare
- `java/src/blockforge/GamePanel.java:432-460` gravita con separazione dei bordi dopo caduta o atterraggio
- `java/src/blockforge/GamePanel.java:463-471` supporto verticale basato sul centro dei piedi
- `java/src/blockforge/GamePanel.java:476-589` depenetrazione orizzontale cerchio-vs-blocco e ricerca della posizione libera piu vicina
- `java/src/blockforge/GamePanel.java:744-747` piazzamento blocchi contro il volume fisico cilindrico del player
- `java/src/blockforge/GamePanel.java:876-950` pulsante e toggle Auto-step nel menu pausa
- `java/src/blockforge/GamePanel.java:1045-1090` `canOccupy` basato su cilindro verticale
- `java/src/blockforge/SaveGame.java` persistenza di `settings.autoStep`

Nota script video:
- "Quando il corpo entra in un angolo non deve restare inchiodato: prima prova a scivolare lateralmente, poi solo se serve valuta lo step opzionale."
- "Durante la caduta non uso piu una collisione verticale generica che appende il player; se entra nel bordo, lo separo lateralmente dal blocco."
- "Il player non e piu un cubo invisibile: per la fisica lo tratto come un cilindro, cosi gli angoli dei voxel non lo agganciano mentre cade."
