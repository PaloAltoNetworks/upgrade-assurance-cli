import multiprocessing
import json

from panos_upgrade_assurance.snapshot_compare import SnapshotCompare

from upgrade_assurance_cli.cli.utils import log, ENCODING
from panos_upgrade_assurance.firewall_proxy import FirewallProxy
from panos_upgrade_assurance.check_firewall import CheckFirewall
import logging


def get_firewall_proxy_from_args(username: str, password: str, device: str):
    """Returns a FirewallProxy object based on the arguments passed to this function"""
    d = device.split(":")
    if len(d) == 2:
        panorama, firewall_serial = d
        return FirewallProxy(
            hostname=panorama,
            api_username=username,
            api_password=password,
            serial=firewall_serial,
        )

    return FirewallProxy(
        hostname=device,
        api_username=username,
        api_password=password,
    )


class CheckExecutionArgs:
    def __init__(
            self,
            username,
            password,
            hostname,
            check_configuration,
            output_file
    ):
        self.check_configuration = check_configuration
        self.output_file = output_file
        self.username = username
        self.password = password
        self.hostname = hostname

    @property
    def device_str(self):
        return f"{self.hostname}".replace(":", "-")

def setup_for_checks(exec_arguments: CheckExecutionArgs):
    device = get_firewall_proxy_from_args(
        exec_arguments.username,
        exec_arguments.password,
        exec_arguments.hostname,
    )

    fileLog = logging.getLogger(exec_arguments.device_str)
    fileLog.addHandler(logging.FileHandler(f"{exec_arguments.device_str}.log"))
    fileLog.propagate = False

    fileLog.info(f"{exec_arguments.device_str} - Running readiness checks on device ")
    return CheckFirewall(device), fileLog

def run_readiness_checks_on_device(exec_arguments: CheckExecutionArgs):
    check_configuration = exec_arguments.check_configuration
    output_file = exec_arguments.output_file
    try:

        checks, fileLog = setup_for_checks(exec_arguments)
        result = checks.run_readiness_checks(
            check_configuration
        )
        with open(output_file, "w", encoding=ENCODING) as fh:
            json.dump(result, fh, indent=4)

        fileLog.info(f"{exec_arguments.device_str} - Writing to file {output_file}")
    except Exception:
        fileLog.critical(f"Readiness checks failed!", exc_info=True)


def get_snapshots_on_device(exec_arguments: CheckExecutionArgs):
    checks, fileLog = setup_for_checks(exec_arguments)
    fileLog.info(f"{exec_arguments.device_str} - Taking device snapshot")

    try:
        snapshot_configuration = exec_arguments.check_configuration
        output_file = exec_arguments.output_file

        result = checks.run_snapshots(
            snapshot_configuration
        )

        with open(output_file, "w", encoding=ENCODING) as fh:
            json.dump(result, fh, indent=4)

        fileLog.info(f"{exec_arguments.device_str} - Writing to file {output_file}")
    except Exception:
        fileLog.critical(f"Readiness checks failed!", exc_info=True)


def pooled_run_readiness_checks_on_devices(
        exec_args: list[CheckExecutionArgs],
        parallel: int = 4
):
    log.info(f"Running readiness checks using multiprocessing ({parallel})")
    with multiprocessing.Pool(parallel) as pool:
        pool.map(run_readiness_checks_on_device, exec_args)

    log.info(f"Readiness checks complete")

def pooled_run_snapshot_checks_on_devices(
        exec_args: list[CheckExecutionArgs],
        parallel: int = 4
):
    log.info(f"Running Snapshot checks using multiprocessing ({parallel})")
    with multiprocessing.Pool(parallel) as pool:
        pool.map(get_snapshots_on_device, exec_args)

    log.info(f"Snapshots complete")
