"""This module contains the main process of the robot."""

import os
import csv
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List

import pyodbc
import requests
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueElement

from itk_dev_shared_components.kmd_nova import nova_tasks, nova_cases, nova_notes
from itk_dev_shared_components.kmd_nova import cpr as nova_cpr
from itk_dev_shared_components.kmd_nova.authentication import NovaAccess
import itk_dev_event_log

from robot_framework.custom import nova_api
from robot_framework import config


# pylint: disable=too-many-instance-attributes
@dataclass
class CaseReport:
    """Report data for a single case."""
    case_number: str
    cpr: str
    case_id: str
    address_in_database: bool
    address_in_nova: bool
    data_mismatch: bool
    num_tasks: int
    deadline: str
    deadline_passed: bool
    action_taken: str
    warnings: str
    timestamp: str


# pylint: disable-next=unused-argument
def process(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement | None = None, dry_run: bool = False) -> None:
    """Do the primary process of the robot.

    Args:
        orchestrator_connection: Connection to the orchestrator
        queue_element: Optional queue element
        dry_run: If True, only generates report without making changes to cases
    """
    orchestrator_connection.log_trace(f"Running process in {'DRY RUN' if dry_run else 'PRODUCTION'} mode.")
    nova_creds = orchestrator_connection.get_credential(config.NOVA_API)
    nova_access = NovaAccess(nova_creds.username, nova_creds.password)
    itk_dev_event_log.setup_logging(orchestrator_connection.get_constant(config.EVENT_LOG_CONN).value)

    cases = nova_api.get_cases(nova_access)
    cases_with_data_mismatch = []
    num_closed = 0
    report_data: List[CaseReport] = []

    for case in cases:
        cpr = case['caseParties'][0]['identification']
        case_number = case['caseAttributes']['userFriendlyCaseNumber']
        case_id = case["common"]["uuid"]
        address_found_in_database = is_person_registered_on_address(cpr)
        nova_address_found = address_found_in_database
        nova_check_failed = False
        warnings = []

        for _ in range(10):
            try:
                nova_address = nova_cpr.get_address_by_cpr(cpr, nova_access)
                nova_address_found = "address" in nova_address and ("addressLine3" not in nova_address["address"] or nova_address["address"]["addressLine3"] != "9999 Ukendt")
                break
            except requests.RequestException as e:
                nova_check_failed = True
                warnings.append(f"Nova check failed: {e}")

        # Handle data mismatch between database and Nova
        data_mismatch = False
        if not nova_check_failed and (nova_address_found != address_found_in_database):
            cases_with_data_mismatch.append(case)
            data_mismatch = True
            warnings.append(f"Data mismatch - DB: {address_found_in_database}, Nova: {nova_address_found}")

        tasks = [task for task in nova_tasks.get_tasks(case_id, nova_access) if not task.closed_date]
        deadline_has_passed = True
        deadline_str = "No deadline set"
        if tasks:
            # Sort tasks by deadline (newest first) to check the most recent task
            tasks_sorted = sorted(tasks, key=lambda t: t.deadline if t.deadline else datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo), reverse=True)
            task = tasks_sorted[0]

            # Check deadline on the most recent task
            deadline_has_passed = task.deadline and task.deadline < datetime.now(task.deadline.tzinfo)
            deadline_str = task.deadline.isoformat() if task.deadline else "No deadline"

        if not deadline_has_passed:
            warnings.append("Deadline has not yet passed")

            report_data.append(CaseReport(
                case_number=case_number,
                cpr=cpr,
                case_id=case_id,
                address_in_database=address_found_in_database,
                address_in_nova=nova_address_found if not nova_check_failed else None,
                data_mismatch=data_mismatch,
                num_tasks=len(tasks),
                deadline=deadline_str,
                deadline_passed=False,
                action_taken="SKIPPED - Deadline not passed",
                warnings="; ".join(warnings),
                timestamp=datetime.now().isoformat()
            ))
            continue

        # Check for address registration
        if nova_address_found:
            num_closed += 1
            action = "CLOSED" if not dry_run else "WOULD CLOSE"

            if not dry_run:
                # Close ALL tasks on the case in one go
                nova_api.set_case_tasks_state(tasks, case_id, "Færdig", nova_access)

                # Add note to case
                nova_notes.add_text_note(case_id, "RPA: Adresse registreret, sagen lukkes.", "Adresse registreret på CPR-nummer.", config.CASEWORKER, True, nova_access)

                # Set case state to completed
                nova_cases.set_case_state(case_id, "Afsluttet", nova_access)

                itk_dev_event_log.emit(orchestrator_connection.process_name, f"Case {case_number} closed - person has address registered.")

            report_data.append(CaseReport(
                case_number=case_number,
                cpr=cpr,
                case_id=case_id,
                address_in_database=address_found_in_database,
                address_in_nova=nova_address_found if not nova_check_failed else None,
                data_mismatch=data_mismatch,
                num_tasks=len(tasks),
                deadline=deadline_str,
                deadline_passed=False,
                action_taken=action,
                warnings="; ".join(warnings),
                timestamp=datetime.now().isoformat()
            ))
        else:
            report_data.append(CaseReport(
                case_number=case_number,
                cpr=cpr,
                case_id=case_id,
                address_in_database=address_found_in_database,
                address_in_nova=nova_address_found if not nova_check_failed else None,
                data_mismatch=data_mismatch,
                num_tasks=len(tasks),
                deadline=deadline_str,
                deadline_passed=False,
                action_taken="NOT CLOSED - No address registered",
                warnings="; ".join(warnings),
                timestamp=datetime.now().isoformat()
            ))
    # Generate report
    report_filename = f"case_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    report_path = os.path.join(os.getcwd(), report_filename)

    with open(report_path, 'w', newline='', encoding='utf-8') as csvfile:
        if report_data:
            fieldnames = list(asdict(report_data[0]).keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for report in report_data:
                writer.writerow(asdict(report))


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

    process(oc, dry_run=True)
