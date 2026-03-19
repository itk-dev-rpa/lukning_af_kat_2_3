"""This module contains the main process of the robot."""

import os
import pyodbc
from datetime import datetime

from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueElement

from itk_dev_shared_components.kmd_nova import nova_tasks, nova_cases, nova_notes
from itk_dev_shared_components.kmd_nova import cpr as nova_cpr
from itk_dev_shared_components.kmd_nova.authentication import NovaAccess
import itk_dev_event_log

from robot_framework.custom import nova_api
from robot_framework import config


# pylint: disable-next=unused-argument
def process(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement | None = None) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")
    nova_creds = orchestrator_connection.get_credential(config.NOVA_API)
    nova_access = NovaAccess(nova_creds.username, nova_creds.password)
    itk_dev_event_log.setup_logging(orchestrator_connection.get_constant(config.EVENT_LOG_CONN).value)

    cases = nova_api.get_cases(nova_access)
    cases_with_duplicate_tasks = []
    cases_without_tasks = []
    num_closed = 0
    num_deadline_close =0
    for case in cases:
        cpr = case['caseParties'][0]['identification']
        address_found_in_database = is_person_registered_on_address(cpr)
        nova_address_found = address_found_in_database
        for _ in range(10):
            try:
                # Nova is unreliable, sometimes we get an error on requests. However, Nova is more up to date.
                # We expect a change in the database is enough to warrant closing the case, while Nova may contain newer data.
                # It is unknown if the data in the database may be unreliable for closing a case. It may be very old, according to sources.
                nova_address_found = nova_cpr.get_address_by_cpr(cpr, nova_access)["address"]["addressLine3"] != "9999 Ukendt"
                break
            except:
                print("WE HAD AN ERROR ON CASE " + case["caseAttributes"]["userFriendlyCaseNumber"])

        if (nova_address_found != address_found_in_database):
            print("SOMETHING IS WRONG")
        case_id = case["common"]["uuid"]
        tasks = [task for task in nova_tasks.get_tasks(case_id, nova_access) if not task.closed_date]
        if len(tasks) > 1:  # Debug
            print("More than one task found")
            cases_with_duplicate_tasks.append(case)
        if len(tasks) == 0:
            print("No tasks found")
            cases_without_tasks.append(case)
            # raise AssertionError("More than one open task found. Must investigate.")
        for task in tasks:
            # If we should handle cases with more than one task, how do we identify the correct one?
            deadline_has_passed = task.deadline and task.deadline > datetime.now(task.deadline.tzinfo)
            if (deadline_has_passed):
                print("Case deadline is passed. " + case["caseAttributes"]["userFriendlyCaseNumber"])
                # break
            # Handle task
            if address_found_in_database:  # and not deadline_has_passed:
                if deadline_has_passed:  # Debug
                    num_deadline_close += 1
                else:
                    num_closed += 1
                    # Close case
                    print("Closing case " + case["caseAttributes"]["userFriendlyCaseNumber"])
                break  # Debug
                # Close task
                nova_cases.set_case_state(case_id, "Afsluttet", nova_access)
                nova_notes.add_text_note(case_id, "RPA: Adresse registreret, sagen lukkes.", "Adresse registreret på CPR-nummer.", )
                # Add case note
                itk_dev_event_log.emit(orchestrator_connection.process_name, "Person has an address registered, case closed.")
            else:
                print("Not closing case " + case["caseAttributes"]["userFriendlyCaseNumber"])
                break
                itk_dev_event_log.emit(orchestrator_connection.process_name, "Person does not have an address registered.")
                # Probably a need to tell someone
            print(task)
    print(f"\n{len(cases)} handled, {num_closed} tasks has been closed. {num_deadline_close} would be closed but has passed deadline.")
    print("Duplicate cases:")
    print([case["caseAttributes"]["userFriendlyCaseNumber"] for case in cases_with_duplicate_tasks])
    print("Cases without tasks:")
    print([case["caseAttributes"]["userFriendlyCaseNumber"] for case in cases_without_tasks])


def is_person_registered_on_address(cpr: str) -> bool:
    """Check if a person is registered at an address."""
    # Maybe use a lookup in Nova
    query = f"SELECT * FROM [DWH].[Mart].[AdresseAktuel] WHERE Vejkode IN (9902, 9901) AND CPR = '{cpr}'"
    connection = pyodbc.connect(config.SQL_CONN)
    cursor = connection.cursor()
    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()
    return len(data) == 0 or len(data[0][20]) == 0


if __name__ == "__main__":
    conn_string = os.getenv("OpenOrchestratorConnString")
    crypto_key = os.getenv("OpenOrchestratorKey")
    oc = OrchestratorConnection("Lukning af Kat 2-3 test", conn_string, crypto_key, '', "")
    process(oc)
