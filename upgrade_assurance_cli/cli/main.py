import enum
import datetime
import pathlib
import os
from typing import Annotated

from typer import Typer, Argument, Option
from rich import print, table

from upgrade_assurance_cli.cli.report import generate_reports_from_store
from upgrade_assurance_cli.cli.runner import pooled_run_readiness_checks_on_devices, \
    ReadinessCheckExecutionArgs
from upgrade_assurance_cli.cli.utils import log, load_config, parse_file_to_devices

SHORT_HELP_TEXT = """PAN-OS Upgrade Assurance CLI"""

HELP_TEXT = f"""{SHORT_HELP_TEXT}

Provides access to the readiness and snapshot comparison tests via a handy CLI interface.
"""

app = Typer(
    help=HELP_TEXT,
    short_help=SHORT_HELP_TEXT
)

DEVICE_ARGUMENT = Annotated[list[str], Argument(
    help="Device IP or FQDN. If using Panorama to proxy commands, specify in the format <panorama_ip>:<serial>. "
         "Multiple are supported at the command line. "
         "Alternatively, a path to a file containing a list of devices - one per line - may be passed.",
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
    """Runs the 'readiness' or pre-check upgrade commands

    This command will generate a consolidated report and print it to the console. For more complex reporting behavior,
    use the `report` command.
    """
    check_config = load_config(config_path).get("pre_checks", {})
    if not check_config:
        log.warning("No explicit readiness checks were given, using library defaults")

    device_list = []
    for d in device:
        if pathlib.Path(d).is_file():
            device_list += parse_file_to_devices(pathlib.Path(d))

    os.makedirs(result_store_path, exist_ok=True)
    timestamp = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    log.info(f"Starting readiness check process on {len(device_list)} devices")
    exec_args = [
        ReadinessCheckExecutionArgs(
            username=username,
            password=password,
            hostname=d,
            check_configuration=check_config,
            output_file=result_store_path.joinpath(
                f"readiness_{d}_{timestamp}.json".replace(":", "-")
            ),
        ) for d in device_list
    ]
    pooled_run_readiness_checks_on_devices(exec_args, parallel=parallel)
    reports = generate_reports_from_store(result_store_path)
    print(reports.counts_as_rich_table())

@app.command()
def snapshot():
    """Takes an operational snapshot"""
    pass
