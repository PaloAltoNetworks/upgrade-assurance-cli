import multiprocessing
import pathlib
import enum
import time
from logging import Logger
from xml.etree.ElementTree import tostring, Element

import panos.errors
import requests
from panos.errors import PanDeviceNotSet
from panos.firewall import Firewall
from panos_upgrade_assurance.firewall_proxy import FirewallProxy

from upgrade_assurance_cli.cli.runner import (
    get_firewall_proxy_from_args,
    setup_logger_for_runners,
)
from upgrade_assurance_cli.cli.utils import log


class BackupTypeEnum(str, enum.Enum):
    configuration = "configuration"
    device_state = "device-state"
    tech_support_file = "tech-support"


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


def get_and_wait_for_job(
    firewall: Firewall,
    job_id: str | int,
    file_log: Logger,
    check_interval: int = 10,
    timeout: int = 300,
) -> Element:
    """Gets the job by the given ID, waiting for it to finish, and returns the entire job xml if it finishes OK.
    Otherwise, raises `TimeoutError`"""
    if not job_id:
        raise ValueError("Requires job_id")
    status = "ACT"
    current_time = 0
    while status != "FIN" and status and current_time < timeout:
        time.sleep(check_interval)
        result = firewall.op(
            f"<show><jobs><id>{job_id}</id></jobs></show>", cmd_xml=False
        )
        status = result.find("./result/job/status").text
        file_log.info(f"Job {job_id} status: {status} (time: {current_time})")
        current_time += check_interval

    if status != "FIN":
        raise TimeoutError(
            f"Timed out waiting for {job_id} to finish. Last status: {status}"
        )

    return result.find("./result/job")


def generate_tech_support_file(
    firewall: FirewallProxy,
    file_log: Logger,
    check_interval: int = 10,
    timeout: int = 300,
):
    """Generates a tech support file by starting a job and waiting for it to be finished.

    Returns the job_id if the job completed."""
    try:
        result = firewall._fw.op(
            "<request><tech-support><dump></dump></tech-support></request>",
            cmd_xml=False,
        )
    except panos.errors.PanDeviceXapiError as e:
        file_log.error(f"Tech support generation command failed: {str(e)}")
        return

    job_id = result.find("./result/job")
    if job_id is None:
        file_log.error(f"Could not generate tech support file: {tostring(result)}")
        return

    job_id = job_id.text

    file_log.info(f"Started generation with job id {job_id}")

    try:
        get_and_wait_for_job(firewall._fw, job_id, file_log, check_interval, timeout)
        return job_id
    except TimeoutError as e:
        file_log.error(f"{e}")
        return None


def download_tech_support_file(
    firewall: Firewall, job_id: str | int, output_file: pathlib.Path
):
    """Retrieves the tech support file from the given, completed, job"""
    params = {
        "action": "get",
        "job-id": job_id,
        "type": "export",
        "category": "tech-support",
        "key": firewall.api_key,
    }
    with requests.get(firewall.xapi.uri, params=params, stream=True, verify=False) as r:
        r.raise_for_status()
        with open(output_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                # If you have chunk encoded response uncomment if
                # and set chunk_size parameter to None.
                # if chunk:
                f.write(chunk)
    return output_file


def export_config(exec_arguments: ExporterArguments):
    """Exports teh device configuration from the firewall.

    This supports running-configuration, device-state, or tech support files.
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

    if exec_arguments.export_type == BackupTypeEnum.tech_support_file:
        try:
            firewall.panorama()
            file_log.critical(
                "Cannot export tech support via Panorama proxied API connection. Please specify"
                "the firewall directly."
            )
            return
        except PanDeviceNotSet:
            pass

        job_id = generate_tech_support_file(firewall, file_log)
        if not job_id:
            log.critical(
                f"Could not export {exec_arguments.export_type.value} from device."
            )
            return
        output_file = str(pathlib.Path(exec_arguments.output_file)) + ".tgz"
        file_log.info(
            f"Downloading tech support file to {output_file} from job {job_id}"
        )
        download_tech_support_file(firewall._fw, job_id, output_file)
        return

    if not write_bytes:
        log.critical(
            f"Could not export {exec_arguments.export_type.value} from device."
        )
        return

    file_log.info(f"Saving config to {output_file}")

    with open(output_file, "wb") as file:
        file.write(write_bytes)


def pooled_take_config_backup(exec_args: list[ExporterArguments], parallel: int = 4):
    log.info(f"Exporting data using multiprocessing ({parallel})")
    with multiprocessing.Pool(parallel) as pool:
        pool.map(export_config, exec_args)

    log.info(f"Exports complete.")
