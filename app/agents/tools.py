"""
LangChain Tools — 封装企业智脑全部能力，供 ReAct Agent 自主调用
"""
import os
import json
import re
from collections import OrderedDict
from typing import NamedTuple
import inspect
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.common.logger import logger
from app.common.permissions import ACTION_ANALYZE, ACTION_EXPORT
from app.agents.evidence import (
    _enum_error_codes,
    bag_from_config,
    record_artifact,
    record_dataset,
    record_document_hits,
    record_tool_status,
)
from app.trace.spans import start_tool_call


def _get_user_context(user: dict | None = None) -> dict:
    """Build tool context from an explicit caller; missing identity is denied."""
    if not user or not user.get("username"):
        raise PermissionError("authorization_required: agent tool identity is missing")
    from app.common.identity import Principal

    principal = Principal.from_user(user, auth_source="agent")
    if principal.status != "active":
        raise PermissionError("permission_denied: agent tool identity is inactive")
    return {
        "username": principal.username,
        "role": principal.role,
        "department": principal.department,
        "permissions": sorted(principal.permissions),
        "clearance": principal.clearance,
    }


def _tool_principal(config):
    """Resolve the canonical Principal carried by the Agent runtime."""
    conf = (config or {}).get("configurable", {}) or {}
    try:
        from app.common.identity import Principal

        provided = conf.get("principal")
        if isinstance(provided, Principal):
            principal = provided
        elif isinstance(provided, dict):
            principal = Principal.model_validate(provided)
        else:
            principal = Principal.from_user(conf, auth_source="agent")
        if not principal.user_id or not principal.username:
            raise PermissionError("authorization_required: agent tool identity is missing")
        if principal.status != "active":
            raise PermissionError("permission_denied: agent tool identity is inactive")
        return principal
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError(
            "authorization_required: agent tool identity is missing"
        ) from exc


def _tool_context(config) -> dict | None:
    try:
        principal = _tool_principal(config)
        return {
            "username": principal.username,
            "role": principal.role,
            "department": principal.department,
            "permissions": sorted(principal.permissions),
            "clearance": principal.clearance,
        }
    except PermissionError as exc:
        logger.warning("[Tool] %s", exc)
        return None


# 错误码词表的唯一来源是 ErrorEnvelope.code，这里派生一份集合、不抄第二份手抄码表
# （抄两份的代价写在 app/agents/evidence.py 的 _enum_error_codes docstring 里）。
_PUBLIC_ERROR_CODES = _enum_error_codes()

# 行级终态的两枚稳定码（R64 判据①）。成员资格由枚举钉，出处由
# tests/test_error_code_vocabulary.py::RATIFIED 钉；两者都不是 rbac 内部 reason 名的别名。
_ROW_SCOPE_DENIED_CODE = "row_scope_denied"
_NO_VISIBLE_ROWS_CODE = "no_visible_rows"

# 数据集准入闸（app/common/policy.py::authorization_decision）的内部 reason → 公开码。
# 全仓只此一份，放在翻译层：policy/rbac 的判定一个字都不改，内部词表改名也不许破坏公开契约。
# 没进这张表的 reason（含 clearance_insufficient）一律说成 permission_denied：那只是
# 「这份资源对你没有授权」这个事实本身，不含更细的判断。密级口径属 H13（业主未裁），
# 本单不许借映射表替它下结论，也不为它新增枚举成员。
_POLICY_DENIAL_CODES = {
    "authentication_required": "authentication_required",
    "principal_inactive": "account_unavailable",
    "department_scope_denied": "department_scope_required",
}
_POLICY_DENIAL_FALLBACK_CODE = "permission_denied"


def _public_error_code(code: object, fallback: str) -> str:
    """不在封闭枚举里的码名不许外泄：先回落成枚举内的码，再谈文案与状态。

    上游的 code 由 getattr(exc, "code", ...) 读出来，任何异常都能塞一个自己的名字进来。
    让它原样进正文＝把内部词表当公开契约卖出去，正是 R64 判据⑤要拦的那件事。
    """
    text = str(code or "")
    return text if text in _PUBLIC_ERROR_CODES else fallback


def _policy_denial_code(reason: object) -> str:
    """policy 的 reason → 公开码：翻译只在这一处发生，判定仍然只在 policy 里。"""
    mapped = _POLICY_DENIAL_CODES.get(str(reason or ""), _POLICY_DENIAL_FALLBACK_CODE)
    return _public_error_code(mapped, _POLICY_DENIAL_FALLBACK_CODE)


def _record_denial(config, *, tool: str, code: str, status: str = "failed") -> None:
    """结构化出口的唯一写法：把稳定码交给本轮的执行证据袋。

    状态默认报 failed 而不是 rejected：evidence._terminal_status 会把任何 rejected 折成
    permission_denied（R13 之前的老账，本单写域外），只有 failed 才把这一层的码原样带到
    AgentResult.error 上。缺授权主体那几条沿用既有的 rejected 写法，一字不动。

    空码直接不写：一条 error_code 为空串的 failed 状态会凭空造出一个失败终态，
    把「本层说不出因由」错报成「执行边界报了失败」。
    """
    if not code:
        return
    record_tool_status(bag_from_config(config), tool=tool, status=status, error_code=code)


def _denial_text(config, *, tool: str, code: str, head: str) -> str:
    """两路一起走：码进证据袋，人话进返回值，两条路共用同一个 code 变量。

    正文格式沿用 R16 已定的那一条（search_docs 的「人话（error_code=码）」），不发明第二套。
    行级终态**不走这里**：R62 钉过那两句人话里不许出现裸码名，见 _row_scope_denial_text。
    """
    _record_denial(config, tool=tool, code=code)
    return f"{head}（error_code={code}）"


# 数据集准入闸由 analyze_data / query_data 共用，它不是任何一个工具的名字。拒绝发生在闸上，
# 取证标签就写闸名，不冒充工具名：码才是契约，标签只说明这条状态是从哪儿来的。
_DATASET_GATE = "dataset_access"


def _authorization_error() -> str:
    return "未找到：当前请求缺少有效授权主体（error_code=authorization_required）"


class DatasetsHiddenByScope(NamedTuple):
    """数据集准入闸的第三种回答：台账里登记着文件，而这一个账号一份都读不到。

    它不是异常，也不带文件名、部门归属、密级这些被挡资源的实际值——只带一个数量与一枚
    公开码。数量够工具说清「不是没有文件」，码够机器读；再多一个字，就是拿拒绝当借口把
    别人资源的元数据发出去了。
    """

    total: int
    code: str


#: 三张脸之一：本轮真的什么都没绑定（台账是空的）。这时候让人去上传是对的。
_NO_BOUND_DATASET_TEXT = (
    "本轮没有绑定任何数据文件：数据集台账里一个文件都没有。请先到数据分析面板上传 Excel/CSV 文件。"
)

#: 三张脸之二：有文件，但按当前权限读不到。措辞的目的很具体——让人去申请权限，而不是让人
#: 再传一次；「不是文件不存在」那一短句就是撞过这面墙的员工需要听到的那句话。
#: 终态的「（error_code=码）」由 _denial_text 统一拼，本层不发明第二套格式。
_HIDDEN_DATASETS_HEAD = (
    "本轮没有展示任何数据文件：台账里登记着数据文件，但按你当前的权限一份都读不到。"
    "这是权限判定，不是文件不存在——不需要重新上传，请找管理员为这个账号开通对应数据的读取权限。"
)


def _dataset_gate_terminal_code(codes: list[str]) -> str:
    """几份文件几种因由混在一起时取哪一枚码：说得出具体原因的优先，兜底码只在别无可选时用。

    与 _row_scope_terminal_code 同一个取法（具体的压过笼统的）。能走到这一步就说明每一份
    文件都被闸挡了，所以这里没有第三种事实可取；一张空表交不出码，而 _record_denial 对空码
    本来就不落状态（R64），本层也不替它硬造一枚。
    """
    for code in codes:
        if code != _POLICY_DENIAL_FALLBACK_CODE:
            return code
    return codes[0] if codes else ""


