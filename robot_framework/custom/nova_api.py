"""Convenience wrappers around KMD Nova API calls used by the robot.

This module contains small helper functions for case and task operations.
"""

import uuid
import re
import urllib.parse
from datetime import datetime, timezone

import requests

from itk_dev_shared_components.kmd_nova.authentication import NovaAccess
from itk_dev_shared_components.kmd_nova import nova_tasks
from itk_dev_shared_components.kmd_nova.nova_objects import Task


def get_cases(nova_access: NovaAccess):
    """Get cases from Nova and return those matching the regex."""
    payload = {
        "common": {
            "transactionId": str(uuid.uuid4())
        },
        "caseAttributes": {
            "title": "Kat 2",
        },
        "states": {
            "states": [
                {"progressState": "Opstaaet"},
                {"progressState": "Oplyst"},
                {"progressState": "Afgjort"},
                {"progressState": "Bestilt"},
            ]
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
        new_cases = [case for case in new_cases if regex.match(case["caseAttributes"]["title"])]
        matching_cases.extend(new_cases)
        start_row += 500
    return matching_cases


def set_case_tasks_state(tasks: list[Task], case_uuid: str, state: str, nova_access: NovaAccess) -> None:
    """Set the state on all provided tasks belonging to a case.

    This updates each task's Nova status code (N/S/F) and sets/clears the
    `closed_date` accordingly before persisting the change via the Nova API.

    Args:
        tasks: The tasks to update (typically open tasks on the case).
        case_uuid: The id of the case the tasks belong to.
        state: A human readable state, e.g. "Færdig", "Startet", "Ny".
        nova_access: Access token provider for Nova.
    """
    # Map a few common human-readable states to Nova status codes
    normalized = state.strip().lower()
    if normalized in {"færdig", "faerdig", "ferdig", "finished", "done", "f"}:
        status_code = "F"
    elif normalized in {"startet", "igang", "in progress", "started", "s"}:
        status_code = "S"
    else:
        status_code = "N"

    for t in tasks:
        t.status_code = status_code
        if status_code == "F":
            # Set closed_date when finishing a task
            t.closed_date = datetime.now(timezone.utc)
        else:
            t.closed_date = None

        nova_tasks.update_task(t, case_uuid, nova_access)
