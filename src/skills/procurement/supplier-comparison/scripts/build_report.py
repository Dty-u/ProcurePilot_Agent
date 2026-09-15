"""在沙箱内把结构化报价转换为四种可审核产物。"""

from __future__ import annotations

import argparse
import csv
import json
import struct
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

_OUTPUT_NAMES = ("analysis.json", "comparison.csv", "price-chart.png", "report.md")
_QUOTE_FIELDS = {
    "supplier_id",
    "supplier_name",
    "quotation_id",
    "unit_price",
    "delivery_days",
    "quoted_at",
    "source",
}


def build_report(payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    part_name, quotations = _validate(payload)
    ranked = sorted(quotations, key=lambda item: (float(item["unit_price"]), int(item["delivery_days"])))
    best = ranked[0]
    analysis = {
        "part_name": part_name,
        "quotation_count": len(ranked),
        "best_price_quotation_id": best["quotation_id"],
        "ranked_quotation_ids": [item["quotation_id"] for item in ranked],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(_QUOTE_FIELDS))
        writer.writeheader()
        writer.writerows(ranked)
    (output_dir / "price-chart.png").write_bytes(_price_chart(ranked))
    rows = [
        f"| {item['quotation_id']} | {item['supplier_name']} | {item['unit_price']} | "
        f"{item['delivery_days']} | {item['source']} | {item['quoted_at']} |"
        for item in ranked
    ]
    report = "\n".join(
        [
            f"# {part_name}供应商比价报告",
            "",
            "| quotation ID | 供应商 | 单价 | 交期(天) | 来源 | 报价时间 |",
            "|---|---|---:|---:|---|---|",
            *rows,
            "",
            f"最低价报价：`{best['quotation_id']}`。本结果仅供分析，不代表下单批准。",
        ]
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    return analysis


def _validate(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if set(payload) != {"part_name", "quotations"} or not isinstance(payload["part_name"], str):
        raise ValueError("输入根字段不符合约定")
    quotations = payload["quotations"]
    if not isinstance(quotations, list) or not quotations:
        raise ValueError("quotations 必须是非空数组")
    for item in quotations:
        if not isinstance(item, dict) or set(item) != _QUOTE_FIELDS:
            raise ValueError("报价字段不符合约定")
        if float(item["unit_price"]) < 0 or int(item["delivery_days"]) < 0:
            raise ValueError("价格和交期不能为负数")
    return payload["part_name"], quotations


def _price_chart(quotations: list[dict[str, Any]]) -> bytes:
    width, height = 320, 180
    pixels = [bytearray([255, 255, 255] * width) for _ in range(height)]
    maximum = max(float(item["unit_price"]) for item in quotations) or 1
    bar_width = max(4, width // (len(quotations) * 2 + 1))
    for index, item in enumerate(quotations):
        bar_height = int((height - 20) * float(item["unit_price"]) / maximum)
        left = bar_width * (index * 2 + 1)
        for y in range(height - bar_height, height):
            for x in range(left, min(left + bar_width, width)):
                pixels[y][x * 3 : x * 3 + 3] = b"\x2f\x80\xed"
    raw = b"".join(b"\x00" + bytes(row) for row in pixels)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    input_path = PurePosixPath(args.input)
    output_path = PurePosixPath(args.output_dir)
    if not str(input_path).startswith("/workspace/") or ".." in input_path.parts:
        raise SystemExit("输入只允许位于 /workspace")
    if not str(output_path).startswith("/artifacts/") or ".." in output_path.parts:
        raise SystemExit("输出只允许位于 /artifacts")
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    build_report(payload, Path(args.output_dir))
    print(json.dumps({"outputs": list(_OUTPUT_NAMES)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
