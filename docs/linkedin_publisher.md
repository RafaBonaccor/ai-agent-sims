# LinkedIn Publisher (MVP)

Il Publisher è nella tab **Reports → LinkedIn**, sotto i post raccolti. Usa il profilo Chrome standard già autenticato, copiato in una sessione temporanea separata dal LinkedIn Agent e dagli altri browser del progetto. Non servono API key LinkedIn.

1. Scrivi una bozza originale oppure scegli **Prepara pubblicazione** su una riscrittura.
2. Rileggi il testo, salva le eventuali modifiche e premi **Rivedi e pubblica**.
3. Digita `PUBBLICA` nella conferma. Solo allora il Publisher apre LinkedIn e tenta l'invio.

Questo MVP pubblica **solo testo** sul profilo personale presente nel Chrome standard. Immagini, video, pagine aziendali e pubblicazione programmata non sono inclusi. Non pubblica automaticamente i post scoperti o le bozze generate.

Il browser controlla che il composer contenga esattamente il testo approvato. Cerca un unico pulsante di pubblicazione e poi una conferma visibile di LinkedIn. Se il clic potrebbe essere partito ma la conferma manca (timeout, rete instabile, DOM cambiato), marca la bozza `unknown` e blocca il riinvio: controlla manualmente il profilo prima di creare un'altra bozza. Un errore certo prima del clic lascia invece la bozza modificabile.

Lo storico locale è in `data/linkedin_publisher.db`. Non contiene cookie o password. I log non stampano il testo della bozza. L'automazione del DOM può rompersi quando LinkedIn cambia interfaccia; i test coprono la logica, ma non possono dimostrare una pubblicazione reale senza eseguire un invio.
