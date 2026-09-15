---
name: supplier-comparison
description: 对已由采购查询工具验证的结构化报价生成可溯源的比价报告和图表。
---

# 供应商比价

仅接受已验证 JSON，根字段为 `part_name` 和 `quotations`。每条报价必须包含
`supplier_id`、`supplier_name`、`quotation_id`、`unit_price`、`delivery_days`、
`quoted_at` 和 `source`。

在 OpenSandbox 内运行：

```text
python /skills/procurement/supplier-comparison/scripts/build_report.py \
  --input /workspace/quotation-input.json \
  --output-dir /artifacts/supplier-comparison
```

输出仅为 `analysis.json`、`comparison.csv`、`price-chart.png` 和 `report.md`。
报告必须保留 quotation ID、来源和报价时间，不得将排名当成业务批准。

禁止联网、读取凭据、访问宿主路径、修改采购业务数据、下载其他 Skill 或自我修改。
