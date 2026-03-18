import json
import pathlib
import enum
import datetime
from rich.table import Table
class ReportTypeEnum(str, enum.Enum):
    readiness = "readiness"

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

class CheckReports:
    def __init__(self):
        self.reports: list[CheckReport] = []

    def add_report(self, report: CheckReport):
        self.reports.append(report)

    def counts_as_rich_table(self):
        list_table = self.counts_as_table()
        table = Table()
        for c in list_table[0]:
            table.add_column(c)

        for r in list_table[1:]:
            new_row_items = [str(i) for i in r]
            table.add_row(*new_row_items)

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

def generate_reports_from_store(store_path: pathlib.Path):
    """Returns the completed readiness check report based on the generated check results in
    the store path"""

    reports = CheckReports()
    file: pathlib.Path
    for file in store_path.iterdir():
        if file.is_file() and file.suffix == '.json':
            filename = file.name.replace(".json", "")
            check_type, device, timestamp = filename.split("_")
            report = CheckReport(
                timestamp=timestamp,
                device=device,
                report=json.load(open(file)),
            )
            reports.add_report(report)

    return reports