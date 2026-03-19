import enum
import datetime
import json
import pathlib
import os
from typing import Annotated

from panos_upgrade_assurance.snapshot_compare import SnapshotCompare
from typer import Typer, Argument, Option
from rich import print, table

from upgrade_assurance_cli.cli.report import generate_reports_from_store, details_from_filename
from upgrade_assurance_cli.cli.runner import pooled_run_readiness_checks_on_devices, \
    CheckExecutionArgs, pooled_run_snapshot_checks_on_devices
from upgrade_assurance_cli.cli.utils import log, load_config, parse_file_to_devices, ENCODING

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
        device: Annotated[str, Option(help="Device string for single device report")] = None
):
    """Read all the check results and generate a report.

    This command enumerates all the reports in the store and returns a report of all the results, including a timestamp,
    to the CLI.

    Alternatively, you can pass a device string in the same format
    """
    reports = generate_reports_from_store(result_store_path)

    if format == FormatEnum.cli_table:
        if device:
            print(reports.device_readiness_report_as_rich_table(device))
            print(reports.device_snapshot_report_as_rich_table(device))
        else:
            print(reports.counts_as_rich_table())
            print(reports.pass_or_fail_as_rich_string())


def get_devices_from_argument(device: list[str]):
    device_list = []
    for d in device:
        if pathlib.Path(d).is_file():
            device_list += parse_file_to_devices(pathlib.Path(d))
        else:
            device_list.append(d)

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
        check_config = [
            "!planes_clock_sync",
            "!certificates_requirements",
            "!arp_entry_exist",
            "!session_exist",
            "!ip_sec_tunnel_status"
        ]
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
            'session_stats'
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


@app.command()
def snapshot_comparison(
        left: Annotated[pathlib.Path, Argument(help="First snapshot")],
        right: Annotated[pathlib.Path, Argument(help="Second snapshot")],
        config_path: CONFIG_OPTION = None,
        result_store_path: Annotated[pathlib.Path, Option(help="Path to store the results")] = "store",
):
    """Compares the result of two given snapshots and creates a report that can then be read using the 'reports'
    command."""
    report_config = load_config(config_path).get("snapshot_config", {})
    os.makedirs(result_store_path, exist_ok=True)

    if not report_config:
        report_config = [
            {
                'arp_table': {
                    'properties': ['!ttl'],
                    'count_change_threshold': 10
                }
            },
            {
                'routes': {
                    'properties': ['!flags'],
                    'count_change_threshold': 10
                }
            },
            {
                'session_stats': {}

            },
            {
                'license': {}
            }
        ]
        log.warn("No config for comparison was provided - using defaults")

        left_data = json.load(open(left))
        right_data = json.load(open(right))
        comparison = SnapshotCompare(left_data, right_data)

        (_, left_device, left_timestamp) = details_from_filename(str(left))
        (_, right_device, right_timestamp) = details_from_filename(str(right))
        if left_device != right_device:
            log.error(f"{left_device} is not the same as {right_device} - are you comparing the right reports?")

        output_file = result_store_path.joinpath(
            f"snapshotr_{right_device}_{right_timestamp}.json".replace(":", "-")
        )
        result = comparison.compare_snapshots(report_config)
        log.info(f"Saving result to {output_file}")
        json.dump(result, open(output_file, "w", encoding=ENCODING))
