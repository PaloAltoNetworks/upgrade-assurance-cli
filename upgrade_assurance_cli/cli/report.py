import json
import pathlib
import enum
import datetime
import sys

from rich.table import Table
from panos_upgrade_assurance.snapshot_compare import SnapshotCompare

class ReportTypeEnum(str, enum.Enum):
    readiness = "readiness"
    snapshot = "snapshotr"

class BadDeviceStringException(Exception):
    pass

class CheckReport:
    def __init__(
            self,
            device: str,
            report: dict[str, dict],
            timestamp: int | str,
            report_type: ReportTypeEnum = ReportTypeEnum.readiness
    ):
        self.timestamp = int(timestamp)
        self.datetime = datetime.datetime.fromtimestamp(self.timestamp)
        self.device = device
        self.report = report
        self.report_type = report_type

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
        table = [
            [
                "check_name",
                "passed",
                "check_status",
                "reason"
            ]
        ]
        for k, check in self.report.items():
            # If this is a snapshot test

            if "state" not in check:
                # If this is a snapshot comparison
                state = check.get("passed")
                reason = f"Failed: {self.calc_change_reason_from_snapshot_report(check)}"
                status = ""
            else:
                state = check["state"]
                status = check["status"]
                reason = check["reason"]

            table.append([
                k,
                state,
                status,
                reason
            ])
        return table

class CheckReports:
    def __init__(self):
        self.reports: list[CheckReport] = []

    def add_report(self, report: CheckReport):
        self.reports.append(report)

    @property
    def failed_reports(self):
        return [r for r in self.reports if r.count_failed_checks > 0]

    @property
    def passed_reports(self):
        return [r for r in self.reports if r.count_failed_checks == 0]

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
            failed_count = r[2]
            style = "green"
            if failed_count > 0:
                style = "bold red"
            new_row_items = [str(i) for i in r]
            table.add_row(*new_row_items, style=style)

        return table

    def counts_as_table(self) -> list[list[str | int]]:
        table = [
            [
                "timestamp",
                "device",
                "failed_checks_count",
                "passed_checks_count"
            ]
        ]
        for report in self.reports:
            table.append(
                [
                    report.datetime.isoformat(),
                    report.device,
                    report.count_failed_checks,
                    report.count_passed_checks
                ]
            )
        return table

    def get_latest_report_by_device(self, device_str: str):
        sorted_devices = sorted([d for d in self.reports if d.device == device_str], key=lambda d: d.timestamp, reverse=True)
        if not sorted_devices:
            raise BadDeviceStringException(f"device {device_str} not found.")

        return sorted_devices[0]

    def device_report_as_rich_table(self, device_str: str):
        report = self.get_latest_report_by_device(device_str)
        list_table = report.checks_as_table()
        table = Table(caption=f"Checks were ran at {report.datetime.isoformat()}")
        for c in list_table[0]:
            table.add_column(c)

        for r in list_table[1:]:
            style = "green"
            if not r[1]:
                style = "bold red"
            new_row_items = [str(i) for i in r]
            table.add_row(*new_row_items, style=style)

        return table

def details_from_filename(filename: str) -> tuple[str, str, str]:
    """Gets the device name, the check type and the timestamp based on the filename."""
    filename = filename.replace(".json", "")
    check_type, device, timestamp = filename.split("_")
    return check_type, device, timestamp

def generate_reports_from_store(store_path: pathlib.Path):
    """Returns the completed readiness check report based on the generated check results in
    the store path"""

    reports = CheckReports()
    file: pathlib.Path
    for file in store_path.iterdir():
        if file.is_file() and file.suffix == '.json':
            check_type, device, timestamp = details_from_filename(file.name)
            report = CheckReport(
                timestamp=timestamp,
                device=device,
                report=json.load(open(file)),
                report_type=ReportTypeEnum(check_type)
            )
            reports.add_report(report)

    return reports