def _dataset_access_text(config, error: object) -> str:
    """把闸交回来的终态翻成这一条腿自己的人话：两条腿各有一句 return，漏一条就是第二张假话。

    闸能交出两种东西：一句已经拼好的拒绝原文（选中文件那两条分支），或一张
    ``DatasetsHiddenByScope``。后者必须在这一层变成话，否则调用方拿回去的是这个
    NamedTuple 的 repr——那是把「有，但你不能看」说得更难懂的新形态。
    """
    if isinstance(error, DatasetsHiddenByScope):
        return _denial_text(
            config, tool=_DATASET_GATE, code=error.code, head=_HIDDEN_DATASETS_HEAD
        )
    return str(error)


def _artifact_principal(config, action: str | None = None) -> object | None:
    try:
        principal = _tool_principal(config)
        if action and action not in principal.permissions:
            raise PermissionError("permission_denied")
        return principal
    except Exception as exc:
        logger.warning("[Tool] artifact creation denied: %s", exc)
        return None


def _artifact_urls(path: str, artifact_type: str, config) -> tuple[str, str] | None:
    artifact = _register_artifact(path, artifact_type, config)
    if artifact is None:
        return None
    return artifact.content_url, artifact.download_url


def _register_artifact(path: str, artifact_type: str, config):
    """Register a generated file and record it as evidence for this execution."""
    principal = _artifact_principal(config)
    if principal is None:
        return None
    from app.storage import artifacts as artifact_storage

    artifact = artifact_storage.register_artifact(
        path,
        artifact_type=artifact_type,
        principal=principal,
    )
    record_artifact(
        bag_from_config(config),
        artifact_id=artifact.artifact_id,
        artifact_type=artifact_type,
        owner_id=artifact.owner_id,
        version_id=artifact.source_version_id or "",
        download_url=artifact.download_url,
        expires_at=artifact.expires_at or "",
    )
    return artifact


def _authorized_dataset_files(
    config,
) -> "tuple[list[tuple[str, str]], str | DatasetsHiddenByScope | None]":
    """Resolve registered datasets after applying the same scope policy as API routes."""
    principal = _artifact_principal(config, ACTION_ANALYZE)
    if principal is None:
        _record_denial(
            config, tool=_DATASET_GATE, code="authorization_required", status="rejected"
        )
        return [], _authorization_error()

    from app.common.policy import authorization_decision
    from app.storage import datasets as dataset_storage

    conf = (config or {}).get("configurable", {}) or {}
    selected_filename = os.path.basename(str(conf.get("data_filename") or "").strip())
    if selected_filename:
        record = dataset_storage.dataset_registry.get_active_by_filename(selected_filename)
        if record is None:
            return [], _denial_text(
                config,
                tool=_DATASET_GATE,
                code="resource_not_found",
                head=f"未找到选中的数据文件：{selected_filename}",
            )
        decision = authorization_decision(
            principal,
            record.resource_scope,
            action=ACTION_ANALYZE,
            require_resource_scope=True,
        )
        if not decision.allowed:
            # 两路各走各的（R65 判据①「人话保留」的字面形态）：正文沿用 policy 的 reason，
            # 因为 tests/test_dataset_route_authorization.py:188 把这句钉在了可见文案上，改它
            # 要动的是别人写域里的文件（已登记为待裁残留）；而**契约字段只认映射表翻出来的
            # 枚举码**——判据⑤要防的正是把内部词表当公开码发出去。
            _record_denial(
                config,
                tool=_DATASET_GATE,
                code=_policy_denial_code(decision.reason_code),
            )
            return [], f"暂无可访问的数据文件（error_code={decision.reason_code}）"
        return [(record.filename, record.storage_path)], None

    records = list(dataset_storage.dataset_registry.active_records())
    permitted: list[tuple[str, str]] = []
    hidden_codes: list[str] = []
    for record in records:
        decision = authorization_decision(
            principal,
            record.resource_scope,
            action=ACTION_ANALYZE,
            require_resource_scope=True,
        )
        if decision.allowed:
            permitted.append((record.filename, record.storage_path))
        else:
            hidden_codes.append(_policy_denial_code(decision.reason_code))
    if not permitted and records:
        # 判定与顺序一个字都没动：还是逐条 authorization_decision，只是把「为什么空」带了出去。
        # 空表本身说不清自己是「没有文件」还是「有文件但读不到」，逼调用方猜，猜出来的就是
        # 员工最常撞的那句假话。空台账照旧交空表与 None，那是第一张脸，不是权限事实。
        return [], DatasetsHiddenByScope(len(records), _dataset_gate_terminal_code(hidden_codes))
    return permitted, None


def _record_dataset_evidence(config, filename: str, df) -> None:
    """Attach the real dataset identity behind an analysis result."""
    from app.storage import datasets as dataset_storage

    record = dataset_storage.dataset_registry.get_active_by_filename(filename)
    bag = bag_from_config(config)
    if bag is None:
        return
    record_dataset(
        bag,
        filename=filename,
        dataset_id=getattr(record, "dataset_id", "") if record is not None else "",
        version_id=getattr(record, "version_id", "") if record is not None else "",
        rows=int(getattr(df, "shape", (0, 0))[0]),
        columns=[str(column) for column in getattr(df, "columns", [])],
        department=str(getattr(record, "department", "") or "") if record is not None else "",
    )


