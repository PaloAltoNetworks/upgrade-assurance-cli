import enum
import datetime
import pathlib
import os
from typing import Annotated

from typer import Typer, Argument, Option

from upgrade_assurance_cli.cli.runner import pooled_run_readiness_checks_on_devices, \
    ReadinessCheckExecutionArgs
from upgrade_assurance_cli.cli.utils import log, load_config

SHORT_HELP_TEXT = """PAN-OS Upgrade Assurance CLI"""

HELP_TEXT = f"""{SHORT_HELP_TEXT}

Provides access to the readiness and snapshot comparison tests via a handy CLI interface.
"""

app = Typer(
    help=HELP_TEXT,
    short_help=SHORT_HELP_TEXT
)

DEVICE_ARGUMENT = Annotated[list[str], Argument(
    help="Device IP or FQDN. If using Panorama to proxy commands, specify in the format <panorama_ip>:<serial>",
)]
USERNAME_OPTION = Annotated[str, Option(
    help="Username",
    envvar="UA_USERNAME",
)]
PASSWORD_OPTION = Annotated[str, Option(
    envvar="UA_PASSWORD",
    help="Password",
)]
CONFIG_OPTION = Annotated[pathlib.Path, Option(
    help="Path To Configuration file",
)]


class LogLevelEnum(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"

@app.callback()
def setup(
    log_level: Annotated[LogLevelEnum, Option()] = LogLevelEnum.INFO
):
    log.setLevel(level=log_level.value)
    log.debug("Debug logging enabled")
    log.info("Informational logging enabled")

@app.command()
def readiness(
        username: USERNAME_OPTION,
        password: PASSWORD_OPTION,
        device: DEVICE_ARGUMENT,
        result_store_path: Annotated[pathlib.Path, Option(help="Path to store the results")] = "store",
        config_path: CONFIG_OPTION = None,
        parallel: Annotated[int, Option(help="Number of concurrent connections to make")] = 2
):
    """Runs the 'readiness' or pre-check upgrade commands"""
    check_config = load_config(config_path).get("pre_checks", {})
    if not check_config:
        log.warning("No explicit readiness checks were given, using library defaults")

    os.makedirs(result_store_path, exist_ok=True)
    exec_args = [
        ReadinessCheckExecutionArgs(
            username=username,
            password=password,
            hostname=d,
            check_configuration=check_config,
            output_file=result_store_path.joinpath(f"readiness_{d}.json".replace(":", "_")),
            serial=None
        ) for d in device
    ]
    pooled_run_readiness_checks_on_devices(exec_args, parallel=parallel)


@app.command()
def snapshot():
    """Takes an operational snapshot"""
    pass
