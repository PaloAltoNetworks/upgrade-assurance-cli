import enum
import datetime
import pathlib
import os
from typing import Annotated

from typer import Typer, Argument, Option
from rich import print, table

from upgrade_assurance_cli.cli.report import generate_reports_from_store
from upgrade_assurance_cli.cli.runner import pooled_run_readiness_checks_on_devices, \
    CheckExecutionArgs, pooled_run_snapshot_checks_on_devices
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

class FormatEnum(str, enum.Enum):
    cli_table = "cli_table"

@app.command()
def report(
        result_store_path: Annotated[pathlib.Path, Option(help="Location of the results")] = "store",
        format: Annotated[FormatEnum, Option(help="Format for the report")] = FormatEnum.cli_table,
        device: Annotated[str, Option(help="Single device report")] = None
):
    """Read all the check results and generate a report.

    If you store contains multiple reports, and you have passed a device string, this will return the most recent
    check results.
    """
    reports = generate_reports_from_store(result_store_path)

    if format == FormatEnum.cli_table:
        if device:
            print(reports.device_report_as_rich_table(device))
        else:
            print(reports.counts_as_rich_table())
            print(reports.pass_or_fail_as_rich_string())

def get_devices_from_argument(device: list[str]):
    device_list = []
    for d in device:
        if pathlib.Path(d).is_file():
            device_list += parse_file_to_devices(pathlib.Path(d))

    return device_list

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

    device_list = get_devices_from_argument(device)

    os.makedirs(result_store_path, exist_ok=True)
    timestamp = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    log.info(f"Starting readiness check process on {len(device_list)} devices")
    exec_args = [
        CheckExecutionArgs(
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
def snapshot(
        username: USERNAME_OPTION,
        password: PASSWORD_OPTION,
        device: DEVICE_ARGUMENT,
        snapshot_store_path: Annotated[pathlib.Path, Option(help="Path to store the snapshot reports")] = "snapshots",
        config_path: CONFIG_OPTION = None,
        parallel: Annotated[int, Option(help="Number of concurrent connections to make")] = 2
):
    """Takes an operational snapshot of the given devices.

    For each device passed, a snapshot will be taken and saved in the passed snapshot store. This can be then used to
    compare with subsequent snapshots. This command does NOT run any tests, it just pulls the data for later
    processing.
    """
    check_config = load_config(config_path).get("snapshots", {})
    if not check_config:
        check_config = [
            'nics',
            'routes',
            'license',
            'arp_table',
        ]
        log.warning("No explicit snapshot config was given, using library defaults")

    os.makedirs(snapshot_store_path, exist_ok=True)

    device_list = get_devices_from_argument(device)
    timestamp = int(datetime.datetime.now(tz=datetime.UTC).timestamp())

    exec_args = [
        CheckExecutionArgs(
            username=username,
            password=password,
            hostname=d,
            check_configuration=check_config,
            output_file=snapshot_store_path.joinpath(
                f"snapshot_{d}_{timestamp}.json".replace(":", "-")
            ),
        ) for d in device_list
    ]
    pooled_run_snapshot_checks_on_devices(exec_args, parallel=parallel)
    log.info("snapshot process has finished.")