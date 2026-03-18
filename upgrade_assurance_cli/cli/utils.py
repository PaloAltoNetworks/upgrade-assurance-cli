import json
import logging
import pathlib

import yaml
from rich.logging import RichHandler

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("cli")

ENCODING = "utf-8"

def load_config(fp: pathlib.Path):
    if not fp:
        return {}
    with open(fp) as config:
        try:
            return yaml.safe_load(config)
        except yaml.YAMLError:
            log.info("Could not load file as YAML - trying JSON")

        try:
            return json.load(config)
        except json.JSONDecodeError as e:
            log.critical("Could not load check config!")
            raise


def parse_file_to_devices(fp: pathlib.Path):
    with open(fp) as fh:
        return [l.strip() for l in fh.read().splitlines()]