# The Main Scraper integration

Questa cartella contiene il contratto tra il runtime degli agenti e il progetto
esterno presente in `projects/main-scraper`.

- `adapter.json` definisce runtime, azioni consentite, parametri e livello di rischio.
- Il codice dello scraper resta indipendente e versionato come Git submodule.
- Database, profili Chrome, output e log restano nel submodule e non sono tracciati.
- Il gateway deve costruire gli argomenti come lista, senza concatenare stringhe shell.
- I percorsi ricevuti devono risolversi dentro il progetto o in directory esplicitamente autorizzate.
- Le azioni con `requiresApproval` non possono essere avviate autonomamente dagli agenti.

Le impostazioni specifiche della macchina, come il percorso di un venv esistente,
vivono in `config/projects.local.json`. Il file e ignorato da Git e sovrascrive i
valori del registro condiviso senza introdurre percorsi assoluti nei commit.

## Aggiornamento del progetto

```powershell
git submodule update --remote projects/main-scraper
```

## Primo checkout del gioco

```powershell
git submodule update --init --recursive
```