def _answer_query(df, query: str, num_cols: list[str], txt_cols: list[str]) -> list[str]:
    """用 pandas 计算查询结果，返回简洁的分析文本"""
    import pandas as pd
    results = []

    q_lower = query.lower()
    first_num_col = num_cols[0] if num_cols else ""

    # R189 · 名字列也要按问法选。数值列那一支早就有"点名优先、点不出就不静默选"的规矩
    # （matched = [nc for nc in num_cols if nc in query] 连同注释 C3），文本列此前一律取 txt_cols[0]：
    # 帧 {姓名, 部门, 销售额} 上问「哪个部门销售额最高」，答案给的是人名 —— 员工看得见的一句假话。
    # 本单补的就是这枚不对称。取数方式与数值列同型（对 txt_cols 做 c in query），不另发明第二套匹配，
    # 也不叫模型来选列：这是纯本地 pandas 判定。名单的唯一出口仍是
    # app/tools/excel.py 的 select_text_columns()（本单一字未动）。
    named_txt_cols = [tc for tc in txt_cols if tc in query]
    if named_txt_cols:
        # 问法点名 => 用它；多列点名时取名单里第一枚，同数值列那一支的 matched[:1]。
        # 列名问题里已经说过，产物不加前缀 —— 与改前逐字节相同（也保住 R185 钉死的那行排名读数）。
        label_col, label_tag = named_txt_cols[0], ""
    elif len(txt_cols) > 1:
        # 判据 2 取 (a)"输出里显式带出按哪一列作答"，不取 (b)"照数值列先例逐列都给"，理由两条：
        #   1) 这段文本是直接进 prompt 的，装箱预算就卡在那儿。逐列都给在"排名前 N"那一支要把同一批
        #      数值行按每个候选名字列重播一遍，行数随候选列数线性翻倍，多出来的行只会把真结论挤出窗口；
        #      在排名答案那一支还要与数值列的 cols_use 相乘（多指标 x 多名字列），读数糊成一团。
        #   2) (a) 只多一个"列名="前缀：读的人看得见这一行是按哪一列给的，模型看得见下一句该点名谁，
        #      而"点名"与"只有一个候选"两种情形一个字节都不动。
        # 候选之间依然按名单顺序取第一枚（名单顺序＝列顺序，由 select_text_columns 守住），
        # 但这一枚会被标出来 —— 不再是静默选错列。
        label_col, label_tag = txt_cols[0], f"{txt_cols[0]}="
    else:
        label_col, label_tag = txt_cols[0] if txt_cols else "", ""

    def label_value(row) -> str:
        """三处消费（排名答案 / 前 N 名逐行标签 / 兜底预览）唯一的名字取值口。

        选列的结论只存在于上面那一处，本函数只做格式化 —— 三处各写一份 if 迟早各自漂移。
        """
        if not label_col:
            return ""
        return label_tag + str(row[label_col])

    # "哪个/谁最XX" → 排名第一
    m = re.search(r"(哪个|谁|哪家|哪).*?(最高|最低|最多|最少|最大|最小)", query)
    if m and txt_cols and num_cols:
        # C3: 优先精确匹配列名；多列且无匹配时所有数值列都给出，避免静默选错列
        matched = [nc for nc in num_cols if nc in query]
        if matched:
            cols_use = matched[:1]
        elif len(num_cols) > 1:
            cols_use = num_cols
        else:
            cols_use = [num_cols[0]]
        direction = m.group(2)
        for col in cols_use:
            if "低" in direction or "少" in direction or "小" in direction:
                row = df.loc[df[col].idxmin()]
            else:
                row = df.loc[df[col].idxmax()]
            name_val = label_value(row)
            results.append(f"🎯 {direction}({col}): {name_val} — {col}={row[col]}")

    # "排名/排序" → top N
    if any(kw in q_lower for kw in ["排名", "排序", "前", "top", "降序", "升序"]):
        sort_col = None
        for nc in num_cols:
            if nc in query:
                sort_col = nc
                break
        if not sort_col and "利润" in query:
            for nc in num_cols:
                if "利润" in nc:
                    sort_col = nc
                    break
        if not sort_col:
            sort_col = first_num_col or num_cols[0]
        top_n = 10
        m = re.search(r"前\s*(\d+)", query)
        if m:
            top_n = int(m.group(1))
        sorted_df = df.sort_values(sort_col, ascending=False).head(top_n)
        lines = [f"📊 按 {sort_col} 排名前{top_n}:"]
        for _, r in sorted_df.iterrows():
            name = label_value(r)
            vals = ", ".join(f"{c}={r[c]}" for c in num_cols[:3])
            lines.append(f"  {name}: {vals}")
        results.append("\n".join(lines))

    # "统计/汇总/平均/合计" → describe
    if any(kw in q_lower for kw in ["统计", "汇总", "平均", "合计", "总计", "概括", "概览"]):
        if num_cols:
            desc = df[num_cols].describe().to_dict()
            # describe() has no sum row, so 合计 printed N/A for a frame whose upload
            # profile had already reported that same total correctly.
            totals = {column: float(df[column].sum()) for column in num_cols}
            lines = [f"📈 数值统计 ({len(num_cols)}个指标):"]
            for stat in ["mean", "min", "max", "sum"]:
                stat_name = {"mean": "均值", "min": "最小", "max": "最大", "sum": "合计"}
                parts = []
                for column in num_cols[:5]:
                    value = totals[column] if stat == "sum" else desc.get(column, {}).get(stat)
                    usable = isinstance(value, (int, float)) and value == value
                    parts.append(f"{column}: {value:.1f}" if usable else f"{column}: N/A")
                lines.append(f"  {stat_name[stat]}: " + ", ".join(parts))
            results.append("\n".join(lines))

    # "对比/比较" → groupby
    if any(kw in q_lower for kw in ["对比", "比较", "分组", "按区域", "按类型"]):
        group_col = None
        for tc in txt_cols:
            if tc in query:
                group_col = tc
                break
        if not group_col:
            for tc in txt_cols:
                n_unique = df[tc].nunique()
                if 2 <= n_unique <= 20:
                    group_col = tc
                    break
        if group_col and num_cols:
            agg = df.groupby(group_col)[num_cols[:3]].sum()
            lines = [f"📋 按 {group_col} 分组汇总:"]
            for idx, row in agg.iterrows():
                vals = ", ".join(f"{c}={v:.1f}" for c, v in row.items())
                lines.append(f"  {idx}: {vals}")
            results.append("\n".join(lines))

    # 兜底：返回基本统计
    if not results and num_cols:
        sorted_df = df.sort_values(num_cols[0], ascending=False).head(10)
        lines = [f"📊 数据预览 (按{num_cols[0]}降序):"]
        for _, r in sorted_df.iterrows():
            name = label_value(r)
            vals = ", ".join(f"{c}={r[c]}" for c in num_cols[:3])
            lines.append(f"  {name}: {vals}")
        results.append("\n".join(lines))

    return results

# ==================== Doc Tool ====================

# 全局单例，避免每次搜索都重建 pipeline（BM25索引/CrossEncoder/Embedding）
# threading.Lock 防止并发请求同时初始化（竞态条件导致多个 BM25 索引重复构建）
import threading
_search_pipeline = None
_pipeline_lock = threading.Lock()

# ==================== R112 · 返回串装箱：doc 腿与 data 腿共用一层 ====================
#
# 容量真源与两枚实测预留都在 ``app/rag/retrieval_pipeline.py`` 的装箱那一节（那里写清了
# 为什么是 ``input_budget_tokens``、为什么不能在代码里再抄一枚 2560/4096）。本层只做两件
# 只有本层能做的事：
#   ① 把真的要塞回模型的字符串装进本轮剩余的 room；
#   ② 把"丢几条、装进几条、装箱后 prompt 多少 token"打成一行 ``[PromptPack]`` 账。
#
# 为什么还要一枚累加的账：同一个 worker 步里模型可以一次并发发好几发工具调用（DOC_PROMPT
# 自己就写着"一次想好几个搜索方向，同时搜多个关键词"），每一发的返回串都会留在 prompt 里。
# 只按"单发别超过 room"装，两发各自装满照样撞墙——真机 doc-12 那枚 prompt_tokens=3897
# 就是这个形状。所以第二发只许用剩下的 room。
# 账挂在**轮身份**上（见 ``_pack_ledger_key``），不是会话身份。为什么不能按 thread：R114 复测
# （跟进单 §55）量出 worker 子图在真装配下**每轮冷启动**——langgraph 给嵌套子图注入的
# ``checkpoint_ns`` 逐轮换 uuid，``{父会话}:{worker}`` 那份 checkpointer 根本 resume 不回来，
# 上一轮的检索串这一轮并不在 prompt 里。账按 ``thread + worker`` 跨轮累减，等于为一笔不在上下文
# 里的料一直占房：room=1606 时同一份料连问四轮就把 room 扣穿，第四起少装、第五起整批发空。
# 同轮内并发多发仍必须累加：那些串确实同时在一次 prompt 里，真机 doc-12 的 prompt_tokens=3897
# 就是这个形状防的。取不到轮身份时才退回按 thread 累加（宁可少装，也不许同一轮并发多发各自吃满
# room）；连 thread 都没有（直接调工具的测试、MCP 单次调用）就按单发装箱、不跨调用累加，也不假
# 装它们是同一条会话。

_pack_lock = threading.Lock()
#: 装箱账：账本键 → 这一本账上已经吃掉多少 prompt token。见 ``_pack_ledger_key``。
_pack_ledger: "OrderedDict[str, int]" = OrderedDict()
#: 账本上限：进程内长跑时旧会话/旧 step 不再回来，超上限就丢最早那些，不留无界字典。
_STEP_PACK_LEDGER_MAX = 256
#: ``search_for_principal`` 认不认 ``context_pack``，按实现类缓存一次签名检查。
_retrieval_pack_support: "OrderedDict[str, bool]" = OrderedDict()

#: 一条都装不下时留给"必须保住的那一条"的截断标记。宁可让模型看到最高分那条的前半段，
#: 也不要真机那种 evidence_n=0 的整题空手；标记本身也计进 room，不留暗账。
PACK_TRUNCATION_MARK = "…（上下文装箱截断）"
#: R122 给上面那句"宁可看到前半段"补了一条下限：只有**裁出来的正文够读**才交（见
#: ``PACK_MIN_STUB_BODY_TOKENS``）。半条命中是好事，只剩几个字的正文不是——那是一条看着
#: 像证据的空壳，模型会照着它编答案。够不上门槛就改交「本轮检索预算已用尽」那句人话。

#: ``[PromptPack]`` 台账新字段 ``stub=`` 的三枚取值（R122 判据 ③）。🔴 台账既有字段一枚
#: 不改名、不改相对顺序（run3/run4 的日志口径要连续），这一枚只新增，插在 ``truncated=`` 之后。
PACK_STUB_NONE = "none"        # 这一发没有"桩"这件事：整批装下了，或连标记都裁不出来
PACK_STUB_KEPT = "kept"        # 桩达标，交出去了（与 ``truncated=1`` 同现）
PACK_STUB_REFUSED = "refused"  # 桩低于门槛没交，改说「本轮检索预算已用尽」那句人话

