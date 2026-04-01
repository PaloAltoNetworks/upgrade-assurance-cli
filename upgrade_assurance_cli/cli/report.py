import json
import pathlib
import enum
import datetime
import sys

from rich.bar import Bar
from rich.progress import BarColumn
from rich.table import Table

from upgrade_assurance_cli.cli.capacity import CapacityComparisonResults


class ReportTypeEnum(str, enum.Enum):
    readiness = "readiness"
    snapshot = "snapshotr"
    capacity = "capacity"


class BadDeviceStringException(Exception):
    pass


class SnapshotReport:
    def __init__(self, device, report, timestamp):
        self.timestamp = int(timestamp)
        self.datetime = datetime.datetime.fromtimestamp(self.timestamp)
        self.device = device
        self.report = report
        self.report_type = ReportTypeEnum.snapshot

    @property
    def count_failed_checks(self) -> int:
        return len([k for k, v in self.report.items() if v and not v.get("passed")])

    @property
    def count_passed_checks(self) -> int:
        return len([k for k, v in self.report.items() if v and v.get("passed")])

    def checks_as_table(self):
        table = [
            ["check_name", "passed", "missing", "added", "count_change_percentage"]
        ]
        for check_name, check_value in self.report.items():
            row = [check_name]
            if check_value:
                for i in table[0][1:]:
                    result = check_value.get(i)
                    if isinstance(result, dict):
                        result = result.get("passed")
                    row.append(result)
            else:
                # In the case where there is some problem wih the snapshot report, assume all tests have failed
                for _ in table[0][1:]:
                    row.append(False)
            table.append(row)

        return table


class ReadinessCheckReport:
    def __init__(
        self,
        device: str,
        report: dict[str, dict],
        timestamp: int | str,
    ):
        self.timestamp = int(timestamp)
        self.datetime = datetime.datetime.fromtimestamp(self.timestamp)
        self.device = device
        self.report = report
        self.report_type = ReportTypeEnum.readiness

    @property
    def count_failed_checks(self) -> int:
        return len([k for k, v in self.report.items() if not v.get("state")])

    @property
    def count_passed_checks(self) -> int:
        return len([k for k, v in self.report.items() if v.get("state")])

    @staticmethod
    def calc_change_reason_from_snapshot_report(result: dict):
        failed_list = []
        for check_type, check_result in result.items():
            if isinstance(check_result, dict):
                if not check_result.get("passed"):
                    failed_list.append(check_type)

        return ", ".join(failed_list)

    def checks_as_table(self):
        table = [["check_name", "passed", "check_status", "reason"]]
        for k, check in self.report.items():
            state = check["state"]
            status = check["status"]
            reason = check["reason"]

            table.append([k, state, status, reason])
        return table


class CapacityReport:
    def __init__(
        self,
        device: str,
        report: dict,
        timestamp: int | str,
        threshold: float | int = 80,
    ):
        self.timestamp = int(timestamp)
        self.datetime = datetime.datetime.fromtimestamp(self.timestamp)
        self.device = device
        self.report = report
        self.report_type = ReportTypeEnum.capacity
        self.threshold = threshold

    @property
    def results(self):
        return self.report.get("results")

    @property
    def count_failed_checks(self):
        results = self.results
        return len([i for i in results if i.get("percent") >= self.threshold])

    @property
    def count_passed_checks(self):
        results = self.results
        return len([i for i in results if i.get("percent") < self.threshold])

    def data_as_rich_table(self):
        table = Table(
            title="Device Capacity",
            show_header=True,
            caption=f"Capacity measured at {self.datetime.isoformat()}",
        )

        table.add_column("test")
        table.add_column("status")
        table.add_column("current")
        table.add_column("max")
        table.add_column("utilization")

        for r in self.results:
            percent = r.get("percent")
            status = "SUCCESS"
            style = "yellow"

            if percent == 0:
                percent = 1  # Make it so it renders some bar anyway, just so it doesn't look broken
                style = "cyan"

            if percent >= self.threshold:
                style = "red"
                status = "FAILED"

            table.add_row(
                r.get("name"),
                status,
                str(r.get("current")),
                str(r.get("capacity")),
                Bar(size=100, begin=0, end=percent, color=style),
            )

        return table


