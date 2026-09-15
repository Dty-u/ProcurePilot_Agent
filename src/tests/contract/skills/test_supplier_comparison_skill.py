import importlib.util
import json
from pathlib import Path

SKILL_ROOT = Path("src/skills/procurement/supplier-comparison")


def test_skill_has_audited_metadata_and_input_contract() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "name: supplier-comparison" in content
    assert "quotation_id" in content
    assert "禁止联网" in content
    assert "/artifacts/supplier-comparison" in content


def test_fixed_sample_generates_only_declared_report_files(tmp_path: Path) -> None:
    script = SKILL_ROOT / "scripts/build_report.py"
    spec = importlib.util.spec_from_file_location("supplier_report", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sample = {
        "part_name": "轴承",
        "quotations": [
            {
                "supplier_id": "S-2",
                "supplier_name": "乙供应商",
                "quotation_id": "Q-2",
                "unit_price": 12.5,
                "delivery_days": 4,
                "quoted_at": "2026-09-10T08:00:00Z",
                "source": "ERP",
            },
            {
                "supplier_id": "S-1",
                "supplier_name": "甲供应商",
                "quotation_id": "Q-1",
                "unit_price": 10,
                "delivery_days": 7,
                "quoted_at": "2026-09-09T08:00:00Z",
                "source": "ERP",
            },
        ],
    }

    result = module.build_report(sample, tmp_path)

    assert set(path.name for path in tmp_path.iterdir()) == {
        "analysis.json",
        "comparison.csv",
        "price-chart.png",
        "report.md",
    }
    assert result["best_price_quotation_id"] == "Q-1"
    analysis = json.loads((tmp_path / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["best_price_quotation_id"] == "Q-1"
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Q-1" in report and "ERP" in report and "2026-09-09" in report
    assert (tmp_path / "price-chart.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