#: 桩的最低可交付**正文**长度（枚＝``text_pack_tokens`` 那把尺；行头与截断标记都不算正文）。
#: 这个数不是抄跟进单 §55A 的建议值，是本树知识库两枚独立采样框量出来的：
#:   甲 本树 ``chroma_db`` 在册 401 枚 chunk：整条正文长度 p05=76 / p25=175 / p50=262 / max=459；
#:   乙 ``documents/*.txt`` 95 份原文按生产 splitter(500/50) 重切 379 枚：p05=88 / p25=186 / p50=276。
#: 两框同一形状："到第一个完整句尾需要多少枚正文" p50=55 / p75=76 / mean=67；分箱实测正文
#: <40 枚的桩 0% 含完整句、<60 枚的桩 ≤34.6% 含完整句。§55A 真机那枚 ``packed=31`` 的桩，按
#: 行头 18 枚＋标记 10 枚算只剩 3 枚正文；同样 room_left=31 拿本树真语料裁，正文中位数 6 枚。
#: 取 60＝中位那句完整话的下边界，同时压在真料 p05(76) 之下：真料够不着这条线，被拦的只可能是
#: 残料。复测＝``tests/test_r122_stub_honesty.py`` 的
#: ``test_stub_threshold_sits_in_the_measured_band``。
PACK_MIN_STUB_BODY_TOKENS = 60


#: 轮身份字段与优先级：全部是请求路径上已有的字段（``orchestrator.py`` 造 configurable 时
#: 写进来的那一批），本模块不新开 contextvar、不新造全局计数器。键前缀就是身份名，
#: ``[PromptPack]`` 的 ``ledger`` 字段直接读它，字段名一枚都不动。
_PACK_TURN_KEYS = (
    ("step_id", "step"),
    ("request_id", "request"),
    ("task_id", "task"),
    ("trace_id", "trace"),
)


def _pack_ledger_key(config) -> str:
    """这一发工具调用该记在哪一本装箱账上；认不出身份就返回空串（＝不累加）。

    轮身份优先。``step_id`` 由装配点造成 ``{trace_id}:worker:{name}``，本身就是一轮一 worker
    一枚：同轮并发多发共用它（照旧互相扣房），下一轮 trace_id 一换就是新账（跨轮不累加）。
    ``request_id``/``task_id``/``trace_id`` 留给 step_id 没造出来的入口（父层没给 trace 的调用、
    可靠队列道），它们同样逐轮新生成，只是不含 worker，所以键里自己补一枚——同一轮里并行跑的
    doc 与 data 不许互相扣房。三样都没有才退回 ``thread + worker``：那个顺序是"宁可少装"，
    不许把同一轮的并发多发放回各自的满 room 上。
    """
    conf = (config or {}).get("configurable", {}) or {}
    worker = str(conf.get("worker") or "").strip()
    for field, kind in _PACK_TURN_KEYS:
        value = str(conf.get(field) or "").strip()
        if not value:
            continue
        if kind == "step":
            return "step:" + value
        return kind + ":" + value + ":" + worker
    thread = str(conf.get("thread_id") or "").strip()
    if thread:
        return "thread:" + thread + ":" + worker
    return ""


def _fit_unit_to_room(text: str, room_tokens: int) -> str:
    """整批一条都装不下时的最后一档：按 room 二分裁这一条，裁完贴上可见的截断标记。"""
    from app.rag.retrieval_pipeline import text_pack_tokens

    if text_pack_tokens(text) <= room_tokens:
        return text
    if room_tokens <= text_pack_tokens(PACK_TRUNCATION_MARK):
        return ""
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if text_pack_tokens(text[:mid] + PACK_TRUNCATION_MARK) <= room_tokens:
            low = mid
        else:
            high = mid - 1
    return (text[:low] + PACK_TRUNCATION_MARK) if low > 0 else ""


def _stub_body_tokens(stub: str, original: str) -> int:
    """这一枚桩真正送出去了多少枚**正文**：行头与截断标记都不算。

    判"够不够读"不能拿 ``text_pack_tokens(stub)`` 当尺——§55A 真机那枚 ``packed=31`` 里行头占
    18 枚、标记占 10 枚，正文只剩 3 枚，账上看着有数、模型读到的是一条空壳。裁到行头之内
    （连一个字正文都没送出去）按 0 枚算；原条本来就没有换行（没有行头可言）时，裁出来的
    整段都是正文，照实计。
    """
    from app.rag.retrieval_pipeline import text_pack_tokens

    body = stub[: -len(PACK_TRUNCATION_MARK)] if stub.endswith(PACK_TRUNCATION_MARK) else stub
    header, sep, _ = original.partition("\n")
    if sep:
        if not body.startswith(header + "\n"):
            return 0
        body = body[len(header) + 1 :]
    return text_pack_tokens(body)


def _pack_dropped_labels(dropped, limit: int = 3) -> str:
    """被丢单元的前 30 字摘要，最多三枚：账要能指着名字核，但不能把正文再喷回日志。"""
    dropped = list(dropped)
    labels = [str(unit).replace("\n", " ")[:30] for unit in dropped[:limit]]
    if len(dropped) > len(labels):
        labels.append("…+" + str(len(dropped) - len(labels)))
    return ",".join(labels) or "-"


def context_pack_room_public() -> int:
    """给文案与测试用的 room 读数：转读真源，不在此处抄数。"""
    from app.rag.retrieval_pipeline import context_pack_room

    return context_pack_room()


def _no_room_text(leg: str, candidates: int) -> str:
    """裁无可裁时工具自己说的那一句：指名是本题检索料/数据结果超出本机上下文。

    这既是判据 3 要的"与模型坏了分色"，也是判据 2 要的"丢得不静默"：它说清了几条候选、
    本机 room 是多少，客户与运维都不会把它读成"模型挂了"。
    """
    subject = "文档检索料" if leg == "doc" else "数据查询结果"
    return (
        f"本轮{subject}共 {candidates} 条，但没有一条装得进本机上下文窗口"
        f"（装箱后剩余 room={context_pack_room_public()} token）：是本题的{subject}超出本机上下文，"
        "不是模型故障。请缩小提问范围或换更具体的关键词后重试。"
    )


def _budget_exhausted_text(ledger_used: int, room_left: int) -> str:
    """桩低于门槛时工具自己说的那一句人话（R122 判据 ②）：不交假料，改报预算。

    两个数都是这一发账上的真数，不是写死的文案：``ledger_used`` 是本轮装箱已经装进 prompt 的
    token 数（台账里的 ``ledger_packed_tokens``），``room_left`` 是本轮还剩的 room（台账里的
    ``room_left``），枚＝token，与 ``[PromptPack]`` 同一把尺。这句话还必须与"没检索到"和
    "模型坏了"分色：它说的只是**这一发的预算**，前面几发取回的料仍在 prompt 里。
    """
    return (
        f"本轮检索预算已用尽，未取回新料（已装 {int(ledger_used)} 枚 / 剩 {int(room_left)} 枚）："
        f"剩下的上下文装不下一段满 {PACK_MIN_STUB_BODY_TOKENS} 枚正文的料，交回来只是一条读不出结论的空壳。"
        "这不是模型故障，也不是没检索到：请基于本轮前面已经取回的材料作答，别再往同一个方向检索。"
    )


class _PackedUnits(list):
    """装进 prompt 的那几段本身，顺手带上这一发的账：``len()`` 即送出的条数。

    ``list`` 语义一个字都不变（判空、``join``、按下标取都一样），所以三条腿的返回串照旧
    拼；多出来的这几个字段是给调用方把"真送出去的那几条"翻译给证据袋与 span summary 用的，
    免得那边为了知道丢了几条再算一遍。
    """

    def __init__(
        self,
        units,
        *,
        dropped_count: int = 0,
        truncated_count: int = 0,
        packed_tokens: int = 0,
        room_left: int = 0,
        stub: str = PACK_STUB_NONE,
        ledger_used: int = 0,
    ) -> None:
        super().__init__(units)
        self.dropped_count = int(dropped_count)
        self.truncated_count = int(truncated_count)
        self.packed_tokens = int(packed_tokens)
        self.room_left = int(room_left)
        #: 这一发的桩：发出去了(``kept``)、被门槛拦下(``refused``)、压根没有(``none``)。
        #: 与 ``[PromptPack]`` 的 ``stub=`` 字段同值，调用方靠它决定该说哪句人话。
        self.stub: str = stub
        #: 本轮装箱在这一发之前已经吃掉的 token 数——「已装 N 枚」里的那个 N。
        self.ledger_used = int(ledger_used)