class CheckReports:
    def __init__(self):
        self.readiness_reports: list[ReadinessCheckReport] = []
        self.snapshot_reports: list[SnapshotReport] = []
        self.capacity_reports: list[CapacityReport] = []

    def add_readiness_report(self, report: ReadinessCheckReport):
        self.readiness_reports.append(report)

    def add_snapshot_report(self, report: SnapshotReport):
        self.snapshot_reports.append(report)

    def add_capacity_report(self, report: CapacityReport):
        self.capacity_reports.append(report)

    @property
    def failed_reports(self):
        return [
            r
            for r in self.readiness_reports + self.snapshot_reports
            if r.count_failed_checks > 0
        ]

    @property
    def passed_reports(self):
        return [
            r
            for r in self.readiness_reports + self.snapshot_reports
            if r.count_failed_checks == 0
        ]

    def exit_by_status(self):
        if self.failed_reports:
            sys.exit(1)

        sys.exit(0)

    def pass_or_fail_as_rich_string(self):
        if len(self.failed_reports) > 0:
            return "[red]❌ Some devices failed checks![/red]"

        return "✅ All devices passed."

    def counts_as_rich_table(self):
        list_table = self.counts_as_table()
        table = Table()
        for c in list_table[0]:
            table.add_column(c)

        for r in list_table[1:]:
            failed_count = r[3]
            style = "green"
            if failed_count > 0:
                style = "bold red"
            new_row_items = [str(i) for i in r]
            table.add_row(*new_row_items, style=style)

        return table

    @property
    def reports(self):
        return self.snapshot_reports + self.readiness_reports + self.capacity_reports

    def counts_as_table(self) -> list[list[str | int]]:
        table = [
            [
                "timestamp",
                "report_type",
                "device",
                "failed_checks_count",
                "passed_checks_count",
            ]
        ]
        for report in self.sorted_reports:
            table.append(
                [
                    report.datetime.isoformat(),
                    report.report_type.value,
                    report.device,
                    report.count_failed_checks,
                    report.count_passed_checks,
                ]
            )
        return table

    @property
    def sorted_reports(self):
        return sorted(self.reports, key=lambda d: d.timestamp)

    def get_latest_report_by_device(self, device_str: str, reports: list):
        sorted_reports = sorted(
            [d for d in reports if d.device == device_str],
            key=lambda d: d.timestamp,
            reverse=True,
        )
        if not sorted_reports:
            return None

        return sorted_reports[0]

    def device_readiness_report_as_rich_table(self, device_str: str):
        report = self.get_latest_report_by_device(device_str, self.readiness_reports)
        if not report:
            return f"[yellow]No Readiness report found for {device_str}[/yellow]"

        list_table = report.checks_as_table()
        table = Table(
            title="Readiness (pre-check) report",
            caption=f"READINESS Checks were ran at {report.datetime.isoformat()}",
        )
        for c in list_table[0]:
            table.add_column(c)

        for r in list_table[1:]:
            style = "green"
            if not r[1]:
                style = "bold red"
            new_row_items = [str(i) for i in r]
            table.add_row(*new_row_items, style=style)

        return table

    def device_snapshot_report_as_rich_table(self, device_str: str):
        report = self.get_latest_report_by_device(device_str, self.snapshot_reports)
        if not report:
            return f"[yellow]No Snapshot report found for {device_str}[/yellow]"
        table = Table(
            title="Snapshot report",
            caption=f"SNAPSHOT Report was ran at {report.datetime.isoformat()}",
        )
        table_list = report.checks_as_table()
        for header in table_list[0]:
            table.add_column(f"{header}")

        for r in table_list[1:]:
            style = "green"
            if not r[1]:
                style = "bold red"
            new_row_items = [str(i) for i in r]

            table.add_row(*new_row_items, style=style)

        return table

    def device_capacity_report_as_rich_table(self, device_str: str):
        report: CapacityReport = self.get_latest_report_by_device(
            device_str, self.capacity_reports
        )
        if not report:
            return f"[yellow]No Capacity report found for {device_str}[/yellow]"

        return report.data_as_rich_table()


def details_from_filename(filename: str) -> tuple[str, str, str]:
    """Gets the device name, the check type and the timestamp based on the filename."""
    filename = filename.replace(".json", "")
    check_type, device, timestamp = filename.split("_")
    return check_type, device, timestamp


def read_snapshot_report(path: pathlib.Path):
    """Reads a single report and returns it"""
    check_type, device, timestamp = details_from_filename(path.name)
    reports = CheckReports()
    report = SnapshotReport(
        timestamp=timestamp,
        device=device,
        report=json.load(open(path)),
    )
    reports.add_snapshot_report(report)
    return reports


def generate_reports_from_store(store_path: pathlib.Path):
    """Returns the completed readiness check report based on the generated check results in
    the store path"""

    reports = CheckReports()
    file: pathlib.Path
    for file in store_path.iterdir():
        if file.is_file() and file.suffix == ".json":
            check_type, device, timestamp = details_from_filename(file.name)
            if check_type == ReportTypeEnum.readiness.value:
                report = ReadinessCheckReport(
                    timestamp=timestamp,
                    device=device,
                    report=json.load(open(file)),
                )
                reports.add_readiness_report(report)
            elif check_type == ReportTypeEnum.snapshot:
                report = SnapshotReport(
                    timestamp=timestamp,
                    device=device,
                    report=json.load(open(file)),
                )
                reports.add_snapshot_report(report)
            elif check_type == ReportTypeEnum.capacity:
                report = CapacityReport(
                    timestamp=timestamp,
                    device=device,
                    report=json.load(open(file)),
                )
                reports.add_capacity_report(report)

    return reports


class SnapshotData:
    def __init__(
        self,
        device: str,
        data: dict[str, dict],
        timestamp: int | str,
    ):
        self.timestamp = int(timestamp)
        self.datetime = datetime.datetime.fromtimestamp(self.timestamp)
        self.device = device
        self.data = data

    def data_as_table(self):
        table = [["type", "state"]]

        for snapshot_type, data in self.data.items():
            table.append([snapshot_type, data.get("state")])

        return table

    def data_as_rich_table(self):
        table = Table(caption=f"SNAPSHOT Taken at {self.datetime.isoformat()}")
        table_list = self.data_as_table()
        for c in table_list[0]:
            table.add_column(c)

        for r in table_list[1:]:
            style = "green"
            if not r[1]:
                style = "bold red"
            new_row_items = [str(i) for i in r]
            table.add_row(*new_row_items, style=style)

        return table


def get_snapshot_data_report(path: pathlib.Path):
    """Returns a `SnapshotData` instance representing a taken snapshot"""
    if path.is_file() and path.suffix == ".json":
        check_type, device, timestamp = details_from_filename(path.name)
        report = SnapshotData(device, json.load(open(path)), timestamp)
        return report

    raise FileNotFoundError(f"{path} not found.")
