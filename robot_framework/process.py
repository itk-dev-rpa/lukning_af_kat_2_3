"""This module contains the main process of the robot."""

import os
import csv
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List

import requests
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection

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
    address_in_nova: bool
    num_tasks: int
    deadline: str
    deadline_passed: bool
    action_taken: str
    warnings: str
    timestamp: str


# pylint: disable-next=unused-argument
def process(
    orchestrator_connection: OrchestratorConnection,
    dry_run: bool = False,
) -> None:
    """Do the primary process of the robot.

    Args:
        orchestrator_connection: Connection to the orchestrator
        queue_element: Optional queue element
        dry_run: If True, only generates report without making changes to cases
    """
    orchestrator_connection.log_trace(
        f"Running process in {'DRY RUN' if dry_run else 'PRODUCTION'} mode."
    )
    nova_creds = orchestrator_connection.get_credential(config.NOVA_API)
    nova_access = NovaAccess(nova_creds.username, nova_creds.password)
    itk_dev_event_log.setup_logging(
        orchestrator_connection.get_constant(config.EVENT_LOG_CONN).value
    )

    cases = nova_api.get_cases(nova_access)
    num_closed = 0
    report_data: List[CaseReport] = []

    for case in cases:
        cpr = case["caseParties"][0]["identification"]
        case_number = case["caseAttributes"]["userFriendlyCaseNumber"]
        case_id = case["common"]["uuid"]

        nova_address_found, warnings, nova_check_failed = _check_nova_address_with_retry(
            cpr, nova_access
        )
        if nova_check_failed:
            _append_report(
                report_data,
                case_number=case_number,
                cpr=cpr,
                case_id=case_id,
                address_in_nova=False,
                num_tasks=0,
                deadline="Unknown - Nova check failed",
                deadline_passed=False,
                action_taken="SKIPPED - Nova check failed",
                warnings=warnings,
            )
            continue

        # Tasks and deadline
        tasks = [
            task for task in nova_tasks.get_tasks(case_id, nova_access) if not task.closed_date
        ]
        deadline_has_passed = True
        deadline_str = "No deadline set"
        if tasks:
            # Sort tasks by deadline (newest first)
            tasks_sorted = sorted(
                tasks,
                key=lambda t: t.deadline
                if t.deadline
                else datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo),
                reverse=True,
            )
            task = tasks_sorted[0]
            deadline_has_passed = bool(task.deadline and task.deadline < datetime.now(task.deadline.tzinfo))
            deadline_str = task.deadline.isoformat() if task.deadline else "No deadline"

        # If deadline not passed, just report and continue
        if not deadline_has_passed:
            warnings.append("Deadline has not yet passed")
            _append_report(
                report_data,
                case_number=case_number,
                cpr=cpr,
                case_id=case_id,
                address_in_nova=nova_address_found,
                num_tasks=len(tasks),
                deadline=deadline_str,
                deadline_passed=False,
                action_taken="SKIPPED - Deadline not passed",
                warnings=warnings,
            )
            continue

        # Close or report depending on address state
        if nova_address_found:
            num_closed += 1
            if not dry_run:
                # Close ALL tasks on the case in one go
                nova_api.set_case_tasks_state(tasks, case_id, "Færdig", nova_access)
                # Add a note to a case
                nova_notes.add_text_note(
                    case_id,
                    "RPA: Adresse registreret, sagen lukkes.",
                    "Adresse registreret på CPR-nummer.",
                    config.CASEWORKER,
                    True,
                    nova_access,
                )
                # Set case state to completed
                nova_cases.set_case_state(case_id, "Afsluttet", nova_access)
                itk_dev_event_log.emit(
                    orchestrator_connection.process_name, f"Case {case_number} closed."
                )
        else:
            _append_report(
                report_data,
                case_number=case_number,
                cpr=cpr,
                case_id=case_id,
                address_in_nova=nova_address_found,
                num_tasks=len(tasks),
                deadline=deadline_str,
                deadline_passed=False,
                action_taken="NOT CLOSED - No address registered",
                warnings=warnings,
            )

    if dry_run:
        generate_report(report_data)


def generate_report(report_data: List[CaseReport]) -> None:
    """Generate a CSV report of the cases."""
    report_filename = f"case_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    report_path = os.path.join(os.getcwd(), report_filename)

    with open(report_path, 'w', newline='', encoding='utf-8') as csvfile:
        if report_data:
            fieldnames = list(asdict(report_data[0]).keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for report in report_data:
                writer.writerow(asdict(report))


def _check_nova_address_with_retry(cpr: str, nova_access: NovaAccess, retries: int = 10) -> tuple[bool, list[str], bool]:
    """Check Nova for an address with simple retry logic.

    Returns a tuple: ``(nova_address_found, warnings, nova_check_failed)``.
    If the check fails for all retries, ``nova_address_found`` will be ``False`` and
    ``nova_check_failed`` will be ``True``.
    """
    warnings: list[str] = []
    nova_check_failed = False
    nova_address_found = False

    for _ in range(retries):
        try:
            nova_address = nova_cpr.get_address_by_cpr(cpr, nova_access)
            nova_address_found = (
                "address" in nova_address
                and (
                    "addressLine3" not in nova_address["address"]
                    or nova_address["address"]["addressLine3"] != "9999 Ukendt"
                )
            )
            nova_check_failed = False
            break
        except requests.RequestException as exc:  # network / API issue
            nova_check_failed = True
            warnings.append(f"Nova check failed: {exc}")

    return nova_address_found, warnings, nova_check_failed


def _append_report(
    report_data: List[CaseReport],
    *,
    case_number: str,
    cpr: str,
    case_id: str,
    address_in_nova: bool,
    num_tasks: int,
    deadline: str,
    deadline_passed: bool,
    action_taken: str,
    warnings: list[str],
) -> None:
    """Create a ``CaseReport`` entry and append it to ``report_data``."""
    report_data.append(
        CaseReport(
            case_number=case_number,
            cpr=cpr,
            case_id=case_id,
            address_in_nova=address_in_nova,
            num_tasks=num_tasks,
            deadline=deadline,
            deadline_passed=deadline_passed,
            action_taken=action_taken,
            warnings="; ".join(warnings),
            timestamp=datetime.now().isoformat(),
        )
    )


if __name__ == "__main__":
    from uuid import uuid4
    conn_string = os.getenv("OpenOrchestratorConnString")
    crypto_key = os.getenv("OpenOrchestratorKey")
    oc = OrchestratorConnection("Lukning af Kat 2-3 test", conn_string, crypto_key, '', "", uuid4())

    process(oc, dry_run=True)