def _empty_pack_text(leg: str, candidates: int, packed: _PackedUnits) -> str:
    """一发装箱空手时该说哪句人话：桩被门槛拦下说「预算用尽」，其余仍说「本题料超窗」。

    两条路的差别是真数：``room_left`` 已经贴地（room=0 那一发）与本轮已装掉大半、只剩几十枚
    残料，是两件不同的事，不能共用一句"没有一条装得进上下文窗口"。
    """
    if packed.stub == PACK_STUB_REFUSED:
        return _budget_exhausted_text(packed.ledger_used, packed.room_left)
    return _no_room_text(leg, candidates)


def _pack_kept_hits(hits: list, units: list, fitted: list) -> list:
    """把真送出去的那几段翻译回 hit：装箱只裁尾巴，所以 ``fitted`` 恒为 ``units`` 的前缀。

    被 ``_fit_unit_to_room`` 裁过尾的那一条（只可能是第一条）按**实际送出的正文**交给证据袋，
    免得 ``excerpt`` 与 ``content_sha256`` 说"模型读过整段"而它其实只读到裁过的那一截。认不出
    这种前缀关系就退回原条并留一行警告：宁可正文少诚实一点，也不许少记一条模型真读过的来源。
    """
    kept: list = []
    for index, unit in enumerate(fitted):
        original = units[index]
        if unit == original:
            kept.append(hits[index])
            continue
        sent = unit[: -len(PACK_TRUNCATION_MARK)] if unit.endswith(PACK_TRUNCATION_MARK) else unit
        if not original.startswith(sent):
            logger.warning(
                "[PromptPack] 装箱前缀不变量被打破（第 %s 段不是裁尾片段）：证据袋按原条记", index + 1
            )
            kept.append(hits[index])
            continue
        header, _, _ = original.partition("\n")
        body = sent[len(header) + 1:] if sent.startswith(header + "\n") else ""
        kept.append({**hits[index], "content": body})
    return kept


def _retrieval_supports_context_pack(pipeline) -> bool:
    """这条检索腿的实现认不认 ``context_pack`` 这个参数（按类缓存，认一次算一次）。

    认就在最终 top-k 处先裁一刀；不认（旧签名的子类、采集替身）就照旧调用。装箱的第二层
    在本文件里，无论如何都会装：绝不能因为多传一个参数，把一次正常检索变成
    ``retrieval_unavailable``——那是把可用性洞换成新的可用性洞。
    """
    key = f"{type(pipeline).__module__}.{type(pipeline).__qualname__}"
    cached = _retrieval_pack_support.get(key)
    if cached is None:
        try:
            cached = "context_pack" in inspect.signature(
                pipeline.search_for_principal
            ).parameters
        except (TypeError, ValueError):  # 内置可调用对象没有可读签名：按不认处理
            cached = False
        _retrieval_pack_support[key] = cached
    return cached


def _pack_into_prompt_room(config, *, leg: str, units, keep_first_truncated: bool = False) -> list:
    """按名次把 ``units`` 装进本轮剩余 room，打一行的账，返回装进去的那几段。

    ``units`` 必须已按优先级从高到低排好（检索腿回来的顺序就是 RRF/重排分数降序，数据腿
    按文件与结论的既有顺序）：装箱只从尾部裁，不在这里重新发明排序。

    ``keep_first_truncated``（R122 加了门槛）：整批一条都装不下时，本来会裁最高分那一条的
    尾巴当桩交出去。桩的正文短于 ``PACK_MIN_STUB_BODY_TOKENS`` 就不交了——那一发是空手，
    ``stub=refused`` 入账，由调用方说「本轮检索预算已用尽」。达标才交，交出去照旧记
    ``truncated=1 stub=kept``。
    """
    from app.rag.retrieval_pipeline import (
        CONTEXT_HISTORY_RESERVE_TOKENS,
        CONTEXT_PACK_TIER,
        CONTEXT_SHELL_RESERVE_TOKENS,
        PROMPT_PACK_MARKER,
        context_pack_room,
        pack_prefix_by_rank,
        text_pack_tokens,
    )

    units = list(units)
    room_total = context_pack_room()
    key = _pack_ledger_key(config)
    with _pack_lock:
        used = _pack_ledger.get(key, 0) if key else 0
        room = max(0, room_total - used)
        fitted, dropped, packed_tokens = pack_prefix_by_rank(units, room)
        truncated = 0
        stub = PACK_STUB_NONE
        if not fitted and units and keep_first_truncated:
            head = _fit_unit_to_room(str(units[0]), room)
            if head:
                if _stub_body_tokens(head, str(units[0])) >= PACK_MIN_STUB_BODY_TOKENS:
                    fitted, dropped, truncated = [head], units[1:], 1
                    packed_tokens = text_pack_tokens(head)
                    stub = PACK_STUB_KEPT
                else:
                    # R122 判据 ①②：低于门槛的桩不交，宁可这一发空手说人话，也不许把一条看着像
                    # 证据、其实只剩几个字的空壳当检索结果交出去。没送出去就不记账（不记假消耗）。
                    stub = PACK_STUB_REFUSED
            # head 为空＝连截断标记都装不下：照旧空手，由调用方说「本题料超窗」那一句
        if key and packed_tokens:
            _pack_ledger[key] = used + packed_tokens
            _pack_ledger.move_to_end(key)
            while len(_pack_ledger) > _STEP_PACK_LEDGER_MAX:
                _pack_ledger.popitem(last=False)
        billed = used + packed_tokens
    reserve = CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS
    #: 账本身份名＝键前缀（step/request/task/thread/off），``[PromptPack]`` 的字段一枚不改名。
    ledger_kind = key.split(":", 1)[0] if key else "off"
    logger.info(
        f"{PROMPT_PACK_MARKER} leg={leg} tier={CONTEXT_PACK_TIER} room_total={room_total} "
        f"room_left={room} candidates={len(units)} fitted={len(fitted)} dropped={len(dropped)} "
        f"truncated={truncated} stub={stub} packed_tokens={packed_tokens} ledger_packed_tokens={billed} "
        f"prompt_estimate_tokens={reserve + billed} ledger={ledger_kind} "
        f"dropped_labels={_pack_dropped_labels(dropped)}"
    )
    return _PackedUnits(
        fitted,
        dropped_count=len(dropped),
        truncated_count=truncated,
        packed_tokens=packed_tokens,
        room_left=room,
        stub=stub,
        ledger_used=used,
    )


def _get_pipeline():
    global _search_pipeline
    if _search_pipeline is None:
        with _pipeline_lock:
            if _search_pipeline is None:  # double-check
                from app.rag.retrieval_pipeline import RetrievalPipeline
                _search_pipeline = RetrievalPipeline()
    return _search_pipeline


def preload_pipeline():
    """启动时预加载 RAG pipeline（BM25索引 + CrossEncoder），避免首个请求等待 10s+"""
    p = _get_pipeline()
    p.preload()


def rebuild_bm25():
    """C1: 文档增删后重建 BM25 索引，新文档免重启即可被关键词检索"""
    if _search_pipeline is not None:
        _search_pipeline.bm25.build_index()
        logger.info("[BM25] 索引已重建")


