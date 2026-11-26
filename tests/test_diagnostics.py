from genesis_core.diagnostics import format_report, run_test_bench


def test_test_bench_runs_isolated_checks_and_reports_hardware(tmp_path):
    report = run_test_bench(tmp_path / "genesis-home")
    assert report["overall"] == "pass"
    assert report["summary"] == {"passed": 6, "failed": 0, "warnings": 0, "total": 6}
    assert report["model_probe_included"] is False
    assert all(item["status"] == "pass" for item in report["checks"])
    assert "No model inference" in format_report(report)


def test_test_bench_does_not_create_or_modify_user_database(tmp_path):
    home = tmp_path / "home"
    report = run_test_bench(home)
    assert report["overall"] == "pass"
    assert not (home / "data" / "genesis.db").exists()


def test_test_bench_report_is_json_serializable(tmp_path):
    report = run_test_bench(tmp_path / "home")
    assert '"overall": "pass"' in __import__("json").dumps(report)
