"""Execute explicitly selected, scoped catalog definitions without generated code."""
from __future__ import annotations

import hashlib
import json
import math
import re

from app.semantics import registry


def execution_support(definition) -> dict:
    if definition.status not in registry.ACTIVE_STATUSES or not definition.verified_against_documents:
        return {"supported": False, "reason": "口径尚未核对或已停用"}
    if not definition.source_scope:
        return {"supported": False, "reason": "口径未指定适用数据文件"}
    match = re.fullmatch(r"\s*(SUM|MEAN|AVG|COUNT)\s*\((.+)\)\s*", definition.formula, re.I)
    if not match or not definition.unit:
        return {"supported": False, "reason": "需要明确的 SUM(列名)、MEAN(列名) 或 COUNT(列名/*) 公式及单位"}
    operation, column = match[1].upper().replace("AVG", "MEAN"), match[2].strip()
    if not column or (column == "*" and operation != "COUNT"):
        return {"supported": False, "reason": "公式未指定可计算字段"}
    if any(not isinstance(key, str) or not isinstance(value, (str, int, float, bool))
           or (isinstance(value, float) and not math.isfinite(value))
           for key, value in definition.filters.items()):
        return {"supported": False, "reason": "当前仅支持明确的字段等值筛选"}
    return {"supported": True, "operation": operation, "column": column}


def _snapshot(definition) -> dict:
    return {**definition.to_public(), "definition_id": definition.definition_id}


def bind_metric(definition_id: str, owner_id: str, dataset) -> dict:
    # Exact rows, not fuzzy matching or a fallback definition with the same name.
    definition = next((item for item in registry._table_definitions(owner_id)
                       if item.definition_id == definition_id), None)
    if definition is None:
        raise ValueError("所选指标口径不可用，请重新选择。")
    support = execution_support(definition)
    if not support["supported"]:
        raise ValueError(support["reason"])
    if not {dataset.filename, dataset.dataset_id}.intersection(definition.source_scope):
        raise ValueError("所选指标口径不适用于这份数据文件。")
    return _snapshot(definition)


def binding_from_config(config) -> dict | None:
    conf = (config or {}).get("configurable") or {}
    context = conf.get("data_context") or {}
    if "metric_binding" not in context:
        context = conf.get("task_context") or {}
    return context.get("metric_binding")


def validate_binding(binding: dict, owner_id: str, dataset) -> None:
    current = bind_metric(str(binding.get("definition_id") or ""), owner_id, dataset)
    if current != binding:
        raise ValueError("指标口径已发生变化，请重新选择并核对后再计算；未沿用旧确认执行。")