@tool
def search_docs(query: str, config: RunnableConfig) -> str:
    """
    搜索公司内部文档知识库。用于查找：公司制度、报销流程、请假规定、产品规格、
    技术架构、客户案例、定价策略、安全规范、操作手册等所有文档类信息。
    如果第一次搜索返回不够，可以换个关键词再搜。
    权限：必须从调用上下文取得有效身份，缺少身份时拒绝检索。
    """
    try:
        principal = _tool_principal(config)
    except PermissionError:
        record_tool_status(
            bag_from_config(config), tool="search_docs", status="rejected", error_code="authorization_required"
        )
        return _authorization_error()

    with start_tool_call(config, tool_name="search_docs", arguments={"query": query}) as span:
        pipeline = _get_pipeline()
        try:
            retrieval_kwargs = {
                "top_k": 5,
            }
            if _retrieval_supports_context_pack(pipeline):
                # R112：这条腿的结果直接拼进 prompt，所以最终 top-k 先按 room 裁一刀。
                retrieval_kwargs["context_pack"] = True
            docs, rewrites = pipeline.search_for_principal(query, principal, **retrieval_kwargs)
        except Exception as exc:
            # 上游异常能塞任意 code：先过枚举，落到枚举内才开始说话（R65 判据②）。
            code = _public_error_code(getattr(exc, "code", ""), "retrieval_unavailable")
            logger.warning("[Tool] document retrieval unavailable: %s", exc)
            span.finish("retrieval_unavailable", error_code=code)
            return f"文档检索不可用（error_code={code}）"

        if not docs:
            span.finish("empty", summary={"hit_count": 0, "rewrite_count": len(rewrites or [])})
            return f"未找到与'{query}'相关的文档信息。建议尝试以下改写角度的关键词：{', '.join(rewrites[:3])}"

        from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS, format_relevance

        result_parts = []
        for i, d in enumerate(docs, 1):
            source = d.get("source", "unknown")
            score = format_relevance(d)
            content = d["content"][:DOC_HIT_CONTENT_CHARS]
            result_parts.append(f"[{i}] 来源:{source} 相关度:{score}\n{content}")

        # R112：装箱之后才是发给模型的返回串。装不下丢名次最低的整条；整批都装不下才裁最高分
        # 那一条的正文尾巴（``keep_first_truncated``），连一帧都装不下时才说人话并留下账。
        # R122：那条尾巴短到读不出结论（正文不足 ``PACK_MIN_STUB_BODY_TOKENS``）就不交了，改说
        # 「本轮检索预算已用尽」——半条命中是证据，六个字不是。三条腿共用这一枚门槛。
        fitted = _pack_into_prompt_room(
            config, leg="doc", units=result_parts, keep_first_truncated=True
        )
        # R112 复验第 2 条：证据袋与这一发 span 只许说"模型真读到过的那几条"。这两件事以前在
        # 装箱之前结清，于是装进 3 条却对外报 5 条——答案引用一条被丢掉的材料时
        # evidence_coverage 仍显示它有出处，那是出处撒谎（R36 的诚实性边界）。summary 同时给
        # 找回/送出/丢掉/裁过四个数：整批判空那一发也读得出 hit_count>0 而 packed_count=0，
        # 不会被下游误读成"没检索到"（那条路是上面 status="empty" 那一发）。
        record_document_hits(
            bag_from_config(config),
            query=query,
            hits=_pack_kept_hits(docs, result_parts, fitted),
        )
        span.finish(
            "completed",
            summary={
                "hit_count": len(docs),
                "packed_count": len(fitted),
                "dropped_count": fitted.dropped_count,
                "truncated": fitted.truncated_count,
                "rewrite_count": len(rewrites or []),
            },
        )
        if not fitted:
            return _empty_pack_text("doc", len(result_parts), fitted)
        return "\n\n---\n\n".join(fitted)


# ==================== Data Tool ====================

# ---- R62：行级口径「为什么看不见」的文案层 ------------------------------------
# 判定的唯一出处是 app/common/rbac.py::filter_dataframe_rows，本层一行都不重判：
# reason_code 与计数字段全部来自 rbac.filter_dataframe_rows_with_scope 的元数据
# （键名 rbac.ROW_SCOPE_ATTR）。密级维度属 H13（业主未裁口径），这里既不动它、也不对它下结论。
_NO_VISIBLE_ROWS = "当前账号没有可见数据行"
_QUERY_DENIED_HEAD = "查询未完成：这些数据文件的行不在当前账号的可见范围内，本轮没有向你展示任何一行。"
_QUERY_DENIED_HINT = "若这些数据本该对你可见，请让管理员核对你的部门归属，以及这些文件的部门标注。"


def _row_scope_reason(info: dict | None) -> str:
    """把「这一帧为什么一行不剩」翻译成人话；翻译不出因由就返回空串。

    空串＝本层拒绝猜因由（表本来就是空的、管理员、部门维度根本没藏过行），调用方必须退回
    中性文案。本单的全部风险都在这句话上：没有依据的因由不能说成权限，反之也不能把权限
    说成「查询没通过」。
    """
    if not info:
        return ""
    reason = str(info.get("reason_code") or "")
    rows_in = int(info.get("rows_in") or 0)
    if rows_in <= 0 or reason == "administrator_scope":
        return ""
    if reason == "department_column_missing":
        # 这一支必须空手回去。``rows_hidden_by_department`` 在 ``department_column_missing`` 下**恒为 0**
        # （rbac 只在「表有部门列」的路径上记部门维度的隐藏行），也就是部门维度一行都没藏过，
        # 这帧是被另一个维度清空的——而那个维度的口径属 H13（业主未裁），本单明文不许对它下结论。
        # 判据①的正解＝说不清因由就不说：写成「本表没有部门列……过滤后一行不剩」是把别的维度的账
        # 挂到部门列上（张冠李戴），且 ``rows_in`` 还是那道过滤**之前**的计数，连数都不对。
        # 本层自己在 department_scope 分支立的同一规矩（部门维度没藏过就不下结论）不许在这里绕过。
        return ""

    blank = int(info.get("rows_hidden_blank_department") or 0)
    accountless = int(info.get("rows_hidden_account_department") or 0)
    department_hidden = int(info.get("rows_hidden_by_department") or 0)
    foreign = max(0, department_hidden - blank - accountless)

    if reason == "authorization_unavailable":
        return f"当前账号没有部门归属，本表 {rows_in} 行全部不可见"
    if reason == "department_scope":
        bits = []
        if blank:
            bits.append(f"{blank} 行未标注部门")
        if foreign:
            bits.append(f"{foreign} 行属于其他部门")
        if not bits:
            # 部门维度一行都没藏过：这帧是被别的维度清空的，本单不许对它下结论。
            return ""
        account_department = str(info.get("account_department") or "")
        who = f"（部门「{account_department}」）" if account_department else ""
        all_marker = "都" if len(bits) > 1 else ""
        return f"本表 {'、'.join(bits)}，{all_marker}不在当前账号{who}的可见范围内"
    if reason == "legacy_open_department_scope":
        hidden = foreign or department_hidden
        if not hidden:
            return ""
        return f"本表 {hidden} 行属于其他部门，不在当前账号的可见范围内（行级口径已回退为放宽档）"
    return ""


def _row_scope_line(filename: str, info: dict | None) -> str:
    """``_analyze_data`` 逐文件那一行：能报因由就报因由，报不出就退回中性文案。"""
    reason = _row_scope_reason(info)
    if reason:
        return f"📧 {filename}: {reason}"
    if int((info or {}).get("rows_in") or 0) <= 0:
        return f"📧 {filename}: 文件里没有数据行"
    return f"📧 {filename}: {_NO_VISIBLE_ROWS}"


# ---- R64：行级终态的结构化码层（紧挨着上面的文案层，共用同一条判据源）------------
# 上面那张表把「为什么看不见」翻译给人看，这里把同一件事翻译成给机器看的码。两边都只读
# rbac 的 reason_code，且都必须先过 _row_scope_reason：文案空手回去的那一支（表本来就是
# 空的、因由根本不在部门维度上），码也一律落到 no_visible_rows——只说「本轮没有可见行」
# 这个事实，不替没裁的维度下结论。判据源只有一个，码与人话不可能各说各话。
_ROW_SCOPE_PUBLIC_CODES = {
    "department_scope": _ROW_SCOPE_DENIED_CODE,
    "authorization_unavailable": _ROW_SCOPE_DENIED_CODE,
    "legacy_open_department_scope": _ROW_SCOPE_DENIED_CODE,
}


def _row_scope_code(info: dict | None) -> str:
    """一帧被行级口径清空之后的稳定码；与 _row_scope_reason 共用同一个判据。"""
    if not _row_scope_reason(info):
        return _NO_VISIBLE_ROWS_CODE
    reason = str((info or {}).get("reason_code") or "")
    return _ROW_SCOPE_PUBLIC_CODES.get(reason, _NO_VISIBLE_ROWS_CODE)


