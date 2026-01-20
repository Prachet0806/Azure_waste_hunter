from reporting.report_builder import build_report


def test_report_includes_empty_sections_and_errors():
    report = build_report(
        [],
        scan_errors=[{"stage": "scan_x", "error": "oops"}],
        delivery_errors=[{"stage": "send_report", "error": "fail"}],
    )

    assert "## Wasted Resources" in report
    assert "scan_x" in report
    assert "send_report" in report