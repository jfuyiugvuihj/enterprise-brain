"""Task-specific presentation over the existing version, calculation and evidence records."""
from __future__ import annotations

import re


def output_constraints(question: str, *, empty_data: bool = False) -> tuple[str, set[str]]:
    """Remove explicit coordinated refusals from intent, retaining the refused actions."""
    output = r"(?:柱状图|折线图|饼图|图表|图|PDF(?:报告)?|报告|简报)"
    lookup = r"(?:查询|检索)(?:资料|文档|知识库)"
    pattern = (rf"(?:不要|不必|不需要|不需|无需|无须|别|不)(?:再)?(?:{lookup}\s*(?:或者|以及|或|和|、|及|与)\s*)?(?:生成|制作|导出|下载|画|绘制)?\s*"
               rf"{output}(?:\s*(?:或者|以及|或|和|、|及|与)\s*{output})*")
    prohibited = set()

    def remove(match):
        prefix = re.split(r'[；;。\n]', question[:match.start()])[-1]
        conditional = re.search(r'(?:如果|若|当).*?(?:为空|0行|没有记录|无数据|没有数据)|为空时', prefix)
        if conditional and not empty_data:
            return ''
        text = match.group().lower()
        if '图' in text:
            prohibited.add('chart')
        if re.search(r'pdf|报告|简报', text):
            prohibited.add('export')
        return ''

    return re.sub(pattern, remove, question, flags=re.I), prohibited


def requires_query_calculation(question: str) -> bool:
    intent, _ = output_constraints(question)
    return bool(re.search(r'同比|环比|预算|预测|SQL|相关性|中位|标准差|方差|分位|去重|唯一|排序|降序|升序|排名|排行|前\s*[\d一二三四五六七八九十]+', intent, re.I))


def table_summary_intent(question: str, *, contextual: bool = False) -> bool:
    intent, _ = output_constraints(question)
    return bool((contextual or re.search(r'按.+?(?:汇总|合计|统计)|合计|总计|统计|多少|平均|均值|记录数|总数|报告|简报', intent))
                and not requires_query_calculation(intent))


def report_delivery(question: str) -> str:
    """Delivery intent never grants an export that the user explicitly prohibited."""
    intent, prohibited = output_constraints(re.sub(r'《[^》]*》', ' ', question))
    if 'export' in prohibited or not re.search(r'PDF|报告|简报', intent, re.I):
        return ''
    if re.search(r'(?:分别|各自|逐(?:题|项|问)).{0,6}(?:生成|导出)|每(?:题|项|问).{0,12}(?:一份|生成|导出)', intent):
        return 'separate'
    if re.search(r'一(?:份|个)(?:含图|带图)?\s*(?:PDF|报告|简报)', intent, re.I):
        return 'combined'
    return 'ambiguous'


def _output_tail(text: str) -> bool:
    tail = output_constraints(text)[0].strip(' \n，,。；;：:')
    return not tail or bool(re.fullmatch(
        r'(?:请)?(?:(?:把|将)(?:以上|上述)(?:[一二两三四五六七八九十\d]+项)?'
        r'(?:结果|问题)(?:合并|汇总)(?:成|为)|(?:分别|各自|逐题)?(?:生成|导出))'
        r'(?:[一二两三四五六七八九十\d]+份)?(?:含图|带图)?\s*PDF(?:报告|简报)?', tail, re.I))


def question_items(question: str) -> list[tuple[str, str]]:
    """Recognize explicit question boundaries, without inventing missing subquestions."""
    markers = list(re.finditer(r'[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)(?:10|[1-9])[.、)）](?=\s|[\u4e00-\u9fff])', question))
    if len(markers) >= 2:
        parts = [(marker.group(), question[marker.end():markers[i + 1].start() if i + 1 < len(markers) else len(question)])
                 for i, marker in enumerate(markers)]
    elif markers:
        return []
    else:
        clauses = re.split(r'[？?]', question)
        if not 3 <= len(clauses) <= 11 or not _output_tail(clauses[-1]):
            return []
        parts = list(zip('①②③④⑤⑥⑦⑧⑨⑩', clauses[:-1]))
    result = []
    for label, item in parts:
        pieces = re.split(r'[？?]', item, maxsplit=1)
        if len(pieces) == 2 and _output_tail(pieces[1]):
            item = pieces[0]
        result.append((label, item.strip(' \n：:；;。？?')))
    return result if all(item for _, item in result) else []


def report_count_conflict(question: str, count: int) -> bool:
    match = re.search(r'([一二两三四五六七八九十\d]+)份', question)
    if report_delivery(question) != 'separate' or not match:
        return False
    number = int(match[1]) if match[1].isdigit() else dict(zip('一二三四五六七八九十', range(1, 11))).get(match[1], 2)
    return number not in (1, count)