def _row_scope_terminal_code(codes: list[str]) -> str:
    """多张表混合时取哪一个码：口径拒绝优先于「没有可见行」。

    至少有一张表是被行级口径挡掉的，就没有任何一条断言比这句更该报出去；全是「没有可见
    行」时才报 no_visible_rows。一张表都没走到行级过滤（读都读不出来）时不给码——那种
    终态的因由不在本层，硬编一个就是瞎猜。
    """
    if _ROW_SCOPE_DENIED_CODE in codes:
        return _ROW_SCOPE_DENIED_CODE
    return _NO_VISIBLE_ROWS_CODE if codes else ""


def _row_scope_denial_text(
    config,
    *,
    tool: str,
    head: str,
    reasons: list[str],
    codes: list[str],
    tail: str = "",
) -> str:
    """把若干文件的行级因由拼成终态，同时把这一轮的码交给结构化那一路。

    人话（reasons/tail）由调用方原样给——R62 那两段成品句子在这里逐字复用，一个字都不改；
    码（codes）是逐文件算出来的稳定码，取哪一个由 _row_scope_terminal_code 说。两条路
    共用同一批输入，所以这个函数存在的唯一意义就是：让终态多一条机器读得懂的路。
    """
    _record_denial(config, tool=tool, code=_row_scope_terminal_code(codes))
    return "\n".join([head, *reasons, tail] if tail else [head, *reasons])


def _analyze_data(query: str, config: RunnableConfig) -> str:
    from app.common.rbac import filter_dataframe_rows_with_scope
    from app.tools.excel import load_excel, profile_dataframe, select_text_columns
    context = _tool_context(config)
    if context is None:
        record_tool_status(
            bag_from_config(config), tool="analyze_data", status="rejected", error_code="authorization_required"
        )
        return "暂无数据：当前请求缺少有效授权主体（error_code=authorization_required）"
    conf = (config or {}).get("configurable", {}) or {}
    role = context["role"]
    dept = context["department"]
    files, dataset_error = _authorized_dataset_files(config)
    if dataset_error is not None:
        return _dataset_access_text(config, dataset_error)
    if not files:
        # 走到这里才是真的「本轮没有绑定任何数据文件」：台账是空的，一句都不提权限。
        return _NO_BOUND_DATASET_TEXT

    parts = []
    scope_codes: list[str] = []
    produced = 0
    #: (文件名, 该文件过滤后的帧, 它进 prompt 的第一段下标)：装箱证明送出去了才记证据袋
    pending_datasets: "list[tuple[str, object, int]]" = []
    for fname, file_path in files:
        try:
            df = load_excel(file_path)
            df, scope_info = filter_dataframe_rows_with_scope(df, role=role, department=dept)
            if df.empty:
                # 码与文案同判据源：一个给机器，一个给人看，同一条 reason_code。
                scope_codes.append(_row_scope_code(scope_info))
                parts.append(_row_scope_line(fname, scope_info))
                continue
            produced += 1
            pending_datasets.append((fname, df, len(parts)))
            profile = profile_dataframe(df)
            cols_info = [f"{c['name']}({c['dtype']})" if isinstance(c, dict) else str(c) for c in profile["columns"]]
            parts.append(f"📁 {fname}: {profile['rows']}行 × {len(cols_info)}列 — 列: {', '.join(cols_info)}")

            # 根据 query 计算具体答案
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            # R185：文本列名单走 excel 那一族语义谓词的唯一出口，不再自己比 dtype 字面串。
            # 旧写法只靠 pandas 3 那条声明要移除的兼容通道才勉强捞到 str 列，string/category 两族当场漏。
            text_cols = select_text_columns(df)

            try:
                ai_parts = _answer_query(df, query, numeric_cols, text_cols)
                parts.extend(ai_parts)
            except Exception:
                pass

            # 返回前 15 行数据用于图表
            try:
                sample = df.head(15).to_dict(orient="records")
                parts.append("--- 数据样本(前15行) ---")
                parts.append(json.dumps(sample, ensure_ascii=False, default=str))
            except Exception:
                pass
        except Exception as e:
            parts.append(f"📁 {fname}: 读取失败 - {e}")

    if not produced:
        # 没有任何一帧进到分析里，这一轮才谈得上行级终态；逐文件的因由仍然只在文案里。
        # 一张表都没走到行级过滤（全读不出来）时 scope_codes 是空的，本层不下结论。
        _record_denial(
            config,
            tool="analyze_data",
            code=_row_scope_terminal_code(scope_codes),
        )

    # R112：这段直接进 prompt，而且多文件时是"每文件 概览 + 结论 + 15 行样本 JSON"顺着
    # 往后可无限长。装箱按既有顺序从尾部裁——先掉的必然是样本 JSON 那种大块，其次才是
    # 后一个文件；一条都装不下时说清是本题数据结果超窗，不静默（判据 2/3）。
    # R122：整批装不下时会裁 parts[0] 当桩，桩的正文不够门槛就不交，改说「预算用尽」——
    # 第一个文件的文件名那一行不是分析结论，模型读不出数。
    fitted = _pack_into_prompt_room(
        config, leg="data", units=parts, keep_first_truncated=True
    )
    # R112 复验第 2 条（与 doc 腿同一读法）：装箱没送出去的那个文件，证据袋不许说模型读过它。
    # 存活线就是前缀长度——装箱只裁尾巴，所以"这个文件的第一段还在前缀里"等价于它进了 prompt。
    for _ds_fname, _ds_df, _ds_index in pending_datasets:
        if _ds_index < len(fitted):
            _record_dataset_evidence(config, _ds_fname, _ds_df)
        else:
            logger.info(
                "[PromptPack] leg=data dataset=%s recorded=false（装箱未送出，证据袋不记）", _ds_fname
            )
    if not fitted:
        return _empty_pack_text("data", len(parts), fitted)
    result = "\n".join(fitted)
    # The answer a caller sees is built from this string when the model is unavailable,
    # so it carries data only: an echoed 用户查询 and an instruction addressed to the
    # model both leaked into the reply.
    return f"数据分析结果:\n{result}"


# ==================== 真·自然语言数据查询（阶段 3 · P0） ====================

def _llm_pandas_code(df, query: str) -> str:
    """让 LLM 根据列结构生成一段只用 df/pd 的 pandas 表达式"""
    from app.agents.nodes import _make_model
    from app.agents.contracts import ModelTier
    from langchain_core.messages import HumanMessage
    cols = ", ".join(f"{c}({df[c].dtype})" for c in df.columns)
    prompt = (
        "你是 pandas 专家。已有 DataFrame 变量 df，列如下：\n" + cols + "\n\n"
        "用【一个 Python 表达式】回答用户问题，只能使用 df 和 pd，"
        "返回值即答案（数字/字符串/列表/Series/DataFrame 均可）。\n"
        "只输出代码本身，不要解释、不要 markdown、不要 ```。\n\n"
        "用户问题：" + query
    )
    resp = _make_model(ModelTier.CODE, prompt=prompt).invoke([HumanMessage(content=prompt)])
    code = str(resp.content).strip()
    if code.startswith("```"):
        code = code.strip("`")
        if code.lower().startswith("python"):
            code = code[6:]
    return code.strip()


