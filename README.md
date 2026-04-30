# Lukning af Kat 2–3 – Robot

Dette projekt er en robot, der hjælper med at lukke sager i KMD Nova for kategorierne "Kat 2" og "Kat 3", når borgeren er registreret på en adresse.

Robotten:
- Finder relevante sager i Nova (titel matcher `Kat 2` eller `Kat 3`, og som ikke allerede er afsluttede)
- Slår adresse op via Nova CPR-service
- Hvis der er adresse registreret, og deadline er overskredet, så:
  - Lukker alle tilknyttede opgaver på sagen (bulk-opdatering)
  - Tilføjer en journalnote
  - Lukker sagen (sætter sagsstatus til "Afsluttet")
- Understøtter sikker "dry-run" (ingen ændringer i Nova; kun CSV-rapport)

## Krav
- Python 3.11+
- Adgang til KMD Novas API (client id/secret)
- Adgang til den anvendte SQL-database til adresseopslag (ODBC-driver 17 til SQL Server)

## Konfiguration
Centrale indstillinger findes i `robot_framework/config.py`:
- `NOVA_API`: Navnet på legitimationssættet i OpenOrchestrator (client id/secret)
- `EVENT_LOG_CONN`: Navn på Event Log-forbindelsen i OpenOrchestrator
- `SQL_CONN`: ODBC-connection string til adresseopslag i DWH
- `CASEWORKER`: Sagsbehandler (bruger/gruppe), som anvendes som afsender på journalnoter

Andre generelle rammeindstillinger (fx `MAX_RETRY_COUNT`) findes i samme fil.

## Sådan virker robotten (overblik)
Den primære logik findes i `robot_framework/process.py`:
1. Henter adgangstoken til Nova via `NovaAccess`
2. Finder sager med titler som matcher "Kat 2/3" (`nova_api.get_cases`)
3. Finder åbne opgaver på sagen og den seneste deadline
4. Hvis deadline er overskredet og borgeren har adresse registreret:
   - Lukker alle opgaver med `nova_api.set_case_tasks_state(..., "Færdig", ...)`
   - Tilføjer journalnote via `nova_notes.add_text_note`
   - Sætter sagen til "Afsluttet" via `nova_cases.set_case_state`
5. Skriver en rapportlinje for hver sag til en CSV-fil i projektmappen ved dryrun

Rapportfilen navngives automatisk som `case_report_YYYYMMDD_HHMMSS.csv` og gemmes i nuværende arbejdsmappe.

## Kørsel lokalt
Der er to måder at køre robotten lokalt på.

1) Kør den specifikke proces i dry-run (ændrer intet i Nova):
```powershell
$env:OpenOrchestratorConnString = "<din-conn-string>"
$env:OpenOrchestratorKey = "<din-krypteringsnøgle>"
python .\robot_framework\process.py --dry-run
```
Flaget `--dry-run` eller `-d` sikrer, at robotten kun genererer rapporten og ikke foretager ændringer i Nova.

2) Kør hele frameworkets entrypoint (som i produktion):
```powershell
python .\main.py
```
`main.py` starter frameworket (lineær flow), som kalder `process()` internt.

## Kørsel i OpenOrchestrator
- Udrul koden som en robot i OpenOrchestrator
- Opret/angiv følgende:
  - Credential: navn som i `config.NOVA_API` med client id/secret til Nova
  - Constant: navn som i `config.EVENT_LOG_CONN` med forbindelsesstreng til event logging
- Robotten forventer ingen kø (lineært flow); `QUEUE_NAME = None`

## Output og logging
- CSV-rapport: `case_report_YYYYMMDD_HHMMSS.csv` i arbejdsbiblioteket
- Event log: initialiseres via `itk_dev_event_log.setup_logging()`

## Sikkerhed og fejlhåndtering
- Nova-kald håndterer HTTP-fejl med `requests.raise_for_status()`
- Netværksfejl mod Nova under adresseopslag genforsøges i op til 10 forsøg per sag
- "Dry-run" anbefales lokalt og for test

## Udviklernoter
- Opgavelukning sker i bulk med `set_case_tasks_state`, som sætter `status_code` og `closed_date` på hver opgave og persisterer via Nova API.
- Flowet bruger lineær ramme (`robot_framework/__main__.py`).
- Strukturen og hjælpefunktioner findes primært i `robot_framework/custom/nova_api.py` og `robot_framework/process.py`.

## Linting og CI
Projektet er sat op til linting (flake8/pylint) via Github Actions. Workflowet kører ved push og ligger i `.github/workflows/Linting.yml` (hvis repoet er forbundet med GitHub Actions).

## Licens
Se `LICENSE` i roden af projektet.
