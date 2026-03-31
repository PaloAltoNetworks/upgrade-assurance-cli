import enum
import datetime
import json
import pathlib
import os
from typing import Annotated

from panos_upgrade_assurance.check_firewall import CheckFirewall
from panos_upgrade_assurance.exceptions import SnapshotNoneComparisonException
from panos_upgrade_assurance.snapshot_compare import SnapshotCompare
from panos_upgrade_assurance.utils import ConfigParser
from typer import Typer, Argument, Option
from rich import print, table

from upgrade_assurance_cli.cli.exporter import (
    ExporterArguments,
    pooled_take_config_backup,
    BackupTypeEnum,
)
from upgrade_assurance_cli.cli.report import (
    generate_reports_from_store,
    details_from_filename,
    read_snapshot_report,
    get_snapshot_data_report,
)
from upgrade_assurance_cli.cli.runner import (
    pooled_run_readiness_checks_on_devices,
    CheckExecutionArgs,
    pooled_run_snapshot_checks_on_devices, pooled_run_capacity_checks_on_devices,
)
from upgrade_assurance_cli.cli.utils import (
    log,
    load_config,
    parse_file_to_devices,
    ENCODING,
    TestConfigs,
)

SHORT_HELP_TEXT = """PAN-OS Upgrade Assurance CLI"""

HELP_TEXT = f"""{SHORT_HELP_TEXT}

Provides access to the readiness and snapshot comparison tests via a handy CLI interface.
"""

app = Typer(help=HELP_TEXT, short_help=SHORT_HELP_TEXT)

DEVICE_ARGUMENT = Annotated[
    list[str],
    Argument(
        help="Device IP or FQDN. If using Panorama to proxy commands, specify in the format <panorama_ip>:<serial>. "
        "Multiple are supported at the command line. "
        "Alternatively, a path to a file containing a list of devices - one per line - may be passed.",
    ),
]
USERNAME_OPTION = Annotated[
    str, Option(help="Username", envvar="UA_USERNAME", prompt="username")
]
PASSWORD_OPTION = Annotated[
    str,
    Option(
        envvar="UA_PASSWORD",
        help="Password",
        prompt="password",
        hide_input=True,
    ),
]
CONFIG_OPTION = Annotated[
    pathlib.Path,
    Option(
        help="Path To Configuration file",
    ),
]


class LogLevelEnum(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"


@app.callback()
def setup(log_level: Annotated[LogLevelEnum, Option()] = LogLevelEnum.INFO):
    log.setLevel(level=log_level.value)
    log.debug("Debug logging enabled")
    log.info("Informational logging enabled")


class FormatEnum(str, enum.Enum):
    cli_table = "cli_table"


@app.command()
def report(
    result_store_path: Annotated[
        pathlib.Path, Option(help="Location of the results")
    ] = "store",
    format: Annotated[
        FormatEnum, Option(help="Format for the report")
    ] = FormatEnum.cli_table,
    device: Annotated[
        str, Option(help="Device string for single device report")
    ] = None,
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
            print(reports.device_capacity_report_as_rich_table(device))
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
    result_store_path: Annotated[
        pathlib.Path, Option(help="Path to store the results")
    ] = "store",
    config_path: CONFIG_OPTION = None,
    parallel: Annotated[
        int, Option(help="Number of concurrent connections to make")
    ] = 2,
):
    """Runs the 'readiness' or pre-check upgrade commands

    This command will generate a consolidated report and print it to the console. For more complex reporting behavior,
    use the `report` command.
    """
    check_config = load_config(config_path).pre_checks

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
        )
        for d in device_list
    ]
    pooled_run_readiness_checks_on_devices(exec_args, parallel=parallel)
    reports = generate_reports_from_store(result_store_path)
    if len(device_list) == 1:
        log.info("Only one device was provided - displaying latest results only")
        print(reports.device_readiness_report_as_rich_table(device_list[0]))
        return

    print(reports.counts_as_rich_table())


@app.command()
def snapshot(
    username: USERNAME_OPTION,
    password: PASSWORD_OPTION,
    device: DEVICE_ARGUMENT,
    snapshot_store_path: Annotated[
        pathlib.Path, Option(help="Path to store the snapshot reports")
    ] = "snapshots",
    config_path: CONFIG_OPTION = None,
    parallel: Annotated[
        int, Option(help="Number of concurrent connections to make")
    ] = 2,
):
    """Takes an operational snapshot of the given devices.

    For each device passed, a snapshot will be taken and saved in the passed snapshot store. This can be then used to
    compare with subsequent snapshots. This command does NOT run any tests, it just pulls the data for later
    processing.
    """
    check_config = load_config(config_path).snapshot_config

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
        )
        for d in device_list
    ]
    pooled_run_snapshot_checks_on_devices(exec_args, parallel=parallel)
    log.info(
        f"snapshot process has finished. {len(exec_args)} snapshots saved to {snapshot_store_path}."
    )
    if len(exec_args) == 1:
        print(get_snapshot_data_report(exec_args[0].output_file).data_as_rich_table())


