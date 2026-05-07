"""This module contains configuration constants used across the framework"""
from itk_dev_shared_components.kmd_nova.nova_objects import Caseworker

# The number of times the robot retries on an error before terminating.
MAX_RETRY_COUNT = 3

# Whether the robot should be marked as failed if MAX_RETRY_COUNT is reached.
FAIL_ROBOT_ON_TOO_MANY_ERRORS = True

# Error screenshot config
SMTP_SERVER = "smtp.adm.aarhuskommune.dk"
SMTP_PORT = 25
SCREENSHOT_SENDER = "robot@friend.dk"

# Constant/Credential names
ERROR_EMAIL = "Error Email"
NOVA_API = "Nova API"
EVENT_LOG_CONN = "Event Log"


# Queue specific configs
# ----------------------

# The name of the job queue (if any)
QUEUE_NAME = None

# The limit on how many queue elements to process
MAX_TASK_COUNT = 100

# ----------------------

CASEWORKER = Caseworker(
    name='Rpabruger Rpa94 - MÅ IKKE SLETTES RITM0',
    ident='AZRPA94',
    uuid='a577c0a2-a131-43a5-b4e6-b4f5bb75028f',
    type='group'
)
