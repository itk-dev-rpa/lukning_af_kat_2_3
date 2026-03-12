"""This module contains the main process of the robot."""

import os
from datetime import datetime

from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueElement

from itk_dev_shared_components.kmd_nova import nova_tasks
from itk_dev_shared_components.kmd_nova.authentication import NovaAccess

from robot_framework.custom import nova_api
from robot_framework import config


# pylint: disable-next=unused-argument
def process(orchestrator_connection: OrchestratorConnection, queue_element: QueueElement | None = None) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")
    nova_creds = orchestrator_connection.get_credential(config.NOVA_API)
    nova_access = NovaAccess(nova_creds.username, nova_creds.password)
    cases = nova_api.get_cases(nova_access)
    for case in cases:
        tasks = nova_tasks.get_tasks(case["common"]["uuid"], nova_access)
        for task in tasks:
            if not tasks[0].closed_date and tasks[0].deadline > datetime.now(tasks[0].deadline.tzinfo):
                # Handle task
                print(task)


def is_person_registered_on_address():
    return False


if __name__ == "__main__":
    conn_string = os.getenv("OpenOrchestratorConnString")
    crypto_key = os.getenv("OpenOrchestratorKey")
    oc = OrchestratorConnection("Lukning af Kat 2-3 test", conn_string, crypto_key, '', "")
    process(oc)