@app.command()
def compare_snapshots(
    left: Annotated[pathlib.Path, Argument(help="First snapshot")],
    right: Annotated[pathlib.Path, Argument(help="Second snapshot")],
    config_path: CONFIG_OPTION = None,
    result_store_path: Annotated[
        pathlib.Path, Option(help="Path to store the results")
    ] = "store",
):
    """Compares the result of two given snapshots and creates a report. The report is saved, but it is also displayed automatically for convenience"""
    report_config = load_config(config_path).snapshot_comparison_config

    os.makedirs(result_store_path, exist_ok=True)
    left_data = json.load(open(left))
    right_data = json.load(open(right))
    comparison = SnapshotCompare(left_data, right_data)

    _, left_device, left_timestamp = details_from_filename(str(left))
    _, right_device, right_timestamp = details_from_filename(str(right))
    if left_device != right_device:
        log.error(
            f"{left_device} is not the same as {right_device} - are you comparing the right reports?"
        )

    output_file = result_store_path.joinpath(
        f"snapshotr_{right_device}_{right_timestamp}.json".replace(":", "-")
    )
    try:
        result = comparison.compare_snapshots(report_config)
        log.info(f"Saving snapshot comparison result to {output_file}.")
        json.dump(result, open(output_file, "w", encoding=ENCODING))

        reports = read_snapshot_report(output_file)
        print(reports.device_snapshot_report_as_rich_table(left_device))
    except SnapshotNoneComparisonException as e:
        log.critical(e)
        print(
            "[bold red]Snapshot comparison is not possible as one, or both, of the snapshots contain null data values."
            " The most likely cause is a device connectivity failure when taking the snapshot data from the device."
            "[/bold red]"
        )


@app.command()
def show_configuration(
    config_path: CONFIG_OPTION = None,
):
    """Displays all the configured tests as they will be run. This is useful to show the defaults for this tool or validate your own provided configuration file."""
    config = load_config(config_path)
    checker = CheckFirewall(None)
    parsed_readiness_config = ConfigParser(
        valid_elements=set(checker._check_method_mapping.keys()),
        requested_config=config.pre_checks,
        explicit_elements=CheckFirewall.EXPLICIT_CHECKS,
    ).prepare_config()

    snaps_list = ConfigParser(
        valid_elements=set(checker._snapshot_method_mapping.keys()),
        requested_config=config.snapshot_config,
    ).prepare_config()

    comparison = SnapshotCompare(None, None)
    parsed_comparison_config = ConfigParser(
        valid_elements=set(comparison._functions_mapping.keys()),
        requested_config=config.snapshot_comparison_config,
    ).prepare_config()

    parsed_config_object = TestConfigs(
        pre_checks=parsed_readiness_config,
        snapshot_config=snaps_list,
        snapshot_comparison_config=parsed_comparison_config,
    )
    print(json.dumps(parsed_config_object.model_dump(), indent=4))


@app.command()
def backup(
    username: USERNAME_OPTION,
    password: PASSWORD_OPTION,
    device: DEVICE_ARGUMENT,
    export_type: Annotated[
        BackupTypeEnum, Option(help="Type of backup to take")
    ] = BackupTypeEnum.configuration,
    backup_path: Annotated[
        pathlib.Path, Option(help="Path to store backups in")
    ] = "backups",
    parallel: Annotated[
        int, Option(help="Number of concurrent connections to make")
    ] = 2,
):
    """Backup the configuration of one or more devices to the provided backup_path."""
    os.makedirs(backup_path, exist_ok=True)

    device_list = get_devices_from_argument(device)
    timestamp = int(datetime.datetime.now(tz=datetime.UTC).timestamp())

    exec_args = [
        ExporterArguments(
            username=username,
            password=password,
            hostname=d,
            output_file=backup_path.joinpath(
                f"backup_{d}_{timestamp}".replace(":", "-")
            ),
            export_type=export_type,
        )
        for d in device_list
    ]
    log.info(f"Taking {export_type} backups of {len(exec_args)} devices")
    pooled_take_config_backup(exec_args, parallel=parallel)


@app.command()
def version():
    """Show the version of this script, then exit"""
    from upgrade_assurance_cli import __version__

    print(
        f"Upgrade Assurance CLI version [bold bright_magenta]{__version__}[/bold bright_magenta]"
    )


@app.command()
def capacity(
    username: USERNAME_OPTION,
    password: PASSWORD_OPTION,
    device: DEVICE_ARGUMENT,
    store_path: Annotated[
        pathlib.Path, Option(help="Path to store the resultant capacity reports")
    ] = "store",
    parallel: Annotated[
        int, Option(help="Number of concurrent connections to make")
    ] = 2,
):
    """Retrieves capacity statistics about the running devices, such as session count, and produces a report. This is useful to determine overall system utilization with hardware limits.
    """
    os.makedirs(store_path, exist_ok=True)

    device_list = get_devices_from_argument(device)
    timestamp = int(datetime.datetime.now(tz=datetime.UTC).timestamp())

    exec_args = [
        CheckExecutionArgs(
            username=username,
            password=password,
            hostname=d,
            check_configuration=None,
            output_file=store_path.joinpath(
                f"capacity_{d}_{timestamp}.json".replace(":", "-")
            ),
        )
        for d in device_list
    ]
    pooled_run_capacity_checks_on_devices(exec_args, parallel=parallel)
    log.info(
        f"Capacity check process has finished. {len(exec_args)} reports saved to {store_path}."
    )
    reports = generate_reports_from_store(store_path)
    if len(device_list) == 1:
        print(reports.device_capacity_report_as_rich_table(device_list[0]))
