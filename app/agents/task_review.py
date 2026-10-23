"""Task-specific presentation over the existing version, calculation and evidence records."""
from __future__ import annotations

import re


def independent_period_questions(question: str) -> list[tuple[str, str]]:
    """Split numbered, independently scoped statistics before any calculation."""
    markers = list(re.finditer(r"[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)(?:10|[1-9])[.、)）](?=\s|[\u4e00-\u9fff])", question))
    if len(markers) < 2:
        return []
    date = r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    range_pattern = rf"{date}\s*(?:至|到|~|～)\s*{date}"
    prefix = question[:markers[0].start()]
    if re.search(date + r"|(?<!\d)\d{4}[-/]\d{1,2}(?![\d/-])", prefix):
        return []
    scopes: list[str] = []
    items: list[tuple[str, str]] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(question)
        item = question[marker.end():end].strip(" ：:；;。\n")
        ranges = re.findall(range_pattern, item)
        without_ranges = re.sub(range_pattern, "", item)
        months = re.findall(r"(?<!\d)\d{4}[-/]\d{1,2}(?![\d/-])", without_ranges)
        if len(ranges) + len(months) != 1 or not re.search(r"合计|总额|总计|记录数|平均|均值|多少", item):
            return []
        scopes.append((ranges or months)[0])
        items.append((marker.group(), item))
    return items if len(set(scopes)) > 1 else []


def is_review_question(question: str) -> bool:
    return bool(re.search(r"核查|核验|核对|是否符合|是否满足|合规", question)
                and re.search(r'制度|合规|审批要求|规章|规则|规定|标准', question))


def is_expense_precheck_request(question: str) -> bool:
    """Only an explicit expense self-check may use the amount precheck worker."""
    return bool(re.search(r"预审|自查", question)
                and re.search(r"报销|费用|住宿费|差旅", question)
                and re.search(r"\d+(?:\.\d+)?\s*(?:元|块)|金额\s*\d+|超标|超额|额度|限额", question))


def requested_documents_valid(task: dict, principal) -> bool:
    if not task.get('requested_documents'):
        return True
    from app.documents.catalog import latest_document_version
    from app.rag.filters import resolve_document_retrieval_scope
    scope = resolve_document_retrieval_scope(principal)
    for reference in task.get('requested_documents') or []:
        current = latest_document_version(reference['filename'])
        if (not current or not scope.allows(current)
                or str(current.get('version') or '') != reference['version_id']):
            return False
    return True


def document_selection_context(names: list[str], previous: dict) -> dict:
    """Pin a document-only task to its first selected versions."""
    if not names:
        return {}
    selected = sorted(dict.fromkeys(names))
    earlier = previous.get('requested_documents') or []
    if sorted(item.get('filename') for item in earlier) == selected:
        return {'requested_documents': [dict(item) for item in earlier]}
    from app.documents.catalog import latest_document_version

    return {'requested_documents': [
        {'filename': name, 'version_id': str((latest_document_version(name) or {}).get('version') or '')}
        for name in selected
    ]}


def legacy_document_selection_unpinned(previous: dict) -> bool:
    """Old document-only sessions lack a trustworthy selected-version snapshot."""
    if previous.get('document_selection') or previous.get('task_context'):
        return False
    return any(str(getattr(message, 'content', '')).startswith('仅依据以下文件')
               for message in previous.get('messages') or []
               if type(message).__name__ == 'HumanMessage')


def _with_document_selection(context: dict, documents: list[dict] | None) -> dict:
    context['analysis_question'] = re.sub(r'^仅依据以下文件(?:《[^》\r\n]+》)+回答：\n', '', context['analysis_question'])
    if documents is None:
        return context
    previous = context.get('requested_documents')
    names = sorted(item['filename'] for item in documents)
    if previous is not None and sorted(item['filename'] for item in previous) == names:
        return context
    context.pop('policy_sources', None)
    context['requested_documents'] = [dict(item) for item in documents]
    return context


