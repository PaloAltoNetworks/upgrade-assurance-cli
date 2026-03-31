from typing import Annotated

import requests
import json
from pydantic import BaseModel, Field, AfterValidator
from upgrade_assurance_cli.cli.utils import log


class ComparisonError(Exception):
    pass


class SessionDetails(BaseModel):
    total_supported: int = Field(alias="num-max")
    packets_per_second: int = Field(alias="pps")
    connections_per_second: int = Field(alias="cps")
    throughput_kbps: int = Field(alias="kbps")
    total_sessions: int = Field(alias="num-active")


class RunningCapacityDetails(BaseModel):
    model: str
    session_details: SessionDetails


def convert_to_mbps_or_int(value: str):
    """Numbers get too big when dealing with tbps so we convert to mbps instead

    This function converts either speed strings like 1.5 Tbps to MBPS, or numbers like 120,000 to int(120000)
    """
    r = value.split(" ")
    if len(r) == 2:
        # ex: 100 Gbps, 1.5 tbps
        i, t = r[0], r[1].lower()
        i = float(i)
        if t == "tbps":
            return i * 1000000
        if t == "gbps":
            return i * 1000
        if t == "mbps":
            return i

        raise ValueError(f"Unknown speed acronym: {t}")

    elif len(r) == 1:
        r = r[0].replace(",", "")
        try:
            return int(r)
        except ValueError:
            return None

    raise ValueError(f"Unparsable as speed or count int: {value}")


AnyTypeOfNumber = Annotated[str | int, AfterValidator(convert_to_mbps_or_int)]


class CapacityComparisonResult(BaseModel):
    name: str
    percent: int
    current: int | float
    capacity: int | float


class CapacityComparisonResults(BaseModel):
    results: list[CapacityComparisonResult]


class ResponseDataItem(BaseModel):
    product_name: str
    title: str
    id: str
    url: str
    app_id_throughput_mbps: AnyTypeOfNumber = Field(alias="5-0-6-1_dfi")
    connections_per_second: AnyTypeOfNumber = Field(alias="5-0-11-1_dfi")
    maximum_sessions_total: AnyTypeOfNumber = Field(alias="14-0-15-1_dfi")

    @staticmethod
    def calc_percentage(x, y):
        return int((x / y) * 100)

    def compare_with_running(
            self,
            running_capacity_statistics: RunningCapacityDetails
    ):
        results = [
            CapacityComparisonResult(
                name="throughput_utilization_mbps",
                percent=self.calc_percentage(
                    # Note conversion of kbps reported by device to mbps as stored by statistics
                    running_capacity_statistics.session_details.throughput_kbps / 1000,
                    self.app_id_throughput_mbps
                ),
                current=running_capacity_statistics.session_details.throughput_kbps / 1000,
                capacity=self.app_id_throughput_mbps,
            ),
            CapacityComparisonResult(
                name="session_utilization_total",
                percent=self.calc_percentage(
                    # Note conversion of kbps reported by device to mbps as stored by statistics
                    running_capacity_statistics.session_details.total_sessions,
                    self.maximum_sessions_total
                ),
                current=running_capacity_statistics.session_details.total_sessions,
                capacity=self.maximum_sessions_total
            ),
            CapacityComparisonResult(
                name="connections_per_second_utilization",
                percent=self.calc_percentage(
                    # Note conversion of kbps reported by device to mbps as stored by statistics
                    running_capacity_statistics.session_details.connections_per_second,
                    self.connections_per_second
                ),
                current=running_capacity_statistics.session_details.connections_per_second,
                capacity=self.connections_per_second
            )
        ]
        return CapacityComparisonResults(results=results)


class ResponseData(BaseModel):
    items: list[ResponseDataItem]

    def get_limits_by_model(self, model: str):
        """Return the limits and details of a given model, by item"""
        try:
            return next(
                i for i in self.items if i.product_name == model
            )
        except StopIteration:
            return None

    def compare_with_running(
            self,
            running_capacity_statistics: RunningCapacityDetails
    ):
        limits = self.get_limits_by_model(running_capacity_statistics.model)
        if limits:
            return limits.compare_with_running(running_capacity_statistics)

        raise ComparisonError(f"Could not find model {running_capacity_statistics.model} in total capacity details")


def get_capacity_details():
    """Pulls capacity details from the public PAN-OS hardware matrix API"""
    log.info("Retrieving capacity details from https://www.paloaltonetworks.com/products/product-selection.html#")
    url = "https://www.paloaltonetworks.com/apps/pan/public/solr/proxy?facet=true&corename=productcompare&q=*:*&facet.field=1-0-3-1_dfi&facet.field=5-0-7-1_dfi&facet.field=5-0-9-1_dfi&facet.field=5-0-12-1_dfi&facet.field=14-0-16-1_dfi&facet.sort=count&facet.limit=20&facet.mincount=1&fq=language:%22en_US%22&sort=position%20asc&rows=100&wt=json"
    response = requests.get(url)
    # This is so ugly but seems like the only way we can return it
    sanitized_response = response.text.replace("var sliderData = ", "")
    data = json.loads(sanitized_response)
    return ResponseData(items=data.get("response").get("docs"))
