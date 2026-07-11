# The Main Scraper integration

Questa cartella contiene il contratto tra il runtime degli agenti e il progetto
esterno presente in `projects/main-scraper`.

- `adapter.json` definisce runtime, azioni consentite, parametri e livello di rischio.
- `botasaurus_bridge.py` espone una sessione browser Botasaurus come protocollo JSONL.
- `requirements.txt` contiene le dipendenze Python minime per usare lo scraper da macOS.
- Il codice dello scraper resta indipendente e versionato come Git submodule.
- Database, profili Chrome, output e log restano nel submodule e non sono tracciati.
- Il gateway deve costruire gli argomenti come lista, senza concatenare stringhe shell.
- I percorsi ricevuti devono risolversi dentro il progetto o in directory esplicitamente autorizzate.
- Le azioni con `requiresApproval` non possono essere avviate autonomamente dagli agenti.

Le impostazioni specifiche della macchina, come il percorso di un venv esistente,
vivono in `config/projects.local.json`. Il file e ignorato da Git e sovrascrive i
valori del registro condiviso senza introdurre percorsi assoluti nei commit.

## Bridge browser live

Il Project Gateway usa `adapter.json` per job batch. Il controllo browser live usa
invece `botasaurus_bridge.py`, avviato dal runtime come subprocess dentro
`projects/main-scraper`.

Protocollo:

- stdin: una riga JSON per comando, con `id`, `command` e `parameters`.
- stdout: una riga JSON per risposta, con lo stesso `id`, `ok` e `result`.
- il primo messaggio stdout e `{"type": "ready", ...}`.

Comandi supportati:

- `current_url`
- `goto`
- `click_text`
- `click_selector`
- `type`
- `extract`
- `snapshot`
- `screenshot`
- `close`

I test end-to-end del runtime usano un bridge mock con lo stesso protocollo, così
non richiedono Chrome/Botasaurus durante la CI locale.

## Setup macOS

Dalla root del progetto principale:

```bash
scripts/setup_macos.sh
```

Lo script crea `projects/main-scraper/.venv`, installa `requirements.txt` di questa
integrazione e scrive `config/projects.local.json` con il path assoluto del Python
dello scraper. Questo e il path usato sia dal Project Gateway batch sia dal browser
control live.

## Aggiornamento del progetto

```powershell
git submodule update --remote projects/main-scraper
```

## Primo checkout del gioco

```powershell
git submodule update --init --recursive
```