def binding_digest(binding: dict) -> str:
    return hashlib.sha256(json.dumps(binding, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def calculate_metric(df, binding: dict, question: str, *, dimension: str | None = None):
    import pandas as pd
    from app.agents.task_review import requires_query_calculation, output_constraints
    from app.insights.alert_evidence import metric_unit

    operation, column = re.fullmatch(r"\s*(SUM|MEAN|AVG|COUNT)\s*\((.+)\)\s*",
                                     binding["formula"], re.I).groups()
    operation, column = operation.upper().replace("AVG", "MEAN"), column.strip()
    intent, _ = output_constraints(question)
    requested = {kind for kind, pattern in (("SUM", r"合计|总计|总额|求和"),
                 ("MEAN", r"平均|均值"), ("COUNT", r"记录数|总数|多少条")) if re.search(pattern, intent)}
    unsupported = re.search(r'最大|最小|最高|最低|极值|占比|百分比|差额|差值|增长|增幅|差多少', intent)
    if requires_query_calculation(intent) or unsupported or requested - {operation}:
        raise ValueError("问题中的运算与所选指标公式不一致或超出当前支持范围，请调整问题或取消该口径。")
    named = [str(field) for field in df.select_dtypes(include=['number']).columns
             if str(field) in intent or (len(re.sub(r'[（(][^）)]+[）)]', '', str(field))) >= 2
                and re.sub(r'[（(][^）)]+[）)]', '', str(field)) in intent)]
    if any(field != column and field != dimension and field not in binding.get('filters', {}) for field in named):
        raise ValueError("问题指定的数值字段与指标公式不一致，请调整问题或取消该口径。")
    frame = df.copy()
    notes = []
    for field, value in binding.get("filters", {}).items():
        if field not in frame.columns:
            raise ValueError(f"指标筛选字段不存在：{field}")
        frame = frame.loc[frame[field].eq(value)].copy()
        notes.append(f"{field}={value}")
    if column != "*" and column not in frame.columns:
        raise ValueError(f"指标公式字段不存在：{column}")
    values = frame[column] if column != "*" else None
    if operation != "COUNT":
        if not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values):
            raise ValueError(f"指标公式字段不是数值列：{column}")
        if not values.dropna().map(lambda value: math.isfinite(float(value))).all():
            raise ValueError("指标数据含非有限数值，未生成结果。")
        source_unit = metric_unit(column)
        if source_unit != "单位未标注" and source_unit != binding["unit"]:
            raise ValueError("指标单位与源字段单位不一致，未自动换算。")
        if source_unit == "单位未标注":
            notes.append("源字段未标注单位；结果单位采用已核对口径中的登记值")

    def aggregate(part):
        if operation == "COUNT":
            return int(len(part) if column == "*" else part[column].count())
        series = part[column].dropna()
        value = float(series.sum() if operation == "SUM" else series.mean()) if len(series) else None
        if value is not None and not math.isfinite(value):
            raise ValueError("计算结果超出有限数值范围，未生成结果。")
        return value

    groups = []
    if dimension and dimension in frame.columns:
        groups = [(str(label) if pd.notna(label) else "未标注", aggregate(part))
                  for label, part in frame.groupby(dimension, dropna=False, sort=True)]
        if len(groups) > 50:
            raise ValueError("分组超过50项，请缩小筛选范围后再计算。")
    result = {"binding": binding, "binding_sha256": binding_digest(binding),
              "operation": operation, "column": column, "value": aggregate(frame),
              "rows": len(frame), "non_null": int(values.count()) if values is not None else len(frame),
              "missing": int(values.isna().sum()) if values is not None else 0,
              "dimension": dimension or "", "groups": groups, "notes": notes}
    frame.attrs["filter_note"] = "；".join(filter(None, [df.attrs.get("filter_note", ""),
                                    *(f"口径筛选：{note}" for note in notes if "=" in note)]))
    frame.attrs["metric_result"] = result
    return frame, result


def metric_answer(result: dict, *, include_groups: bool = True) -> str:
    binding = result["binding"]
    value = f"{result['value']:,.2f}（{binding['unit']}）" if result["value"] is not None else "无可计算的非空数据"
    provenance = binding["provenance"]
    parts = [f"**{binding['metric_name']}：{value}**",
             f"计算公式：{binding['formula']}；口径版本：{binding['definition_version']}；口径ID：{binding['definition_id']}。",
             f"定义：{binding['definition']}",
             f"登记的核对依据：{provenance['verified_document']} · {provenance['verified_section']}。",
             f"筛选后 {result['rows']} 条记录，其中 {result['non_null']} 条非空；缺失 {result['missing']} 条，未按零值填充。"]
    if include_groups and result["groups"]:
        cell = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        parts.append(f"| {cell(result['dimension'])} | {cell(binding['metric_name'])}（{cell(binding['unit'])}） |\n| --- | ---: |\n"
                     + "\n".join(f"| {cell(label)} | {value:,.2f} |" if value is not None else
                                 f"| {cell(label)} | 无非空数据 |" for label, value in result["groups"]))
    parts.extend(result["notes"])
    return "\n\n".join(parts)