def turn_clarification(state: dict) -> str:
    context = state.get('task_context') or state.get('data_context') or {}
    if context.get('clarification'):
        return context['clarification']
    latest = next((str(m.content or '') for m in reversed(state.get('messages') or [])
                   if type(m).__name__ == 'HumanMessage'), '')
    if context.get('report_body') or latest.startswith('请将以下已完成的分析原文排版导出'):
        return ''
    question = context.get('analysis_question') or context.get('query') or latest
    items = question_items(question)
    mode = report_delivery(context.get('execution_question') or latest)
    if not mode and latest != question and not output_constraints(latest)[1]:
        mode = report_delivery(question)
    if len(items) > 1 and mode == 'ambiguous':
        return ('已识别到多个问题。请先说明：把所有结果合成一份PDF，还是每题分别生成一份PDF？'
                '你也可以回复“先只回答，不生成报告”。本轮尚未发起导出操作确认。')
    if items and report_count_conflict(context.get('execution_question') or latest, len(items)):
        return f'已识别到{len(items)}个问题，但要求的报告份数与逐题导出不一致。请说明每份报告包含哪些题，或改为每题一份；本轮尚未发起导出操作确认。'
    return ''


def scoped_question_items(question: str) -> list[tuple[str, str, str]]:
    result = []
    for label, item in question_items(question):
        intent = output_constraints(item)[0]
        if re.search(r'制度|规定|凭证|审批要求|提交期限|政策', intent) and not re.search(r'金额.*(?:合计|平均|均值)', intent):
            kind = 'doc'
        elif re.search(r'为什么|原因|解释.*(?:增长|变化|下降)', intent):
            kind = 'explanation'
        elif re.search(r'合计|总额|总计|记录数|平均|均值|中位数|排序|排名|预算', intent):
            kind = 'data'
        else:
            kind = 'unknown'
        result.append((label, item, kind))
    return result


def independent_period_questions(question: str) -> list[tuple[str, str]]:
    """Split numbered, independently scoped statistics before any calculation."""
    def output_tail(text: str) -> bool:
        return _output_tail(text)

    markers = list(re.finditer(r"[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)(?:10|[1-9])[.、)）](?=\s|[\u4e00-\u9fff])", question))
    if len(markers) < 2:
        if markers:
            return []  # Mixed numbering must not silently drop a question.
        parts = re.split(r'[？?]', question)
        if not 3 <= len(parts) <= 11 or not output_tail(parts[-1]):
            return []
        clauses = parts[:-1]
        if not all(re.search(r'合计|总额|总计|记录数|平均|均值|中位数|标准差|方差|分位|排名|预算', item) for item in clauses):
            return []
        prefix = re.split(r'\d{4}[-/]\d{1,2}', clauses[0], maxsplit=1)[0]
        if re.search(r'仅|只|排除|不含|不统计', output_constraints(prefix)[0]):
            return []  # A shared filter needs clarification, not first-question-only scope.
        question = ''.join(label + item for label, item in zip('①②③④⑤⑥⑦⑧⑨⑩', clauses))
        markers = list(re.finditer(r'[①②③④⑤⑥⑦⑧⑨⑩]', question))
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
        separated = re.split(r'[？?]', item, maxsplit=1)
        if len(separated) == 2 and output_tail(separated[1]):
            item = separated[0].strip()
        ranges = re.findall(range_pattern, item)
        without_ranges = re.sub(range_pattern, "", item)
        months = re.findall(r"(?<!\d)\d{4}[-/]\d{1,2}(?![\d/-])", without_ranges)
        if len(ranges) + len(months) != 1 or not re.search(r"合计|总额|总计|记录数|平均|均值|多少|中位数|标准差|方差|分位|排名|预算", item):
            return []
        scopes.append((ranges or months)[0])
        items.append((marker.group(), item))
    return items


def alert_task_question(question: str, data_context: dict) -> str:
    """The alert draft appends evidence; that evidence is not a new user instruction."""
    if data_context.get('alert_id'):
        return question.split('\n\n提醒编号：', 1)[0]
    return question


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


