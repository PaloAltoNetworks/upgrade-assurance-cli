from tests.unit.fixtures import report_store


def test_generate_report_from_store(report_store):
    from upgrade_assurance_cli.cli.report import generate_reports_from_store

    reports = generate_reports_from_store(report_store)
    assert reports.reports[0].count_failed_checks == 10
    assert reports.reports[0].count_passed_checks == 7
    assert reports.reports[0].device == "1.1.1.1"