def review_context(question: str, filename: str, previous: dict, dataset: dict,
                   *, documents: list[dict] | None = None) -> dict:
    """Follow-ups retain the user's input criteria, never criteria inferred by a model."""
    same = previous and previous.get("filename") == filename
    status_clause = r"(?:仅|只)(?:统计|计算|包含|保留|分析|汇总)[^，。；;\n]+"
    explicit_scope = bool(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|工作表", question)
                          or re.search(status_clause, question))
    if same and not re.search(r"新任务|重新发起|改用新版本", question):
        saved = dict(previous)
        saved['execution_question'] = question
        if question.startswith('请将以下已完成的分析原文排版导出'):
            return _with_document_selection(saved, documents)
        if explicit_scope:
            # A partial scope change must not silently discard earlier status criteria.
            date_range = r"\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*(?:至|到|~|～)\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}"
            found = re.search(date_range, question)
            if found:
                prior = saved["analysis_question"]
                saved["analysis_question"] = (re.sub(date_range, found.group(), prior)
                    if re.search(date_range, prior) else prior + "，" + found.group())
            # Replace only the explicitly changed condition, not the entire task.
            changed = re.search(status_clause, question)
            if changed:
                clause = changed.group()
                statuses = r"已批准|已支付|待审批|已驳回"
                prior = saved["analysis_question"]
                if re.search(statuses, clause):
                    prior = re.sub(status_clause, lambda m: clause if re.search(statuses, m.group()) else m.group(), prior)
                    prior = re.sub(r"状态(?:为|是|仅包含|包含)(?:已批准|已支付|待审批|已驳回)(?:或(?:已批准|已支付|待审批|已驳回))*(?:记录)?", clause, prior)
                if clause not in prior:
                    prior += "，" + clause
                saved["analysis_question"] = prior
            sheet = r'工作表\s*[「“"]([^」”"]+)[」”"]|[「“"]([^」”"]+)[」”"]\s*工作表'
            changed_sheet = re.search(sheet, question)
            if changed_sheet:
                prior = saved["analysis_question"]
                saved["analysis_question"] = (re.sub(sheet, changed_sheet.group(), prior)
                    if re.search(sheet, prior) else prior + "，" + changed_sheet.group())
        return _with_document_selection(saved, documents)
    return _with_document_selection({"filename": filename, "version_id": dataset.get("version_id", ""),
            "sha256": dataset.get("sha256", ""), "analysis_question": question,
            "execution_question": question}, documents)


def policy_identity(documents: list[dict], *, period: str = "") -> list[dict]:
    if period:
        documents = _applicable_policy_documents(documents, period)
    identities = sorted({(str(d.get("source_name") or ""), str(d.get("version_id") or ""),
        str(d.get("index_version_id") or "")) for d in documents
        if d.get("source_name")})
    return [dict(zip(("source_name", "version_id", "index_version_id"), values)) for values in identities]


def _applicable_policy_documents(documents: list[dict], period: str) -> list[dict]:
    usable = []
    for item in documents:
        text = str(item.get("excerpt") or "")
        if "制度" not in text and "提交期限" not in text:
            continue
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", period)
        starts = re.search(r"(?:生效日[：:]\s*|费用发生日期自)(\d{4}-\d{2}-\d{2})", text)
        expires = re.search(r"适用日期[：:]\s*(\d{4}-\d{2}-\d{2})至(\d{4}-\d{2}-\d{2})", text)
        if not dates or not starts:
            continue
        if min(dates) < starts.group(1) or (expires and max(dates) > expires.group(2)):
            continue
        usable.append(item)
    return usable


def policy_review_text(documents: list[dict], *, period: str, unit_known: bool = False,
                       verified_rows: int | None = None) -> str:
    """Quote permitted policy clauses; missing business evidence stays unverified."""
    lines = ["### 制度依据与核查边界"]
    usable = _applicable_policy_documents(documents, period)
    # Distinct policies may conflict. Do not select the strictest amount or newest title.
    sources = {item.get("source_name") for item in usable}
    if len(sources) != 1:
        lines.append("未取得唯一且覆盖本次日期范围的制度依据；制度适用性无法判断，请明确制度文件及版本。")
    else:
        for item in usable:
            business_version = re.search(r"版本[：:]\s*([^；;\n。]+)", item["excerpt"])
            locator = item.get("locator") or {}
            lines.append(f"依据：《{item['source_name']}》；制度版本：{business_version.group(1) if business_version else '原文未标注'}；"
                         f"知识库版本：{item.get('version_id') or '未记录'}；定位：片段 {locator.get('chunk_index', '未记录')}。")
            for clause in item["excerpt"].splitlines():
                clause = clause.strip()
                if re.match(r"[一二三四五六七八九十]+[、．.]", clause):
                    lines.append(f"> {clause}")
            lines.append("以上为制度原文；审批人金额分档不等于报销额度上限，批准状态不证明已经付款。")
    verification = ("数据事项请以本轮实际计算结果为准；本节仅列制度依据，不证明数据计算已经成功。"
        if verified_rows is None else "已核验：授权范围与筛选结果为0条；没有记录可核验状态或作分组比较。"
        if verified_rows == 0 else "已核验：本次授权数据中的状态、记录数、分组及合计，详见计算事实。")
    lines.extend(["### 已核验与尚待核实", verification,
                  "缺失材料：原始凭证、业务用途说明、真实批准记录；未核验其真实性和完整性。",
                  "无法判断：缺提交日期，不能判断是否按期提交；缺业务材料，不能据此认定全面合规。"])
    if not unit_known:
        lines.append("金额单位未注明，不能与制度中的元金额比较或据此确定审批人。")
    lines.append("风险建议：补齐单位、提交日期和对应材料后再核查；本结果是辅助核查意见，不是正式业务审批。")
    return "\n\n".join(lines)
