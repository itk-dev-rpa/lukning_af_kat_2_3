import urllib
import requests
import uuid
import re

from itk_dev_shared_components.kmd_nova.authentication import NovaAccess
from itk_dev_shared_components.kmd_nova import nova_tasks


def get_cases(nova_access: NovaAccess):
    """Get cases from Nova and return those matching the regex."""
    payload = {
        "common": {
            "transactionId": str(uuid.uuid4())
        },
        "caseAttributes": {
            "title": "Kat 2",
        },
        "caseGetOutput": {
            "caseAttributes": {
                "title": True,
                "userFriendlyCaseNumber": True
            },
            "state": {
                "progressState": True,
                "activeCode": True
            },
            "journalNotes": {
                "journalNoteAttributes": {
                    "title": True
                }
            },
            "caseParty": {
                "identificationType": True,
                "identification": True,
                "name": True
            },
            "numberOfDocuments": True,

        },
        "paging": {
            "startRow": 1,
            "numberOfRows": 500,
            "calculateTotalNumberOfRows": True
        }
    }
    params = {"api-version": "2.0-Case"}
    headers = {'Content-Type': 'application/json', 'Authorization': f"Bearer {nova_access.get_bearer_token()}"}
    regex = re.compile("^Kat\\.?\\s[23]")

    matching_cases = []
    more_cases = True
    url = urllib.parse.urljoin(nova_access.domain, "api/Case/GetList")
    start_row = 1
    while more_cases:
        paging = {
                "startRow": start_row,
                "numberOfRows": 500,
                "calculateTotalNumberOfRows": True
        }
        payload["paging"] = paging
        response = requests.put(url, params=params, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        more_cases = response.json()["pagingInformation"]['hasMoreRows']
        new_cases = response.json()["cases"]
        new_cases = [case for case in new_cases if regex.match(case["caseAttributes"]["title"]) and case['state']['progressState'] != "Afsluttet"]
        matching_cases.extend(new_cases)
        start_row += 500
    return matching_cases


def set_task_state(case_uuid, state, nova_access):
    nova_tasks.update_task()
    return None