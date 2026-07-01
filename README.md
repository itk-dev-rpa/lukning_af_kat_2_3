# Lukning af Kat 2–3 – Robot

Dette projekt er en robot, der hjælper med at lukke sager i KMD Nova for kategorierne "Kat 2" og "Kat 3", når borgeren er registreret på en adresse.

Robotten bygger på [itk-dev-rpa/Robot-Framework](https://github.com/itk-dev-rpa/Robot-Framework) (lineært flow). Dette dokument beskriver kun det robot-specifikke — den generelle framework-opsætning (kørsel, entrypoints, retry, linting/CI) er dokumenteret i template-repoet.

## Hvad robotten gør
- Finder relevante sager i Nova (titel matcher `Kat 2` eller `Kat 3`, og som ikke allerede er afsluttede)
- Slår borgerens adresse op via Nova CPR-service
- Hvis adressen er registreret, og opgavens deadline er overskredet, lukkes sagen:
  - Lukker alle tilknyttede opgaver på sagen (bulk-opdatering)
  - Godkender alle ikke-godkendte dokumenter på sagen
  - Sætter sagsstatus til "Afsluttet"
  - Tilføjer en journalnote
- Sender en rapport-mail med de lukkede sager (se "Parametre for kørslen")
- Understøtter "dry-run" (ingen ændringer i Nova; kun CSV-rapport)

## Konfiguration
Robot-specifikke indstillinger i `robot_framework/config.py`:
- `NOVA_API`: Credential-navn i OpenOrchestrator med client id/secret til Nova
- `EVENT_LOG_CONN`: Constant-navn på Event Log-forbindelsen
- `CASEWORKER`: Bruger/gruppe der står som afsender på journalnoter
- `REPORT_SENDER`: Afsender på rapport-mailen om lukkede sager
- `LOAD_PAGING` (100): Antal sager der hentes pr. side ved Nova-opslag

Øvrige konstanter i `config.py` (fx `MAX_RETRY_COUNT`, `SMTP_SERVER`, `QUEUE_NAME`) er generel framework-boilerplate.

## Parametre for kørslen
Robotten forventer `process_arguments` fra OpenOrchestrator som en JSON-streng med:
- `report_receivers` (array af e-mailadresser): Modtagere af rapport-mailen om lukkede sager.

Eksempel:
```json
{
  "report_receivers": ["navn1@aarhus.dk", "navn2@aarhus.dk"]
}
```
Hvis robotten lukker sager uden at `report_receivers` er sat, fejler mail-afsendelsen.

## Sådan virker robotten
Den primære logik findes i `robot_framework/process.py`:
1. Henter adgangstoken til Nova via `NovaAccess`
2. Finder sager der matcher "Kat 2/3" (`nova_api.get_cases`)
3. Slår borgerens adresse op i Nova (genforsøges op til 10 gange ved netværksfejl)
4. Finder åbne opgaver på sagen og den seneste deadline
5. Hvis deadline er overskredet og adressen er registreret, lukkes sagen (`_close_case`): lukker opgaver → godkender dokumenter → sætter status "Afsluttet" → tilføjer journalnote
6. I produktion sendes en rapport-mail til `report_receivers`. Ved dry-run skrives i stedet en CSV-rapport (`case_report_YYYYMMDD_HHMMSS.csv`) i arbejdsmappen

## Kørsel lokalt
```powershell
$env:OpenOrchestratorConnString = "<din-conn-string>"
$env:OpenOrchestratorKey = "<din-krypteringsnøgle>"
python .\robot_framework\process.py
```
Dette kører i produktionstilstand (ændrer sager i Nova). Der findes intet CLI-flag; for at køre i dry-run sættes `dry_run=True` i `__main__`-blokken i `process.py`.

## Kørsel i OpenOrchestrator
Udrul koden som en robot i OpenOrchestrator og angiv:
- Credential: navn som i `config.NOVA_API` (client id/secret til Nova)
- Constant: navn som i `config.EVENT_LOG_CONN` (forbindelse til event logging)
- Process arguments: JSON med `report_receivers` (se "Parametre for kørslen")

## Udviklernoter
- Robot-specifik logik ligger i `robot_framework/process.py`; Nova-hjælpefunktioner i `robot_framework/custom/nova_api.py`
- Opgavelukning sker i bulk med `set_case_tasks_state`, som sætter `status_code` og `closed_date` på hver opgave

## Licens
Se `LICENSE` i roden af projektet.