def _revise_question_item(original: str, replacement: str) -> str:
    """Apply an explicit single condition change without dropping the other filters."""
    replacement = re.split(r'[，,。；;]?\s*(?:其他|其余)(?:题|项|条件)?不变', replacement, maxsplit=1)[0]
    replacement = output_constraints(replacement)[0].strip(' ，,。；;？?')
    date = r'\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?'
    period = rf'{date}(?:\s*(?:至|到|~|～)\s*{date})?'
    status = r'(?:仅|只)(?:统计|计算|包含|保留|分析|汇总)(?:状态(?:为|是))?(?:已批准|已支付|待审批|已驳回)(?:或(?:已批准|已支付|待审批|已驳回))*(?:的?记录)?'
    if re.fullmatch(period, replacement):
        periods = list(re.finditer(period, original))
        if len(periods) == 1:
            match = periods[0]
            return original[:match.start()] + replacement + original[match.end():]
        return ''
    if re.fullmatch(status, replacement):
        prior = re.sub(status, replacement, original)
        prior = re.sub(r'状态(?:为|是|仅包含|包含)(?:已批准|已支付|待审批|已驳回)(?:或(?:已批准|已支付|待审批|已驳回))*(?:的?记录)?', replacement, prior)
        return prior if prior != original or replacement in prior else prior + '，' + replacement
    if re.search(period, replacement) and re.search(r'合计|总额|总计|平均|均值|记录数|多少|中位数|标准差|方差|分位|排名|预算', replacement):
        # Conditions embedded in the statistic cannot be separated reliably.
        # Ask for an explicit scope instead of silently broadening it.
        clauses = re.split(r'[，,；;]', original)
        if re.search(r'部门|状态|工作表|仅|只|超过|大于|小于|不含|排除', clauses[0]):
            return ''
        for clause in clauses[1:]:
            clause = clause.strip()
            if not clause or clause in replacement:
                continue
            if re.fullmatch(status, clause) and re.search(status, replacement):
                continue
            key = re.match(r'(.+?)(?:为|是|超过|大于|小于|等于|[><=])', clause)
            if key and re.search(re.escape(key[1]) + r'(?:为|是|超过|大于|小于|等于|[><=])', replacement):
                # Conflicting updates require a complete, unambiguous condition.
                return ''
            replacement += '，' + clause
        return replacement
    return ''


def review_context(question: str, filename: str, previous: dict, dataset: dict,
                   *, documents: list[dict] | None = None) -> dict:
    """Follow-ups retain the user's input criteria, never criteria inferred by a model."""
    same = previous and previous.get("filename") == filename
    status_clause = r"(?:仅|只)(?:统计|计算|包含|保留|分析|汇总)[^，。；;\n]+"
    explicit_scope = bool(re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|工作表", question)
                          or re.search(status_clause, question))
    if same and not re.search(r"新任务|重新发起|改用新版本", question):
        saved = dict(previous)
        saved.pop('clarification', None)
        saved['execution_question'] = question
        if question.startswith('请将以下已完成的分析原文排版导出'):
            return _with_document_selection(saved, documents)
        target = re.search(r'第?([一二两三四五六七八九十\d]+)(?:题|项|问).*?(?:改为|改成|修改为)(.+)', question)
        if target:
            numerals = dict(zip('一二三四五六七八九十', range(1, 11)))
            number = int(target[1]) if target[1].isdigit() else numerals.get(target[1], 2 if target[1] == '两' else 0)
            items = question_items(saved['analysis_question'])
            replacement = _revise_question_item(items[number - 1][1], target[2]) if 1 <= number <= len(items) else ''
            if not 1 <= number <= len(items):
                saved['clarification'] = f'原任务有{len(items)}个可识别的问题，请说明要修改哪一题；其他题尚未改动。'
            elif replacement:
                items[number - 1] = (items[number - 1][0], replacement)
                prefix = saved['analysis_question'].split(items[0][0], 1)[0] if items[0][0] in saved['analysis_question'] else ''
                saved['analysis_question'] = prefix + ''.join(label + item + '？' for label, item in items)
            else:
                saved['clarification'] = '请明确该题要修改的期间、状态或完整统计问题，例如“第二题的期间改为2026-04”；其他题尚未改动。'
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
    from calendar import monthrange
    usable = []
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", period)
    if not dates:
        for year, month in re.findall(r'(?<!\d)(\d{4})[-/](\d{1,2})(?![\d/-])', period):
            if 1 <= int(month) <= 12:
                dates.extend([f'{int(year):04d}-{int(month):02d}-01',
                    f'{int(year):04d}-{int(month):02d}-{monthrange(int(year),int(month))[1]}'])
    for item in documents:
        text = str(item.get("excerpt") or "")
        if "制度" not in text and "提交期限" not in text:
            continue
        starts = re.search(r"(?:生效日[：:]\s*|费用发生日期自)(\d{4}-\d{2}-\d{2})", text)
        expires = re.search(r"适用日期[：:]\s*(\d{4}-\d{2}-\d{2})至(\d{4}-\d{2}-\d{2})", text)
        if not dates or not starts:
            continue
        if min(dates) < starts.group(1) or (expires and max(dates) > expires.group(2)):
            continue
        usable.append(item)
    return usable


def policy_question_reviews(documents: list[dict], question: str) -> list[dict]:
    """Each independent period gets its own applicable evidence and limitations."""
    items = independent_period_questions(question)
    shared = question.split(items[0][0], 1)[0] if items and items[0][0] in question else ''
    return [{'label': label, 'question': (shared + ' ' + item).strip(),
        'policy_sources': policy_identity(documents, period=shared + ' ' + item),
        'body': policy_review_text(documents, period=shared + ' ' + item)} for label,item in items]


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
        lines.append("如金额单位未注明，不能与制度中的元金额比较或据此确定审批人。")
    lines.append("风险建议：补齐单位、提交日期和对应材料后再核查；本结果是辅助核查意见，不是正式业务审批。")
    return "\n\n".join(lines)
