import multiprocessing
import pathlib
import enum
from xml.etree.ElementTree import tostring

import requests
from panos.firewall import Firewall

from upgrade_assurance_cli.cli.runner import (
    get_firewall_proxy_from_args,
    setup_logger_for_runners,
)
from upgrade_assurance_cli.cli.utils import log


class BackupTypeEnum(str, enum.Enum):
    configuration = "configuration"
    device_state = "device-state"


class ExporterArguments:
    def __init__(
        self,
        username,
        password,
        hostname,
        output_file,
        export_type=BackupTypeEnum.configuration,
    ):
        self.output_file = output_file
        self.username = username
        self.password = password
        self.hostname = hostname
        self.export_type = export_type

    @property
    def device_str(self):
        return f"{self.hostname}".replace(":", "-")


def get_device_state(firewall: Firewall, verify: bool = False):
    """Patch variation of the device state command as does not seem to work within XAPI"""
    url = f"https://{firewall.hostname}:{firewall.port}/api"
    params = {
        "type": "export",
        "category": "device-state",
    }
    if firewall.serial:
        panorama = firewall.panorama()
        api_key = panorama.api_key
        url = f"https://{panorama.hostname}:{firewall.port}/api"
        params["device"] = firewall.serial
    else:
        api_key = firewall.api_key

    params = {
        "key": api_key,
        "type": "export",
        "category": "device-state",
    }

    return requests.post(url, params=params, verify=verify)


def export_config(exec_arguments: ExporterArguments):
    """Exports teh device configuration from the firewall.

    This supports running-configuration and device-state exports.
    """
    firewall = get_firewall_proxy_from_args(
        exec_arguments.username,
        exec_arguments.password,
        exec_arguments.hostname,
    )
    file_log = setup_logger_for_runners(exec_arguments.device_str)
    file_log.info(
        f"Exporting {exec_arguments.export_type.value} for {exec_arguments.device_str}"
    )
    write_bytes = b""
    if exec_arguments.export_type == BackupTypeEnum.device_state:
        result = get_device_state(firewall._fw, verify=False)
        output_file = str(pathlib.Path(exec_arguments.output_file)) + ".tgz"
        write_bytes = result.content

    elif exec_arguments.export_type == BackupTypeEnum.configuration:
        result = firewall._fw.xapi.export(category=exec_arguments.export_type.value)
        output_file = str(pathlib.Path(exec_arguments.output_file)) + ".xml"
        write_bytes = tostring(result)

    if not write_bytes:
        log.critical(
            f"Could not export {exec_arguments.export_type.value} from device."
        )
        return

    file_log.info(f"Saving config to {output_file}")

    with open(output_file, "wb") as file:
        file.write(write_bytes)


def pooled_take_config_backup(exec_args: list[ExporterArguments], parallel: int = 4):
    log.info(f"Exporting configuration using multiprocessing ({parallel})")
    with multiprocessing.Pool(parallel) as pool:
        pool.map(export_config, exec_args)

    log.info(f"Exports complete.")