def _query_data(query: str, config: RunnableConfig) -> str:
    from app.common.rbac import filter_dataframe_rows_with_scope
    from app.tools.excel import load_excel, safe_query
    context = _tool_context(config)
    if context is None:
        record_tool_status(
            bag_from_config(config), tool="query_data", status="rejected", error_code="authorization_required"
        )
        return _authorization_error()
    conf = (config or {}).get("configurable", {}) or {}
    role = context["role"]
    dept = context["department"]
    files, dataset_error = _authorized_dataset_files(config)
    if dataset_error is not None:
        # 与 _analyze_data 同形的第二处（app/agents/tools.py 原 :1069-1071）：两处都得自己
        # 把 DatasetsHiddenByScope 翻成人话，只改一处就是留下第二张假话给 query_data 这条腿。
        return _dataset_access_text(config, dataset_error)
    if not files:
        return _NO_BOUND_DATASET_TEXT

    attempted = 0
    denied_rows: list[str] = []
    denied_codes: list[str] = []
    unreadable = 0
    empty_files = 0
    for fname, file_path in files:
        try:
            df = load_excel(file_path)
            df, scope_info = filter_dataframe_rows_with_scope(df, role=role, department=dept)
            if df.empty:
                reason = _row_scope_reason(scope_info)
                if reason:
                    denied_codes.append(_row_scope_code(scope_info))
                    denied_rows.append(f"· {fname}: {reason}")
                elif int(scope_info.get("rows_in") or 0) <= 0:
                    empty_files += 1
                continue
        except Exception:
            unreadable += 1
            continue
        attempted += 1
        code = _llm_pandas_code(df, query)
        res = safe_query(df, code)
        if res.get("error") is None:
            result = res["result"]
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)
            # R112：查询结果是一整块，装箱装不下时只能裁这块的尾巴（带可见截断标记），
            # 连标记都装不下就换那一句指名"本题数据结果超出本机上下文"的话。
            # R122：裁出来那一截的正文不够门槛也不交——"📊 x.xlsx 查询结果:"加三个字不是答案。
            query_text = f"📊 {fname} 查询结果:\n{result}"
            fitted = _pack_into_prompt_room(
                config, leg="query", units=[query_text], keep_first_truncated=True
            )
            if not fitted:
                # R112 复验第 2 条：整块都没送出去 ⇒ 证据袋什么都不记（模型一条都没读到）。
                return _empty_pack_text("query", 1, fitted)
            # 同一读法：只有真进 prompt 的那一块，才算模型读过这个数据集。
            _record_dataset_evidence(config, fname, df)
            return fitted[0]
    # 三种终态各说各话（R62 判据①②）：查询确实没过 ≠ 无权看到行 ≠ 压根没有行可读。
    if attempted:
        return "查询失败：LLM 生成的代码在沙箱中多次执行未通过，请换个问法。"
    if denied_rows:
        # 终态的码：R62 的三句人话逐字不动，只是旁边多了一条机器读得懂的路。
        return _row_scope_denial_text(
            config,
            tool="query_data",
            head=_QUERY_DENIED_HEAD,
            reasons=denied_rows,
            codes=denied_codes,
            tail=_QUERY_DENIED_HINT,
        )
    # 读不出来的那些文件不是行级口径的账，本层不替它编码（说不清因由就不说）。
    if unreadable and not empty_files:
        return "查询未完成：这些数据文件载入失败，本轮没有取到任何数据行。"
    # 没有可见行（表本来就是空的、或因由不在本层能说话的那个维度上）：码在这条路上。
    return _row_scope_denial_text(
        config,
        tool="query_data",
        head="查询未完成：本次可用的数据文件里没有可分析的数据行。",
        reasons=[],  # 这条终态没有可归因的文件，那一句中性文案本身就是能说的全部
        codes=[_NO_VISIBLE_ROWS_CODE],
    )


# ==================== Chart Tool v2 ====================

def _generate_chart(
    chart_type: str,
    config: RunnableConfig,
    labels: list | None = None,
    values: list | None = None,
    datasets: dict | None = None,
    categories: list | None = None,
    tasks: list[dict] | None = None,
    root: str | None = None,
    branches: dict[str, list[str]] | None = None,
    title: str = "数据分析图表",
) -> str:
    from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
    from app.tools.visualize import gantt_chart, mindmap as _mindmap

    chart_funcs = {
        "bar": lambda: bar_chart(labels or [], values or [], title=title),
        "line": lambda: line_chart(labels or [], datasets or {"数据": values or []}, title=title),
        "pie": lambda: pie_chart(labels or [], values or [], title=title),
        "radar": lambda: radar_chart(categories or labels or [], datasets or {"数据": values or []}, title=title),
        "gantt": lambda: gantt_chart(tasks or [], title=title),
        "mindmap": lambda: _mindmap(root or title, branches or {}, title=title),
    }

    if chart_type not in chart_funcs:
        return f"不支持的图表类型: {chart_type}，可选: bar/line/pie/radar/gantt/mindmap"

    try:
        if _artifact_principal(config, ACTION_ANALYZE) is None:
            record_tool_status(
                bag_from_config(config), tool="generate_chart", status="rejected", error_code="authorization_required"
            )
            return _authorization_error()
        path = chart_funcs[chart_type]()
    except Exception as e:
        return f"图表生成失败: {e}"

    urls = _artifact_urls(path, "chart", config)
    if urls is None:
        _record_denial(
            config, tool="generate_chart", code="authorization_required", status="rejected"
        )
        return _authorization_error()
    url, _ = urls
    if path.lower().endswith(".html"):
        return f"图表已生成: [{title}]({url})"
    return f"图表已生成: ![{title}]({url})"



# ==================== Export Tool ====================

def _export_report(report_title: str, sections_json: str,
                    config: RunnableConfig, include_charts: str = "") -> str:
    from app.tools.export import generate_pdf_report

    try:
        if _artifact_principal(config, ACTION_EXPORT) is None:
            record_tool_status(
                bag_from_config(config), tool="export_report", status="rejected", error_code="authorization_required"
            )
            return _authorization_error()
        sections = json.loads(sections_json)
        path = generate_pdf_report(title=report_title, sections=sections)

        urls = _artifact_urls(path, "report", config)
        if urls is None:
            _record_denial(
                config, tool="export_report", code="authorization_required", status="rejected"
            )
            return _authorization_error()
        _, url = urls
        return f"报告已生成: [📋 下载报告]({url})"
    except Exception as e:
        return f"报告生成失败: {e}"


@tool
def analyze_data(query: str, config: RunnableConfig) -> str:
    """
    分析企业经营数据。用于所有数据相关问题：统计数字、计算指标、对比业绩、
    排名、增长率、利润、营收等。调用此工具会自动检测已上传的 Excel/CSV 文件并进行分析。
    如果用户提到具体数字指标，优先使用此工具而不是 search_docs。
    """
    with start_tool_call(config, tool_name="analyze_data", arguments={"query": query}):
        return _analyze_data(query, config)


@tool
def query_data(query: str, config: RunnableConfig) -> str:
    """
    用自然语言查询经营数据（阶段3 P0）。LLM 生成 pandas 代码 → 沙箱执行 → 报错自动纠错。
    适合 analyze_data 固定模板答不了的组合条件问题，如
    "利润率超过20%且营收环比增长的门店有哪些"。
    """
    with start_tool_call(config, tool_name="query_data", arguments={"query": query}):
        return _query_data(query, config)


@tool("generate_chart")
def generate_chart_v2(
    chart_type: str,
    config: RunnableConfig,
    labels: list | None = None,
    values: list | None = None,
    datasets: dict | None = None,
    categories: list | None = None,
    tasks: list[dict] | None = None,
    root: str | None = None,
    branches: dict[str, list[str]] | None = None,
    title: str = "数据分析图表",
) -> str:
    """生成柱状图、折线图、饼图、雷达图、甘特图或思维导图。"""
    with start_tool_call(
        config,
        tool_name="generate_chart",
        arguments={
            "chart_type": chart_type,
            "title": title,
            "label_count": len(labels or []),
            "value_count": len(values or []),
        },
    ) as span:
        result = _generate_chart(
            chart_type,
            config,
            labels=labels,
            values=values,
            datasets=datasets,
            categories=categories,
            tasks=tasks,
            root=root,
            branches=branches,
            title=title,
        )
        if not str(result).startswith("图表已生成"):
            span.finish("failed", error_code="validation_error")
        return result


generate_chart = generate_chart_v2


@tool
def export_report(report_title: str, sections_json: str,
                  config: RunnableConfig, include_charts: str = "") -> str:
    """
    导出分析报告为 PDF 文件。
    sections_json: JSON 数组，每项 {"type":"heading"|"text","content":"..."}
    include_charts: 图表路径列表（可选）
    """
    with start_tool_call(
        config,
        tool_name="export_report",
        arguments={"report_title": report_title, "sections_json_length": len(sections_json or "")},
    ) as span:
        result = _export_report(report_title, sections_json, config, include_charts)
        if "报告已生成" not in str(result):
            span.finish("failed", error_code="internal_error")
        return result


# ==================== 工具列表 ====================

ALL_TOOLS = [search_docs, analyze_data, query_data, generate_chart, export_report]
