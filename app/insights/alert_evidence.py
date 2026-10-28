"""Authorized, reproducible threshold observations over the existing alert ledger."""
import hashlib
import json
import math
import re
from datetime import datetime, timezone

from app.common.rbac import filter_dataframe_rows_with_scope
from app.tools.excel import filter_explicit_categories


def additive_metric(name):
    if str(name).strip() in {'月份', '年月', '统计月份', '日期', '发生日期'}:
        return False
    return not re.search(r'率|比例|占比|百分|单价|均价|平均|编号|编码|序号|ID$|id$', str(name))


def metric_unit(name):
    for annotation in re.findall(r'[（(]([^()（）]+)[）)]', str(name)):
        if re.fullmatch(r'(?:人民币)?(?:元|万元|亿元|千元|美元|万元人民币|人|人次|个|件|台|套|吨|千克|公斤|克|升|米|平方米|小时|天|次|%|％|百分比)', annotation.strip()):
            return annotation.strip()
    return '单位未标注'


def calculate_finding(frame, rule, *, filename, dataset_id, version_id, sha256, principal, system_department=''):
    options = rule.get('options') or {}
    query = str(options.get('query') or '')
    role = principal.role if principal else 'admin'
    department = principal.department or '' if principal else ''
    visible, _scope = filter_dataframe_rows_with_scope(frame, role=role, department=department)
    selected = filter_explicit_categories(visible, query)
    if selected.empty:
        raise ValueError('筛选后无记录，无法作阈值判断或确认异常恢复。')
    metric = rule['metric']
    if not additive_metric(metric):
        raise ValueError('该指标不可直接求和，请改选可加指标或先准备正确聚合后的数据。')
    if metric not in selected or not __import__('pandas').api.types.is_numeric_dtype(selected[metric]):
        raise ValueError('指标列不存在或不是数值列，未生成阈值结论。')
    values = selected[metric].dropna()
    if not values.map(math.isfinite).all():
        raise ValueError('指标含无穷值，未生成阈值结论。')
    if len(selected) and not len(values):
        raise ValueError('指标全部缺失，不能按零判断。')
    current = float(values.sum())
    threshold = float(rule['threshold'])
    if not math.isfinite(threshold):
        raise ValueError('阈值必须是有限数值。')
    op = rule.get('op', 'gt')
    breached = bool(len(selected)) and {'gt': current > threshold, 'gte': current >= threshold,
        'lt': current < threshold, 'lte': current <= threshold}[op]
    dimensions = [c for c in selected if any(word in str(c) for word in ('部门', '产品', '项目', '类别'))]
    group = options.get('group_by') or next(iter(dimensions), '')
    contributions = []
    if group and group in selected:
        contributions = [{'label': str(label), 'value': float(value)} for label, value in
            selected.groupby(group, dropna=False)[metric].sum().sort_values(ascending=False).head(20).items()]
    unit = re.search(r'[（(]([^()（）]+)[）)]', metric)
    period = selected.attrs.get('requested_period') or '全部授权可见记录（未限定期间）'
    scope = {'role': role, 'department': department or system_department,
             'department_ids': sorted(principal.department_ids) if principal else []}
    key = {'rule_id': rule['id'], 'dataset_id': dataset_id, 'scope': scope, 'query': query,
           'owner_id': principal.user_id if principal else ''}
    return {'filename': filename, 'dataset_id': dataset_id, 'version_id': version_id, 'sha256': sha256,
        'owner_id': principal.user_id if principal else '', 'scope': scope,
        'finding_key': hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'metric': metric, 'current': current, 'threshold': threshold, 'op': op, 'breached': breached,
        'rows': len(selected), 'missing': int(selected[metric].isna().sum()),
        'unit': metric_unit(metric), 'period': period,
        'query': query, 'filter': selected.attrs.get('filter_note') or '未指定分类筛选',
        'dimension': group, 'contributions': contributions,
        'records': json.loads(selected.head(20).to_json(orient='records', date_format='iso')),
        'observed_at': datetime.now(timezone.utc).isoformat()}


def explain_finding(evidence):
    compare = {'gt': '大于', 'gte': '大于等于', 'lt': '小于', 'lte': '小于等于'}[evidence['op']]
    result = [f"阈值提醒：{evidence['metric']}={evidence['current']:g}（{evidence['unit']}），"
              f"规则为{compare}{evidence['threshold']:g}；纳入{evidence['rows']}条记录。",
              f"期间：{evidence['period']}；筛选：{evidence['filter']}。"]
    if evidence['contributions']:
        result.append('主要构成：' + '；'.join(f"{item['label']} {item['value']:g}" for item in evidence['contributions'][:5]) + '。构成不代表确定原因。')
    result.append('未提供可比上期、预算及业务原因证据，不判断异常增长或确定原因；请核对明细及业务材料。')
    return '\n'.join(result)


def observation_update(prior, evidence, now):
    history = list(prior.get('observations') or [prior.get('evidence') or {}])
    previous = history[-1] if history else {}
    identity = ('version_id', 'sha256', 'current', 'threshold', 'rows', 'breached')
    if any(previous.get(key) != evidence.get(key) for key in identity):
        history.append(evidence)
    recovered = now if not evidence['breached'] and not prior.get('recovered_at') else prior.get('recovered_at', '')
    return {**prior, 'evidence': evidence, 'observations': history,
            'recovered_at': recovered, 'last_observed_at': now}


def source_allowed(principal, row):
    evidence = row.get('evidence') or {}
    if not evidence:
        return True
    from app.common.policy import is_administrator, authorization_decision
    from app.common.permissions import ACTION_VIEW
    from app.storage.datasets import dataset_registry
    # Disposal already authorizes department peers. Evidence can be shared only
    # under the identical calculation scope and current source permission below.
    if not is_administrator(principal):
        snapshot = evidence.get('scope') or {}
        if (snapshot.get('role') != principal.role or snapshot.get('department') != (principal.department or '')
                or snapshot.get('department_ids', []) != sorted(principal.department_ids)):
            return False
    scope = dataset_registry.scope_for_version(evidence.get('version_id') or '')
    return bool(scope and authorization_decision(principal, scope, action=ACTION_VIEW, require_resource_scope=True).allowed)
