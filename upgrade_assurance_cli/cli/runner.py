import multiprocessing
import json

from panos.firewall import Firewall
from panos.panorama import Panorama
from panos_upgrade_assurance.snapshot_compare import SnapshotCompare

from upgrade_assurance_cli.cli.utils import log, ENCODING
from panos_upgrade_assurance.firewall_proxy import FirewallProxy
from panos_upgrade_assurance.check_firewall import CheckFirewall
import logging


def get_firewall_proxy_from_args(username: str, password: str, device: str) -> FirewallProxy:
    """Returns a FirewallProxy object based on the arguments passed to this function"""
    d = device.split(":")
    if len(d) == 2:

        panorama_hostname, firewall_serial = d
        fw = Firewall(
            api_username=username,
            api_password=password,
            serial=firewall_serial,
        )
        panorama = Panorama(
            api_username=username,
            api_password=password,
            hostname=panorama_hostname,
        )
        panorama.add(fw)
        return FirewallProxy(
            fw
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

def setup_logger_for_runners(device_str):
    file_log = logging.getLogger(device_str)
    file_handler = logging.FileHandler(
        f"{device_str}.log"
    )
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
    )
    file_log.addHandler(file_handler)
    file_log.propagate = False
    return file_log

def setup_for_checks(exec_arguments: CheckExecutionArgs):
    device = get_firewall_proxy_from_args(
        exec_arguments.username,
        exec_arguments.password,
        exec_arguments.hostname,
    )
    file_log = setup_logger_for_runners(exec_arguments.device_str)
    return CheckFirewall(device), file_log

def run_readiness_checks_on_device(exec_arguments: CheckExecutionArgs):
    check_configuration = exec_arguments.check_configuration
    output_file = exec_arguments.output_file
    try:

        checks, file_log = setup_for_checks(exec_arguments)
        result = checks.run_readiness_checks(
            check_configuration
        )
        with open(output_file, "w", encoding=ENCODING) as fh:
            json.dump(result, fh, indent=4)

        file_log.info(f"{exec_arguments.device_str} - Writing to file {output_file}")
    except Exception as e:
        file_log.critical(f"Readiness checks failed!", exc_info=True)
        result = {
            "device_connectivity": {
                "state": False,
                "status": "ERROR",
                "reason": f"Critical error running readiness checks: {e}"
            }
        }
        with open(output_file, "w", encoding=ENCODING) as fh:
            json.dump(result, fh, indent=4)


def get_snapshots_on_device(exec_arguments: CheckExecutionArgs):
    checks, file_log = setup_for_checks(exec_arguments)
    file_log.info(f"{exec_arguments.device_str} - Taking device snapshot")
    output_file = exec_arguments.output_file

    try:
        snapshot_configuration = exec_arguments.check_configuration

        result = checks.run_snapshots(
            snapshot_configuration
        )

        with open(output_file, "w", encoding=ENCODING) as fh:
            json.dump(result, fh, indent=4)

        file_log.info(f"{exec_arguments.device_str} - Writing to file {output_file}")
    except Exception as e:
        file_log.critical(f"Snapshot failed!", exc_info=True)


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
