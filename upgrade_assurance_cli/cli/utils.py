import json
import logging
import pathlib

import yaml
from pydantic import BaseModel
from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("cli")

ENCODING = "utf-8"

DEFAULT_SNAPSHOT_CONFIG = [
    'nics',
    'routes',
    'license',
    'arp_table',
    'session_stats',
    'ip_sec_tunnels',
    'bgp_peers'
]

DEFAULT_SNAPSHOT_COMPARISON_CONFIG = [
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

DEFAULT_READINESS_CHECKS = [
    "environmentals",
    "ha",
    "ntp_sync",
    "candidate_config",
    "expired_licenses",
    "active_support",
    "free_disk_space",
    "certificates_requirements",
    "dynamic_updates",
    "jobs",
    "global_jumbo_frame",
    "dp_cpu_utilization",
    "mp_cpu_utilization",
    # "planes_clock_sync" # Currently bugged on some platforms
]


class TestConfigs(BaseModel):
    pre_checks: list = DEFAULT_READINESS_CHECKS
    snapshot_config: list = DEFAULT_SNAPSHOT_CONFIG
    snapshot_comparison_config: list | dict = DEFAULT_SNAPSHOT_COMPARISON_CONFIG


def load_config(fp: pathlib.Path):
    if not fp:
        log.warning(
            "No config file provided, using defaults. Use the `show-configuration` subcommand to show all defaults"
        )
        loaded_config = {
            "snapshot_config": DEFAULT_SNAPSHOT_CONFIG,
            "snapshot_comparison_config": DEFAULT_SNAPSHOT_COMPARISON_CONFIG,
            "pre_checks": DEFAULT_READINESS_CHECKS
        }

        return TestConfigs(**loaded_config)
    with open(fp) as config:
        try:
            loaded_config = yaml.safe_load(config)
            return TestConfigs(**loaded_config)

        except yaml.YAMLError:
            log.info("Could not load file as YAML - trying JSON")

        try:
            loaded_config = json.load(config)
            return TestConfigs(**loaded_config)

        except json.JSONDecodeError as e:
            log.critical("Could not load check config!")
            raise


def parse_file_to_devices(fp: pathlib.Path):
    with open(fp) as fh:
        return [l.strip() for l in fh.read().splitlines()]
