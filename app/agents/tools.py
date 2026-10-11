"""
LangChain Tools — 封装企业智脑全部能力，供 ReAct Agent 自主调用
"""
import os
import json
import re
from collections import OrderedDict
from typing import Any, NamedTuple
import inspect
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.common.logger import logger
from app.common.permissions import ACTION_ANALYZE, ACTION_EXPORT
from app.agents.evidence import (
    _enum_error_codes,
    bag_from_config,
    record_artifact,
    record_chart_series,
    record_dataset,
    record_document_hits,
    record_tool_status,
)
from app.trace.spans import span_identity, start_tool_call


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


#: R294 —— 载荷快照不是权威身份。图内这一族只认两种投影：在场请求直接下发的 `Principal`
#: 对象，以及后台 worker 在**消费时刻**从用户库现取、逐维核过漂移之后交出的那一份 dict。
#: 后者靠一枚随行签名自证。签名长在 configurable 上而不是 Principal 里：两条路径的
#: Principal 字段集必须逐字相等（判据②），把出处塞成字段，相等就没有了。
#: 取值必须与 deploy/queue_worker.py 的同名常量逐字相等，由
#: tests/test_r294_principal_freeze.py 钉住（写法照 queue_worker 的 REPORT_LANE）。
PRINCIPAL_PROVENANCE_KEY = "principal_provenance"
CONSUMPTION_PRINCIPAL_PROVENANCE = "consumption-time"


def _tool_principal(config):
    """Resolve the canonical Principal carried by the Agent runtime.

    R294: a dict here is a queue payload's projection, and a queue payload outlives an
    identity change -- the department it froze is not the department in force now. Only
    the worker's consumption-time re-resolution may hand one over, and it signs the
    hand-off. Anything else that tries to make a frozen dict speak as the subject is
    refused, because the only honest directions left are narrowing and invalidation.
    """
    conf = (config or {}).get("configurable", {}) or {}
    try:
        from app.common.identity import Principal

        provided = conf.get("principal")
        if isinstance(provided, Principal):
            principal = provided
        elif isinstance(provided, dict):
            if str(conf.get(PRINCIPAL_PROVENANCE_KEY) or "") != CONSUMPTION_PRINCIPAL_PROVENANCE:
                raise PermissionError(
                    "authorization_required: agent tool identity is not consumption-time resolved"
                )
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
# 「这份资源对你没有授权」这个事实本身，不含更细的判断。密级这一维今天不是悬案：
# 密级口径已于 2026-09-28 裁定＝甲（出处 docs/handoff/2026-09-17-human-gates.md 最后一节
# 「H13 结案 ＋ A1/A3 裁定」；口径已写进契约 docs/api/contract-v1.md 的「## R467」节），
# 而这一维的拒绝由 authorization_decision 现成的两枚在册裸码承担——越档回
# clearance_insufficient、密级元数据缺失回 resource_scope_missing，与检索侧
# app/rag/filters.py::DocumentRetrievalScope.refusal_code 同一套词。翻译层不为它另开一码，
# 也不替它新增枚举成员。
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


def _tool_turn(config) -> tuple:
    """(会话号, 请求号) for the turn that is running this tool, or (None, None).

    Both legs already exist on the request path: ``thread_id`` is what the orchestrator names
    the conversation (``app/agents/orchestrator.py`` puts it in ``configurable``), and
    ``span_identity`` is the existing resolver for the request. This function reads them, it
    does not re-declare them; a background or direct call that carries neither produces a row
    that records nothing, which is the honest answer and not a placeholder to fill in.
    """
    conf = (config or {}).get("configurable", {}) or {}
    session = str(conf.get("thread_id") or "").strip()
    request = str(span_identity(config).get("request_id") or "").strip()
    return (session or None, request or None)


def _register_artifact(path: str, artifact_type: str, config):
    """Register a generated file and record it as evidence for this execution."""
    principal = _artifact_principal(config)
    if principal is None:
        return None
    from app.storage import artifacts as artifact_storage

    turn_session, turn_request = _tool_turn(config)
    artifact = artifact_storage.register_artifact(
        path,
        artifact_type=artifact_type,
        principal=principal,
        session_id=turn_session,
        request_id=turn_request,
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


def _round_chart_paths(config, principal) -> list[str]:
    """本轮真登记过、现在还打得开的图表件路径（newest first）。

    为什么不去问证据袋：袋是按腿开的（``app/agents/orchestrator.py`` 每一枚 worker leg 各开一只，
    批准腿再开一只），导出腿那只袋里永远没有图腿登记的那枚件——按袋查图必然查不到。
    所以装箱走产物台账的生成血缘：会话号去掉 ``:worker`` 那一截后缀就是本轮这一场会话，
    再按属主收一道（同一场会话也可能换人批准），只读物证、不猜。
    """
    session, _request = _tool_turn(config)
    if not session:
        return []
    base = session.split(":", 1)[0]
    owner = str(getattr(principal, "user_id", "") or "")
    from app.storage import artifacts as artifact_storage

    paths: list[str] = []
    for record in artifact_storage.artifact_registry.list_active(artifact_type="chart"):
        lineage = str(getattr(record, "session_id", "") or "")
        if lineage.split(":", 1)[0] != base:
            continue
        if owner and str(getattr(record, "owner_id", "") or "") != owner:
            continue
        stored = str(getattr(record, "storage_path", "") or "")
        if stored:
            paths.append(stored)
    return paths


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


# ==================== R192 · 问法里的「前 N」：中文数词与阿拉伯数字同解 ====================
# 病灶：员工写「排名前三」，屏上标题写「排名前10」——标题里那个数就是 top_n 本身，而 top_n
# 只在 `re.search(r"前\s*(\d+)")` 命中时才动，\d 不吃中文数字，于是问三答十。
# 为什么这一族归一全仓只此一处（三条都是改前实取，不是推测）：
#   1) 扫遍 app/**，"前 + 数字"的取数正则只有 _answer_query 这一枚命中，没有第二个消费者；
#   2) 仓里没有既成的中文数词→整数通路可复用：app/documents/index_policy.py 里的
#      [一二三四五六七八九十百] 是"这一行像不像标题"的字符类，只做形状匹配，不产数值；
#   3) app/common/model_budget.py::_env_int 与 app/rag/indexing.py::_scope_int 化的是环境量
#      和台账字段，输入永远是阿拉伯数字串，喂中文数词只会落回默认值——不是同一件事。
# 所以本单养的是唯一一个消费者：正则一枚、取值一口。第二枚消费者出现时调 _ranking_count()，
# 不许再抄一份；也不许顺手长成一套通用数词文法（判据明令不许新增自由解析器）。

#: 中文个位数 → 值。"两"是手写里"二"的常见替代，同解。
_CN_DIGIT_VALUES = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

#: 「前」后面那一串，外加三种"这根本不是排名条数"的后随形状，命中就整条不认：
#:   - 后面还是数字：「前30年」被贪婪匹配截成"前 3"是一枚新假话；
#:   - 数量级位（零/百/千/万）：「前一百名」认成"前 1"同样是假话，宁可退回默认条数——那与改前逐字相同；
#:   - 时间单位（天/日/周/月/年…）：「提前一天」「前五个月」问的是时间段，不是要前几名。
_RANKING_COUNT_RE = re.compile(
    r"前\s*(\d+|[一二两三四五六七八九十]{1,3})"
    r"(?!\s*(?:\d|[零百千万]|个?(?:工作日|工作天|天|日|号|星期|周|月|年|小时|分钟)))"
)

#: 问法里点不出数时的条数：沿用改前那一枚，本单不动它。
_DEFAULT_RANKING_COUNT = 10

#: 病灶二那张脸（用户可见那一层）。它与准入闸那三张脸不同族：那三张说的是文件读不读得到，
#: 这一张说的是文件读到了、也有行，只是这张表能拿来比大小的列一枚都没有。
#: 措辞三条红线：不说"没结论"（那是把算不出来说成没算过）、不说"没数据"（数据就在下一段）、
#: 不提权限与部门（因由不归这里猜）。
_NO_SORTABLE_NUMERIC_COLUMN_TEXT = (
    "这份文件没有可排序的数值列：它已有的列全是文本，排名需要一个能比大小的数值列。"
)


def _chinese_ranking_number(token: str) -> int | None:
    """1..99 的中文数词 → 整数；认不出交 None，不猜。

    只覆盖「三」「十」「十二」「二十」「二十三」这一档形状。再往上（一百、一千）是数量级组合，
    要吃得下就得写一套完整的中文数词文法，而今天没有任何问法需要它：那一档一律 None，
    由调用方落回默认条数，读数与改前逐字相同。
    """
    if "十" in token:
        head, _, tail = token.partition("十")
        tens = 1 if not head else _CN_DIGIT_VALUES.get(head, 0)
        if not tens:
            return None
        if not tail:
            return tens * 10
        units = _CN_DIGIT_VALUES.get(tail, 0) if len(tail) == 1 else 0
        return tens * 10 + units if units else None
    return _CN_DIGIT_VALUES.get(token)


def _ranking_count(query: str) -> int | None:
    """问法里「前 N」的那个 N：阿拉伯数字与中文数词同解；点不出来交 None。"""
    match = _RANKING_COUNT_RE.search(query or "")
    if match is None:
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    return _chinese_ranking_number(token)


# ==================== R703 · 分组维度照这张表的真列名点，不照硬写字面点 ====================
#
# 病形现取（跟进单口径：客户带着报销明细表.csv 问「按月份统计报销金额，并画一张柱状图」，
# 屏上回的是「文档中未包含实际报销数据」）：Data 腿的返回串里只有一枚 📈 数值统计 小节，
# 分组汇总那一节一个字都没出。原因在触发条件与选列两处都写死了字面：
#   触发那一枚字面表是 ["对比","比较","分组","按区域","按类型"]，后两枚是别家夹具的列名手抄，
#   真表真问法一枚都不命中；选列那一支做的是 `tc in query` 单向包含，列名「发生月份」
#   不是问法「按月份…」的子串，于是永远配不上。
# 判据口径：命中与否由**这张表自己的列名**说了算，问法只负责指出"按哪个维度"。
# 老那一支（字面命中时的选列与任意挑选）整段保留，读数字节不变；新增的只是
# "问法点了维度、且维度在这张表里对得上真列名"这一条通路。

#: 问法里点维度时常用的那几枚前导字：「按月份」「各区域」「逐月」「分部门」「每季」「照类型」。
_DIMENSION_MARKERS = "按各逐分照每"
#: 前导字后面最多取几个字去找列名，再从最长逐字回退：「按月份统计报销」里只有「月份」是列名片段。
_DIMENSION_WINDOW = 6
#: 分组汇总最多列几组。这一段直接进 prompt，装箱预算卡在那儿；超线明说还剩几组，不静默截断。
_MAX_GROUP_ROWS = 12

_DIMENSION_CANDIDATE_RE = re.compile(
    "[" + _DIMENSION_MARKERS + r"]\s*([0-9A-Za-z_一-鿿]{1," + str(_DIMENSION_WINDOW) + r"})"
)


def _named_dimension_column(query: str, txt_cols: list[str]) -> str | None:
    """问法点名的维度 → 这张表里的真列名；点不出或表里没有交 None，不猜。

    匹配是**双向**的，两个方向各有各的真实问法：「月份」要能对上「发生月份」（候选是列名的一段），
    「发生月份」要能对上「发生月份」（列名是候选的一段）。只写单向那一枚，命中的就仍然只是
    "客户把列名一字不差敲出来"的那种问法。

    单字候选只认等值：「分析金额」里「析」是"分析"的尾巴，若允许包含匹配，
    任何列名带「析」的表都会被判成"客户要按那一列分组"。
    """
    for match in _DIMENSION_CANDIDATE_RE.finditer(query or ""):
        token = match.group(1)
        for size in range(len(token), 0, -1):
            candidate = token[:size]
            for column in txt_cols:
                if candidate == column:
                    return column
                if len(candidate) >= 2 and (candidate in column or column in candidate):
                    return column
    return None


# ==================== B18 · 问句点名某一行的时候，先去表里把那一行找出来 ====================
#
# 病形现读（10-08 09:5x，跟进单 B18）：夹具表 41 行，最后一行是 项目=走查标记425273 / 数值=1325273，
# 屏上问「它里面「走查标记425273」这一行的数值是多少」答的是「数值为 3，对应数据行：项目=月度差旅425273-01」。
# 两处叠在一起才成这一格：
#   ① `_answer_query` 那四段（排名／统计／分组／兜底预览）里没有一段是"照问句点名的值取行"，
#      这一发只落到兜底预览那一段；
#   ② 预览每一行只印一枚 `label_col`，而这张表挑中的是「部门」——41 行全是「市场部」，
#      印出来的十行彼此一模一样，被点名的那一行在 prompt 里根本没有身份。
# 于是模型回头去读同一条消息里那份 `数据样本(前15行)`，第一行就是 3。
# 判据（交班单 §1.1）：同一句被点名的话，两条道答出来的数必须一致，且等于表里那一行。
# 本层只负责把那一行连同它所有的列摆到模型眼前，不叫模型自己去认——认错了就是屏上那个假数。

#: 问句里点名一行时可能带的引号（成对，取中间那一段）。
_QUOTED_NAME_RE = re.compile(r"[「『“《〈]([^」』”》〉]{1,80})[」』”》〉]")
#: 没有引号时按"名字段"切：连续的汉字／字母／数字／点／横线／下划线，标点与空白即断。
_NAME_TOKEN_RE = re.compile(r"[0-9A-Za-z_一-鿿.\-]{2,80}")
#: 一次最多拿几枚候选去比。问句本身只有几十字，这枚上限只挡畸形输入，不改正常读数。
_MAX_NAME_TOKENS = 40
#: 兜底那一路（在某一列的真值集合里找"整段出现在引号里"的那一枚）每列最多看多少枚真值。
_MAX_NAME_SCAN_VALUES = 4000
#: 「点名一行」的行数上限：一次挑出六行八行的那不是点名，是按某个维度切了一刀——
#: 那种问法归分组汇总那一段管，本段不插手，免得把客户没要的东西塞进已经很挤的 prompt。
_MAX_NAMED_ROWS = 5
#: 一句问话最多点几枚行名（「对比 A 和 B 两行」这种形状）。
_MAX_NAMED_HITS = 3
#: 点名行每一行最多印几列：这一段直接进 prompt，与分组那一节同一规矩，超线明说、不静默。
_MAX_NAMED_COLUMNS = 10


def _name_tokens(query: str) -> tuple[list[str], list[str]]:
    """问句里可能是在点一行名字的两族片段：(引号段, 全部候选)。长的排前面。

    分两族是因为「市场部」这种既可能是在点名一行、也可能只是顺嘴提了一个部门：
    前者可以放宽到"真值整段出现在引号里"，后者只认整值相等，不然每一张按部门切的表都会多出一段。
    """
    text = query or ""
    quoted = [item.strip() for item in _QUOTED_NAME_RE.findall(text)]
    tokens = quoted + [item.strip() for item in _NAME_TOKEN_RE.findall(text)]
    unique: list[str] = []
    for token in tokens:
        if len(token) >= 2 and token not in unique:
            unique.append(token)
    unique.sort(key=len, reverse=True)
    quoted_unique = [token for token in unique if token in quoted]
    return quoted_unique, unique[:_MAX_NAME_TOKENS]


def _named_row_hits(df, query: str, txt_cols: list[str]) -> list[tuple[str, str, object]]:
    """问句点到的行名 → [(列名, 那一列里的真值, 挑出来的子帧)]；一枚都不点交空表，不猜。

    两条通路，先便宜后兜底：
      ① 拿候选名去和文本列的**整值**比（pandas 向量化，一个字符都不猜）；
      ② ① 一枚都不中时，只在**引号里**找"这一列的某枚真值整段出现在引号中"——
        客户打的是「走查标记425273这一行」而表里存的是「走查标记425273」时走这里。
    只收"至少挑出一行、又没挑走整张表、且行数不超过 _MAX_NAMED_ROWS"的命中：
    整张表都姓「市场部」时那不是点名一行，一次挑出二十行也不是。
    """
    quoted, tokens = _name_tokens(query)
    total = len(df)
    if not total or not tokens or not txt_cols:
        return []
    hits: list[tuple[int, int, str, str, object]] = []

    def keep(column: str, value: str) -> None:
        mask = df[column].astype(str).eq(value)
        rows = int(mask.sum())
        if 0 < rows <= _MAX_NAMED_ROWS and rows < total:
            hits.append((rows, len(value), column, value, df[mask]))

    for column in txt_cols:
        for token in tokens:
            keep(column, token)
    if not hits:
        for column in txt_cols:
            uniques = df[column].dropna().unique()
            if len(uniques) > _MAX_NAME_SCAN_VALUES:
                continue
            for value in uniques:
                text = str(value)
                if len(text) < 2:
                    continue
                if any(text in item for item in quoted):
                    keep(column, text)
    hits.sort(key=lambda item: (item[0], -item[1]))
    return [(item[2], item[3], item[4]) for item in hits[:_MAX_NAMED_HITS]]


def _record_series(series_out: list | None, *, kind: str, dimension: str, column: str, labels, values) -> None:
    """把算好的一串数交给缓冲；只在调用方要的时候记，正文那几行一个字都不动。"""
    if series_out is None:
        return
    pairs: list[tuple[str, float]] = []
    for label, value in zip([str(item).strip() for item in (labels or [])], list(values or [])):
        if not label:
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        if number != number:
            return
        pairs.append((label, number))
    if pairs:
        series_out.append(
            {
                "kind": kind,
                "dimension": str(dimension or ""),
                "column": str(column or ""),
                "labels": [item[0] for item in pairs],
                "values": [item[1] for item in pairs],
            }
        )


def _answer_query(
    df, query: str, num_cols: list[str], txt_cols: list[str], series_out: list | None = None
) -> list[str]:
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

    def plain_label(row) -> str:
        """图表标签取裸值：``label_value`` 带「列名=」前缀，那是给人读的一句，不是横轴刻度。"""
        if not label_col:
            return ""
        return str(row[label_col])

    # 问句点名一行 → 先把那一行连同它所有的列摆出来（B18）。这一段排在其余四段之前，
    # 并且顺手替自己把兜底预览顶掉：预览印的是"数值最大的那十行"，被点名的那一行多半不在里面，
    # 而模型只会去读它看得见的那几行。
    for hit_column, hit_value, hit_frame in _named_row_hits(df, query, txt_cols):
        hit_rows = len(hit_frame)
        lines = [f"📍 问句点名的行（{hit_column}={hit_value}，命中 {hit_rows} 行）:"]
        columns_use = list(df.columns)[:_MAX_NAMED_COLUMNS]
        for _, row in hit_frame.head(_MAX_NAMED_ROWS).iterrows():
            cells = ", ".join(f"{column}={row[column]}" for column in columns_use)
            lines.append(f"  {cells}")
        if hit_rows > _MAX_NAMED_ROWS:
            lines.append(f"  …共 {hit_rows} 行，本条只列前 {_MAX_NAMED_ROWS} 行")
        results.append("\n".join(lines))

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
        if not num_cols:
            # R192 病灶二第 2 层（用户可见那张脸）：下面那一枚 `num_cols[0]` 在零数值列时抛
            # IndexError，改前被调用方的 `except Exception: pass` 整个吞掉，于是员工只看见
            # "这份文件没结论"。因由在这里就说得出，就在这里说，而不是把话留给一次注定被
            # 吞掉的异常——那是把"说得清"主动降级成"说不清"。
            results.append(_NO_SORTABLE_NUMERIC_COLUMN_TEXT)
        else:
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
            # 条数：中文数词与阿拉伯数字同解（前三 / 前五 / 前十名 / 前 10 四形共用一个取值口）。
            # 点不出数＝改前的零匹配，落回默认条数，读数与改前逐字相同。标题与 head() 取的是
            # 同一枚 top_n，所以"问三答十"那类各说各话不可能再出现；表本身不足 N 行时列满即止，
            # 这一格语义本单不动（改前「排名前10」在三行表上印的也是三行，R189 钉的就是那个形状）。
            count = _ranking_count(query)
            top_n = _DEFAULT_RANKING_COUNT if count is None else count
            sorted_df = df.sort_values(sort_col, ascending=False).head(top_n)
            lines = [f"📊 按 {sort_col} 排名前{top_n}:"]
            for _, r in sorted_df.iterrows():
                name = label_value(r)
                vals = ", ".join(f"{c}={r[c]}" for c in num_cols[:3])
                lines.append(f"  {name}: {vals}")
            for _col in num_cols[:3]:
                _record_series(
                    series_out,
                    kind="ranking",
                    dimension=label_col,
                    column=_col,
                    labels=[plain_label(r) for _, r in sorted_df.iterrows()],
                    values=sorted_df[_col].tolist(),
                )
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
    # R703：触发条件补一条通路 —— 问法点了维度、且这个维度在这张表的真列名里对得上。
    # 字面命中时走的仍是老那两挑选（先 `tc in query` 单向包含，再 2..20 唯一值任意挑），
    # 读数一字不变；新增的只处理"字面一枚都不命中、但客户明明说了按哪一列"的那一支。
    literal_group = any(kw in q_lower for kw in ["对比", "比较", "分组", "按区域", "按类型"])
    group_col = None
    if literal_group:
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
    if not group_col:
        group_col = _named_dimension_column(query, txt_cols)
    if group_col and num_cols:
        agg = df.groupby(group_col)[num_cols[:3]].sum()
        lines = [f"📋 按 {group_col} 分组汇总:"]
        total_groups = len(agg)
        for idx, row in agg.head(_MAX_GROUP_ROWS).iterrows():
            vals = ", ".join(f"{c}={v:.1f}" for c, v in row.items())
            lines.append(f"  {idx}: {vals}")
        if total_groups > _MAX_GROUP_ROWS:
            # 截断要看得见：这一段直接进 prompt，静默少列几组＝让模型以为这就是全部。
            lines.append(
                f"  …共 {total_groups} 组，本条只列前 {_MAX_GROUP_ROWS} 组"
                f"（还有 {total_groups - _MAX_GROUP_ROWS} 组未列出）"
            )
        shown = agg.head(_MAX_GROUP_ROWS)
        for _col in num_cols[:3]:
            _record_series(
                series_out,
                kind="group",
                dimension=group_col,
                column=_col,
                labels=[str(item) for item in shown.index],
                values=shown[_col].tolist(),
            )
        results.append("\n".join(lines))

    # 兜底：返回基本统计
    if not results and num_cols:
        sorted_df = df.sort_values(num_cols[0], ascending=False).head(10)
        lines = [f"📊 数据预览 (按{num_cols[0]}降序):"]
        for _, r in sorted_df.iterrows():
            name = label_value(r)
            vals = ", ".join(f"{c}={r[c]}" for c in num_cols[:3])
            lines.append(f"  {name}: {vals}")
        for _col in num_cols[:3]:
            _record_series(
                series_out,
                kind="preview",
                dimension=label_col,
                column=_col,
                labels=[plain_label(r) for _, r in sorted_df.iterrows()],
                values=sorted_df[_col].tolist(),
            )
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
# 🔴 R463 把「可用量由哪一处算」这件事收了口：``window - 该档 declared_max_tokens`` 全仓只
# 写在 ``app/agents/contracts.py::prompt_room`` 那一处，装箱读的 ``ModelBudget.pack_room_tokens``
# 与发请求前那道守卫读的 ``ModelBudget.context_window_code`` 都是它的下游。以前这两格是各自
# 抄了一遍减法（``input_budget_tokens`` 与 ``context_window_code`` 里的 ``prompt+cap<=window``），
# 装箱塞到边界＝守卫的边界，纯靠两笔算式碰巧同值；跟进单 §133 五 那发 ``prompt_tokens=14928``
# 被自己下游判拒成 ``required_n_ctx=16464``，撞的就是这条缝。
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

#: 整批一条都装不下时，留给"裁过头的那一条"的截断标记。宁可让模型看到某一条真料的前半段，
#: 也不要真机那种 evidence_n=0 的整题空手；标记本身也计进 room，不留暗账。
#: R445 以前这一条写的是"最高分那条"：救援只裁 ``units[0]``，第一名太长、第三名很短时
#: 第三名压根没被试过——那是本单修的硬顶。名次顺序仍然一个字没动，只是往下扫到装满为止。
PACK_TRUNCATION_MARK = "…（上下文装箱截断）"
#: R122 给上面那句"宁可看到前半段"补了一条下限：只有**裁出来的正文够读**才交（见
#: ``PACK_MIN_STUB_BODY_TOKENS``）。半条命中是好事，只剩几个字的正文不是——那是一条看着
#: 像证据的空壳，模型会照着它编答案。够不上门槛就改交「本轮检索预算已用尽」那句人话。

#: ``[PromptPack]`` 台账新字段 ``stub=`` 的三枚取值（R122 判据 ③）。🔴 台账既有字段一枚
#: 不改名、不改相对顺序（run3/run4 的日志口径要连续），这一枚只新增，插在 ``truncated=`` 之后。
PACK_STUB_NONE = "none"        # 这一发没有"桩"这件事：整批装下了，或交出去的是整条，或连标记都裁不出来
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


def pack_profile_tier(profile: str | None = None):
    """把装箱档位名翻译成"这一串最终由哪一档买单"，缺省＝在册的 ``analysis``。

    🔴 R463 判据 ①：room 扣的必须是**买单那一档自己声明的** ``declared_max_tokens``，所以
    装箱侧先得说清自己装出来的串最终由哪一发请求送出。以前这里没有可说的档位——调用点一律
    走 ``context_pack_room()`` 的缺省，等于替全仓认下了 ``CONTEXT_PACK_TIER`` 那一枚写死的
    ``"analysis"``。

    ``report`` 不是 ``ModelTier`` 的成员，它是产品道（``app/agents/nodes.py`` 的
    ``LANE_REPORT``），所以走 ``LANE_TIERS`` 那座既有的桥：今天桥另一头是
    ``ModelTier.ANALYSIS``（``app/api/v1/observability.py`` 的 ``bridge_note`` 把这件事写在册
    钉里，"analysis and report share ModelTier.ANALYSIS"），桥上改了这里跟着改，本处不抄第二份。
    """
    from app.agents.contracts import ModelTier
    from app.rag.retrieval_pipeline import CONTEXT_PACK_TIER

    name = str(profile or CONTEXT_PACK_TIER)
    try:
        return ModelTier(name)
    except ValueError:
        pass
    from app.agents.nodes import LANE_TIERS

    if name in LANE_TIERS:
        return LANE_TIERS[name]
    raise ValueError(
        f"unknown pack profile {profile!r}: not a ModelTier and not a lane in LANE_TIERS "
        f"({', '.join(sorted(tier.value for tier in ModelTier))} / {', '.join(sorted(LANE_TIERS))})"
    )


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

    ``source_indexes``：``self[i]`` 来自原 ``units`` 的第几名。前缀填装时它就是 ``0..n-1``
    （与旧读法逐字等价），R445 的救援交的是名次更后面那一条，没有这一枚，调用方会把
    "第 4 名送出去了"读成"第 1 名送出去了"，证据袋当场认错人。它是**纯 Python 属性**：
    ``[PromptPack]`` 台账的字段一枚不新增、不改名、不改顺序（``tests/test_r117_ledger_turn_scoped.py``
    与 ``tests/test_r122_stub_honesty.py`` 钉着精确字段序）。
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
        source_indexes: "list[int] | None" = None,
    ) -> None:
        super().__init__(units)
        #: 送出去的每一段对应回原 units 的名次；缺省＝前缀（按下标一一对应）。
        self.source_indexes: "list[int]" = (
            list(range(len(units))) if source_indexes is None else list(source_indexes)
        )
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
    """把真送出去的那几段翻译回 hit：按 ``source_indexes`` 认名次，装箱只裁尾巴。

    前缀填装时 ``fitted`` 恒为 ``units`` 的前缀，名次就是下标（逐字沿用旧读法）；R445 的救援
    可能交的是名次更后面那一条，所以这里必须按 ``source_indexes`` 取，不许再拿 ``enumerate``
    的下标当名次。

    被 ``_fit_unit_to_room`` 裁过尾的那一条按**实际送出的正文**交给证据袋，免得 ``excerpt`` 与
    ``content_sha256`` 说"模型读过整段"而它其实只读到裁过的那一截。认不出这种前缀关系就退回
    原条并留一行警告：宁可正文少诚实一点，也不许少记一条模型真读过的来源。
    """
    kept: list = []
    for unit, index in zip(fitted, getattr(fitted, "source_indexes", range(len(fitted)))):
        original = units[index]
        if unit == original:
            kept.append(hits[index])
            continue
        sent = unit[: -len(PACK_TRUNCATION_MARK)] if unit.endswith(PACK_TRUNCATION_MARK) else unit
        if not original.startswith(sent):
            logger.warning(
                "[PromptPack] 装箱前缀不变量被打破（名次 %s 那一条不是裁尾片段）：证据袋按原条记",
                index + 1,
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


#: 建图那一刻由 app/agents/orchestrator.py 登记进子图 config 的两格。缺省（没登记）＝今天
#: 的算术一字不变，钉装箱那几枚用例（r112/r122/r445/r451/r463）因此不必跟着房账重测；生产路径上
#: 四条 worker 腿都带，图是那一边建的。
#:   shell_extra＝这一腿挂进请求体的工具字段，比 run5 量 456 那枚壳时多出来的一截；
#:   calibration＝表格料在真机的词价对估算的倍率，房按它折过才开始装。
#: 10-08 真机（qwen3.5:9b / num_ctx=8192 / 兼容腿）逐档量过料价：估算 1032 / 3012 / 4538 /
#: 5322 枚的表格 JSON，真机 prompt 分别是 1836 / 4716 / 6936 / 8076 枚，拟合 real ≈
#: 1.45 × est + 338。再往上（6023 枚那一档）服务端不答 413，它把最前面几条挤出去重渲染模板，
#: 被挤掉的正是本轮问题，模板当场 raise → HTTP 500「No user query found in messages」→
#: 兜底把 12k 字原始材料当答案回屏，屏上零张图。取 1.6 给第三轮往返留余量。
PROMPT_SHELL_EXTRA_TOKENS_KEY = "prompt_shell_extra_tokens"
PROMPT_MATERIAL_CALIBRATION_KEY = "prompt_material_calibration"
PACK_MATERIAL_CALIBRATION = 1.6


def _configurable(config) -> dict:
    return ((config or {}).get("configurable") or {})


def _leg_shell_extra_tokens(config) -> int:
    try:
        return max(0, int(_configurable(config).get(PROMPT_SHELL_EXTRA_TOKENS_KEY) or 0))
    except (TypeError, ValueError):
        return 0


def _leg_material_calibration(config) -> float:
    try:
        factor = float(_configurable(config).get(PROMPT_MATERIAL_CALIBRATION_KEY) or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return factor if factor > 1.0 else 1.0


def _pack_into_prompt_room(
    config, *, leg: str, units, keep_first_truncated: bool = False, profile: str | None = None
) -> list:
    """按名次把 ``units`` 装进本轮剩余 room，打一行的账，返回装进去的那几段。

    ``units`` 必须已按优先级从高到低排好（检索腿回来的顺序就是 RRF/重排分数降序，数据腿
    按文件与结论的既有顺序）：装箱只从尾部裁，不在这里重新发明排序。

    ``keep_first_truncated``（R122 加了门槛，R445 改成按名次扫）：整批一条都装不下时开启救援，
    按 ``units`` 的**原名次**从头扫到装满为止——名次高优先于内容短，交不出去的跳过而不是重排
    （排序归检索腿，这里不发明第二套）。名字保留 R112 的叫法，但它今天保的**不是** ``units[0]``
    那一条：改前只裁第一名，第一名太长、后面的短料够房时照样 ``fitted=0``，run9 真机 135 枚空手
    里有 13 枚的 ``room_left`` 已经够它那一条腿最便宜的整条（取证＝``scripts/r445_pack_forensics.py``
    的 RULER／VERDICT 两格）。

    门槛只管桩、不管整条：装得下的完整料本来就由 ``pack_prefix_by_rank`` 无门槛交付，救援沿用
    同一读法，不给整条另立一把尺（``PACK_MIN_STUB_BODY_TOKENS`` 拦的是空壳桩，不是短料）。桩照旧
    裁不出够读的正文就不交。每一候选都试过仍一件交不出去，那一发才是空手，``stub=refused``
    （裁得出桩但不够读）或 ``stub=none``（连标记都装不下）入账，由调用方说对应那一句人话。

    前缀填装非空那一支的行为逐字不变（名次就是下标）；救援那一支 ``dropped`` 是「除送出去的
    那些名次以外的全部」，所以 ``fitted + dropped == candidates`` 这条账不因为打洞而失真。打洞
    必须带名次账（``source_indexes``），否则证据袋会把第 4 名读成第 1 名。

    ``profile``（R463）：这一串最终由哪一档买单，缺省 ``analysis``（四条 worker 腿在装配期就
    按它出牌）。它只决定**扣哪一档自己声明的** ``declared_max_tokens``，不改名次、不改门槛、
    不改台账字段。room 不再由本处或 ``retrieval_pipeline`` 各算一遍，而是问 ``ModelBudget
    .pack_room_tokens``——发请求前那道守卫判拒用的正是同一枚数（``app/agents/contracts.py``
    的 ``prompt_room``），所以装箱装到边界就是守卫的边界：再大一枚 token 当场少塞一片，而不是
    塞完之后由下游那道守卫把整发拒掉（跟进单 §133 五：装箱交出的 14 928 枚题面，加上该档
    自己声明的输出顶，恰好是判拒读数 ``required_n_ctx=16464 > MODEL_CONTEXT_TOKENS=16384``）。
    """
    from app.common.model_budget import model_tier_budget
    from app.rag.retrieval_pipeline import (
        CONTEXT_HISTORY_RESERVE_TOKENS,
        CONTEXT_PACK_TIER,
        CONTEXT_SHELL_RESERVE_TOKENS,
        PROMPT_PACK_MARKER,
        pack_prefix_by_rank,
        text_pack_tokens,
    )

    units = list(units)
    profile = str(profile or CONTEXT_PACK_TIER)
    tier = pack_profile_tier(profile)
    #: 装箱看不见的那半截 prompt（system 段＋题面＋壳＋两轮历史），两枚实测预留就是它的现值。
    #: 它同时进 room 与台账的 ``prompt_estimate_tokens``：一处算，两处读，不许再各抄一遍。
    shell_extra = _leg_shell_extra_tokens(config)
    calibration = _leg_material_calibration(config)
    prefix_reserve = (
        CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS + shell_extra
    )
    room_total = model_tier_budget(tier).pack_room_tokens(prefix_reserve)
    key = _pack_ledger_key(config)
    with _pack_lock:
        used = _pack_ledger.get(key, 0) if key else 0
        room = max(0, room_total - used)
        if calibration > 1.0:
            #: 房先按实测料价折一刀再装：估不准的那一截（表格 JSON 的词价）要是留给服务端自己
            #: 裁，代价是整轮 500，不是少塞一片料。
            room = int(room / calibration)
        fitted, dropped, packed_tokens = pack_prefix_by_rank(units, room)
        truncated = 0
        stub = PACK_STUB_NONE
        #: 名次账：前缀填装就是 0..n-1，救援那一支换成真正送出去的那几名。
        source_indexes = list(range(len(fitted)))
        if not fitted and units and keep_first_truncated:
            #: 救援那一支：按原名次扫到装满为止。left 是这一支自己的房账，走完就是这一发交出的
            #: 总额（packed_tokens 进到这里的初值是 0——前缀填装空手时它必然是 0）。
            rescued: list = []
            source_indexes = []
            left = room
            trimmable = False
            for index, unit in enumerate(units):
                text = str(unit)
                if not text.strip():
                    #: 全空白的一条交出去就是一条读不出结论的空壳，与 R122 拦桩同一件事，不算可用料。
                    continue
                cost = text_pack_tokens(text)
                if cost <= left:
                    rescued.append(unit)
                    source_indexes.append(index)
                    packed_tokens += cost
                    left -= cost
                    continue
                head = _fit_unit_to_room(text, left)
                if not head:
                    continue
                if _stub_body_tokens(head, text) >= PACK_MIN_STUB_BODY_TOKENS:
                    cost = text_pack_tokens(head)
                    rescued.append(head)
                    source_indexes.append(index)
                    truncated += 1
                    packed_tokens += cost
                    left -= cost
                else:
                    trimmable = True
            if rescued:
                fitted = rescued
                #: 打洞了，所以按名次取补集：dropped 仍是「没送出去的那些」，枚数对得上账。
                kept_set = set(source_indexes)
                dropped = [u for i, u in enumerate(units) if i not in kept_set]
                stub = PACK_STUB_KEPT if truncated else PACK_STUB_NONE
            elif trimmable:
                # R122 判据 ①②：低于门槛的桩不交，宁可这一发空手说人话，也不许把一条看着像
                # 证据、其实只剩几个字的空壳当检索结果交出去。没送出去就不记账（不记假消耗）。
                stub = PACK_STUB_REFUSED
            # trimmable 为假＝每一候选连截断标记都装不下：照旧空手，由调用方说「本题料超窗」那一句
        if key and packed_tokens:
            _pack_ledger[key] = used + packed_tokens
            _pack_ledger.move_to_end(key)
            while len(_pack_ledger) > _STEP_PACK_LEDGER_MAX:
                _pack_ledger.popitem(last=False)
        billed = used + packed_tokens
    #: 账本身份名＝键前缀（step/request/task/thread/off），``[PromptPack]`` 的字段一枚不改名。
    #: ``tier=`` 今天交的是**买单那一档的名字**（由 ``profile`` 决定，缺省即在册的 ``analysis``），
    #: 字段名与相对顺序一枚没动（``tests/test_r117_ledger_turn_scoped.py`` 与
    #: ``tests/test_r445_pack_priority.py`` 钉着）；``prompt_estimate_tokens`` 与 room 用的是同一
    #: 枚 ``prefix_reserve``，这两格从此不可能互相打脸。
    ledger_kind = key.split(":", 1)[0] if key else "off"
    logger.info(
        f"{PROMPT_PACK_MARKER} leg={leg} tier={profile} room_total={room_total} "
        f"room_left={room} candidates={len(units)} fitted={len(fitted)} dropped={len(dropped)} "
        f"truncated={truncated} stub={stub} packed_tokens={packed_tokens} ledger_packed_tokens={billed} "
        f"prompt_estimate_tokens={prefix_reserve + billed} ledger={ledger_kind} "
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
        source_indexes=source_indexes,
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
        from app.rag.retrieval_pipeline import requested_document_names
        original_question = str(((config or {}).get("configurable") or {}).get("data_question") or "")
        if requested_document_names(original_question):
            query = original_question
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

        # R112：装箱之后才是发给模型的返回串。装不下丢名次最低的整条；整批都装不下才开救援
        # （``keep_first_truncated``）：按名次往下找第一条交得出去的料，整条装得下交整条、装不下
        # 裁它的正文尾巴，R445 之前这里只试第一名，第一名太长就整批空手。
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
# （键名 rbac.ROW_SCOPE_ATTR）。密级口径已于 2026-09-28 裁定＝甲（出处
# docs/handoff/2026-09-17-human-gates.md 最后一节「H13 结案 ＋ A1/A3 裁定」；口径已写进契约
# docs/api/contract-v1.md 的「## R467」节），但本层的计数器只有部门那一维，所以密级这一维
# 这里既不动它、也不替它报因由。
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
        # 这帧是被另一个维度清空的——而本层只翻译部门维度的计数器（契约
        # docs/api/contract-v1.md 的「## R467」节把这一支的理由正是这么改口的：换掉的只是
        # 理由，这一支仍然不报因由）。密级口径已于 2026-09-28 裁定＝甲（出处
        # docs/handoff/2026-09-17-human-gates.md 最后一节「H13 结案 ＋ A1/A3 裁定」），
        # 它不在本层的计数器里，所以照样不许对它下结论。
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
# 这个事实，不替本层没有计数器的维度下结论（密级口径已于 2026-09-28 裁定＝甲，出处
# docs/handoff/2026-09-17-human-gates.md 最后一节「H13 结案 ＋ A1/A3 裁定」；口径已写进契约
# docs/api/contract-v1.md 的「## R467」节，那里明写这一支仍然只报 no_visible_rows、不报因由）。
# 判据源只有一个，码与人话不可能各说各话。
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
    from app.tools.excel import filter_explicit_categories
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
            question = str(conf.get("data_question") or "")
            df = load_excel(file_path, query=question) if question else load_excel(file_path)
            category_frame = df
            df, scope_info = filter_dataframe_rows_with_scope(df, role=role, department=dept)
            if df.empty:
                # 码与文案同判据源：一个给机器，一个给人看，同一条 reason_code。
                scope_codes.append(_row_scope_code(scope_info))
                parts.append(_row_scope_line(fname, scope_info))
                continue
            produced += 1
            try:
                df = filter_explicit_categories(df, question or query, category_frame=category_frame)
            except ValueError as exc:
                return _denial_text(config, tool="analyze_data", code="validation_error",
                                    head=f"筛选条件无法执行：{exc}")
            pending_datasets.append((fname, df, len(parts)))
            if df.attrs.get("filter_note"):
                parts.append(f"📁 {fname}: {df.attrs['filter_note']}")
            if df.empty:
                parts.append("筛选后没有符合条件的记录，不计算全表金额。")
                continue
            profile = profile_dataframe(df)
            cols_info = [f"{c['name']}({c['dtype']})" if isinstance(c, dict) else str(c) for c in profile["columns"]]
            parts.append(f"📁 {fname}: {profile['rows']}行 × {len(cols_info)}列 — 列: {', '.join(cols_info)}")
            if df.attrs.get("sheet_name"):
                parts.append(f"本次只读取工作表「{df.attrs['sheet_name']}」；工作簿全部工作表：{'、'.join(df.attrs['sheet_names'])}。")

            # 根据 query 计算具体答案
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            # R185：文本列名单走 excel 那一族语义谓词的唯一出口，不再自己比 dtype 字面串。
            # 旧写法只靠 pandas 3 那条声明要移除的兼容通道才勉强捞到 str 列，string/category 两族当场漏。
            text_cols = select_text_columns(df)

            try:
                series: list[dict] = []
                ai_parts = _answer_query(df, question or query, numeric_cols, text_cols, series_out=series)
                parts.extend(ai_parts)
                #: 10-07 现读（走查环 7）：图腿自己调用 analyze_data 时，数在这条边界上就算完了，
                #: 可模型连发 21 发 generate_chart 只带标签不带数值，最后把本地模型的历史挤空、
                #: 服务端 500，一轮白等 114 s、屏上零张图。数既然已经在手，就不该再押在模型的抄写上。
                record_chart_series(bag_from_config(config), series)
            except Exception:
                # R192 病灶二第 1 层（可诊断性）：这一支改前是裸 `pass`——异常被吞干净之后，
                # 员工看见的是"这份文件没结论"，运维侧一个字都没有，现场不可复现。
                # 记账只走仓里既有那一条通路（record_tool_status：本文件上方几处拒绝出口用的
                # 就是它），不另立日志器、不 print、不新增 logging 配置。
                # 码取这条边界本来就会给的兜底码：app/trace/spans.py::error_code_for 对未登记的
                # 异常交 internal_error。本单不发明新码——新增一枚枚举码要同时动
                # app/agents/contracts.py 与前端键集合（tests/test_error_code_vocabulary.py 与
                # 那枚"枚举＝前端键"用例双向钉着），两处都不在本单写域内。
                # 落 failed 而不是 rejected：evidence._terminal_status 会把任何 rejected 折成
                # permission_denied，那是把"算不出来"说成"没权限"（本文件 _record_denial 同一规矩）。
                record_tool_status(
                    bag_from_config(config),
                    tool="analyze_data",
                    status="failed",
                    error_code="internal_error",
                )

            # 返回前 15 行数据用于图表。
            # R451：标题与它的正文必须是同一枚 unit，不许切成两条。切成两条时装箱按整条取舍，
            # 前缀填装那一支与 R445 的名次救援那一支都够得着这一形状：标题那条装得下、JSON 那条
            # 装不下 ⇒ 交出去的是一段以 "数据样本(前15行)" 收尾的话，承诺了 15 行样本
            # 而后面一个字节都没有。并成一枚以后 "正文没装下" 与 "标题也没出去" 是同一件事，两条支
            # 用同一把尺，判定只留在这一处，装箱那一层一个字都不必知道小节语法。
            # 这不是新规矩，是把这一层本来就有的规矩补齐：_answer_query 的排名/统计/分组/预览四段
            # 各自都是 "\n".join(lines) 出来的一整条，样本是唯一把标题切出去的那一支。
            try:
                sample = df.head(15).to_dict(orient="records")
                parts.append(
                    "--- 数据样本(前15行) ---\n"
                    + json.dumps(sample, ensure_ascii=False, default=str)
                )
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
    # R122：整批装不下时开救援裁桩，桩的正文不够门槛就不交，改说「预算用尽」——第一个文件的
    # 文件名那一行不是分析结论，模型读不出数。R445：救援按名次找第一条交得出去的料，所以交出来
    # 的可能是后面某个文件的整段，下面那句「这个文件的第一段还在不在送出的那些里」必须按名次判。
    fitted = _pack_into_prompt_room(
        config, leg="data", units=parts, keep_first_truncated=True
    )
    # R112 复验第 2 条（与 doc 腿同一读法）：装箱没送出去的那个文件，证据袋不许说模型读过它。
    # 存活线以前是前缀长度（"装箱只裁尾巴 ⇒ 第一段还在前缀里"）；R445 的救援会交名次更后面的
    # 那一段，前缀长度当场认错文件，所以改按 ``source_indexes`` 判"它的第一段真被送出去了"。
    # 前缀填装那一支里两种读法逐字等价（名次就是下标）。
    _kept_indexes = set(fitted.source_indexes)
    for _ds_fname, _ds_df, _ds_index in pending_datasets:
        if _ds_index in _kept_indexes:
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


#: R462 · safe_query 交回的查询结果里，pandas 多级索引会落成 tuple 键：
#: app/tools/excel.py:476 的 Series.to_dict()（df.groupby(['区域','季度'])['销售额'].sum()
#: 那一族）与 app/tools/excel.py:474 的 DataFrame.to_dict(orient="records")
#: （df.groupby('区域').agg({'销售额': ['sum','mean']}) 那一族）。元组不是 JSON 合法的键，
#: 而 json.dumps 的 default= 只作用于**值**，对键一律当场抛
#: keys must be str, int, float, bool or None, not tuple（实测加 default=str 一个字都救不了，
#: 所以那不是修法）。造键那两行不在本单写域，本函数是本条腿唯一的 JSON 契约出口，
#: 于是在序列化之前把层级元组展成字符串键：逐层原样保序，用 _TUPLE_KEY_SEPARATOR 连接。
#: 🔴 非 tuple 键与所有值原样交回，没有 tuple 键的负载出来的结构与改前完全相等。
_TUPLE_KEY_SEPARATOR = " | "


def _flatten_query_key(key: Any) -> Any:
    """层级元组展成字符串键；其余键型原样不动。"""
    if not isinstance(key, tuple):
        return key
    return _TUPLE_KEY_SEPARATOR.join(str(part) for part in key)


def _flatten_query_tuple_keys(value: Any) -> Any:
    """递归展平查询结果里的 tuple 键，供 _query_data 那一次 json.dumps 之前用（R462）。

    只重建 dict 与 list 两类容器，标量与非 tuple 键原样交回：今天全部在绿路径（单级 groupby、
    纯数字、平面 records 键）交出去的结构与改前逐枚相等，本单不顺手改它们的形状。

    🔴 两枚不同的原键若展成同一枚字符串就当场抛，不合并、不覆盖、不吞异常。静默去重等于
    交出一枚看着正常、实际混了两行的键——跟进单 §133 判据要的是"修成字符串键"，
    不是"让它别炸"。
    """
    if isinstance(value, dict):
        flat: dict[Any, Any] = {}
        origin: dict[Any, Any] = {}
        for key, item in value.items():
            normalized = _flatten_query_key(key)
            if normalized in origin and origin[normalized] != key:
                raise ValueError(
                    "查询结果的层级键展平后撞成同一枚字符串，拒绝合并："
                    f"{origin[normalized]!r} 与 {key!r} 都展成 {normalized!r}"
                )
            origin[normalized] = key
            flat[normalized] = _flatten_query_tuple_keys(item)
        return flat
    if isinstance(value, list):
        return [_flatten_query_tuple_keys(item) for item in value]
    return value


def _query_data(query: str, config: RunnableConfig) -> str:
    from app.common.rbac import filter_dataframe_rows_with_scope
    from app.tools.excel import load_excel, safe_query
    from app.tools.excel import filter_explicit_categories
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
            question = str(conf.get("data_question") or "")
            df = load_excel(file_path, query=question) if question else load_excel(file_path)
            category_frame = df
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
        try:
            df = filter_explicit_categories(df, question or query, category_frame=category_frame)
        except ValueError as exc:
            return f"查询未完成：{exc}"
        if df.empty:
            return f"{df.attrs.get('filter_note', '')}筛选后没有符合条件的记录。"
        attempted += 1
        code = _llm_pandas_code(df, query)
        res = safe_query(df, code)
        if res.get("error") is None:
            result = res["result"]
            if not isinstance(result, str):
                # R462：多级索引的结果带 tuple 键，先在契约出口展平成字符串键，再序列化。
                result = json.dumps(
                    _flatten_query_tuple_keys(result), ensure_ascii=False, default=str
                )
            # R112：查询结果是一整块（只有一条候选），装箱装不下时只能裁这块的尾巴（带可见
            # 截断标记），连标记都装不下就换那一句指名"本题数据结果超出本机上下文"的话。
            # R445 按名次扫的救援在这一条候选上与旧读法同形：交得出就是它自己的整条或桩。
            # R122：裁出来那一截的正文不够门槛也不交——"📊 x.xlsx 查询结果:"加三个字不是答案。
            sheet = f" 工作表「{df.attrs['sheet_name']}」" if df.attrs.get("sheet_name") else ""
            query_text = f"📊 {fname}{sheet} 查询结果:\n{result}"
            if df.attrs.get("filter_note"):
                query_text += f"\n{df.attrs['filter_note']}"
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

#: 图腿失败的三张脸，每张一句人话加一枚公开码（形状抄导出腿 ``_EXPORT_NO_DEPARTMENT_HEAD``）。
#: 改前只有两枚裸 f-string：``except Exception as e: return f"图表生成失败: {e}"`` 把画图函数抛出的
#: 异常原句直接拼进客户可见正文、且不落日志；登记那一腿更糟——它整个在 try 之外，
#: ``app/storage/artifacts.py::ArtifactRegistry.register`` 交回的「artifact owner must have a
#: department scope」由 langgraph 的 ToolNode 按 TOOL_CALL_ERROR_TEMPLATE 折成「Error: …」交给
#: 模型：既没有稳定码，又把内部英文词表卖给了客户。一手读数见
#: docs/testing/walkthrough-2026-10-06/README.md 缺陷 #2 与 #3（环 7：chart_artifact.found=false、
#: total=0、charts_on_screen=0，而终答正文 6 250 字，屏上零字说清「为什么没有图」）。
#: 次序现在是反过来的：先问登记表收不收，收不下就不写盘。
_CHART_NO_DEPARTMENT_HEAD = (
    "本轮没有生成图表文件：产物台账要求发起这一轮的账号有部门归属，而这个账号的部门是空的。"
    "图落盘也登记不进去、查不回来，所以本轮不写盘——请管理员先给这个账号补部门归属"
)
_CHART_REGISTRATION_REFUSED_HEAD = "本轮的图表文件没能登记进产物台账：这一轮没有可打开的图表文件"
_CHART_GENERATION_FAILED_HEAD = "图表生成失败：这一轮没有写出图表文件"
_CHART_FAILURE_CODE_RE = re.compile(r"error_code=([a-z_]+)")


def _discard_unregistrable_chart(path: object) -> None:
    """登记不上的那一枚图不该留在盘上：形状与理由抄在册正例 ``_discard_unregistrable_report``。

    它自己抄的是 ``app/api/v1/data.py::upload_excel``——登记失败时删的就是刚写的那一枚。这里删的
    也只可能是本函数这一次调用刚交回来的路径：私有化部署的机器上，一枚没有台账行、因而没有任何
    权限判定管得着它的 PNG/HTML，留着就是留着一个人人可读、系统却不认的原件。
    """
    if not path:
        return
    try:
        os.remove(str(path))
    except OSError as exc:
        logger.warning(f"[Tool] unregistered chart left on disk: {exc}")


def _chart_terminal_error_code(text: object) -> str:
    """图腿没交出图时 span 上写哪一枚码：读它自己那句话里带的码，两路同源（抄导出腿）。

    一句都没有码的老形状只剩「不支持的图表类型」那一枚，它本来就是模型拼错的参数，沿用
    ``validation_error``；带得出码却不是公开枚举成员的名字（``authorization_required``）一律折回
    ``internal_error``——本层不替公开词表扩容，也不再把所有失败洗成同一枚码（走查缺陷 #3 要的
    正是「参数没验过」与「画图函数抛了」分色）。
    """
    match = _CHART_FAILURE_CODE_RE.search(str(text or ""))
    if not match:
        return "validation_error"
    return _public_error_code(match.group(1), "internal_error")


#: 模型把图型写成中文是常态：本机 10-07 12:21 现读，图腿第一发交回 chart_type="柱状图"
#: （validation_error），反思重试那一发写对了 "bar" 却把数值那一栏留空（internal_error）。
#: 同义词只在这一处收，未知名照旧走「不支持的图表类型」那一句——
#: tests/test_r715_chart_leg_refuses_before_a_byte_lands.py 钉着那句与它那枚码。
_CHART_TYPE_ALIASES = {
    "柱状图": "bar", "柱图": "bar", "条形图": "bar", "直方图": "bar",
    "折线图": "line", "曲线图": "line", "线图": "line",
    "饼图": "pie", "饼状图": "pie", "圆形图": "pie", "扇形图": "pie",
    "雷达图": "radar", "蜘蛛图": "radar",
    "甘特图": "gantt", "进度图": "gantt", "里程碑图": "gantt",
    "思维导图": "mindmap", "脑图": "mindmap",
}

#: 图腿第四张脸：名目收到了、数字没跟上。以前这一格由画图函数抛异常换成一句
#: 「图表生成失败」，客户看不出差在哪一栏；现在它在写盘之前就说出口。
_CHART_NO_NUMBERS_HEAD = (
    "本轮没有生成图表文件：横轴的名目收到了，纵轴的数字是空的。"
    "这不是画图组件坏了，是这一轮没算出可画的数——"
    "请确认选中的数据文件里有一列能求和或计数，或换一种说法再问一次。"
)


def _normalize_chart_type(chart_type: object) -> str:
    """图型名只认六个英文键，先把中文同义词翻过来，其余原样交回（小写化）。"""
    name = str(chart_type or "").strip()
    if not name:
        return ""
    return _CHART_TYPE_ALIASES.get(name) or _CHART_TYPE_ALIASES.get(name.lower()) or name.lower()


def _as_sequence(raw: object) -> list:
    """名目与数值都可能是 None、真数组、或一枚 JSON 串／逗号串：模型只被要求「给一串」。"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, dict):
        return list(raw.values())
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith(("[", "{")):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, (list, tuple)):
            return list(parsed)
        if isinstance(parsed, dict):
            return list(parsed.values())
    return [piece.strip() for piece in re.split(r"[,;、\n]", text) if piece.strip()]


#: 一个「数」可能长成 {"金额": "12,300"} 那样。单位只剥不改值：带「万」的字符串解析不出来，
#: 宁可交回 None 让图腿说出「没拿到数」，也不悄悄把 12 万画成 12。
_NUMBER_KEYS = ("值", "数值", "金额", "数量", "总数", "合计", "value", "y", "count", "total", "amount")
_UNIT_NOISE = (",", "元", "￥", "¥", "$", "%", " ", "，")


#: 横轴名目在模型手里最常长的几种「有名字的那一格」；认不出就退回逐个值里挑第一个标量。
_LABEL_KEYS = ("label", "name", "category", "x", "名称", "名字", "标签", "类目")


def _as_label(item: object) -> str:
    """横轴名目只认标量文本。

    10-07 13:10 现读（走查环 7，后端日志 ``[Tool] chart generation failed: TypeError:
    unhashable type: 'dict'``）：模型把 labels 交成一串 dict（每枚形如 ``{"发生月份": "2026-01",
    "金额": 67770}``），那枚 dict 一路走进 matplotlib 的分类轴，画图当场炸，客户看到的只有
    「图表生成失败：这一轮没有写出图表文件」。名字从 dict 里挑第一个标量，挑不出就交回空串。
    """
    if item is None or isinstance(item, bool):
        return ""
    if isinstance(item, (str, int, float)):
        return str(item).strip()
    if isinstance(item, dict):
        for key in _LABEL_KEYS:
            found = _as_label(item.get(key))
            if found:
                return found
        for value in item.values():
            found = _as_label(value)
            if found:
                return found
        return ""
    if isinstance(item, (list, tuple)):
        for value in item:
            found = _as_label(value)
            if found:
                return found
        return ""
    return str(item).strip()


def _as_number(item: object) -> float | None:
    if isinstance(item, bool):
        return None
    if isinstance(item, (int, float)):
        return float(item)
    if isinstance(item, dict):
        for key in _NUMBER_KEYS:
            if key in item:
                found = _as_number(item[key])
                if found is not None:
                    return found
        for value in item.values():
            found = _as_number(value)
            if found is not None:
                return found
        return None
    if isinstance(item, (list, tuple)):
        return _as_number(item[0]) if item else None
    text = str(item or "").strip()
    for noise in _UNIT_NOISE:
        text = text.replace(noise, "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_series(datasets: object) -> list:
    """模型把数字放进 datasets 而没放 values 时取第一条序列：柱图与饼图只画一条。"""
    if not isinstance(datasets, dict):
        return []
    for series in datasets.values():
        numbers = [n for n in (_as_number(item) for item in _as_sequence(series)) if n is not None]
        if numbers:
            return numbers
    return []


#: 装箱时的挑选次序：分组汇总是「按客户点名的维度算出来的一串数」，最贴近一张柱状图；
#: 排名/预览次之。读不出的 kind 给零分，不加分。
_BOX_KIND_PREFERENCE = {"group": 300.0, "ranking": 200.0, "preview": 100.0}


def _best_series_row(bag: dict | None, labels: list | None, title: str) -> dict:
    """本轮缓冲里与「模型点名的那一串横轴」最对得上的那一行数；对不上交回空表。

    装箱与填名目两件事共用这一枚打分：只认账上真算过的 series，不猜、不编。
    """
    candidates = [
        row
        for row in ((bag or {}).get("chart_series") or [])
        if isinstance(row, dict) and row.get("labels") and row.get("values")
    ]
    if not candidates:
        return {}
    given = [str(item).strip() for item in (labels or []) if str(item).strip()]

    def score(row: dict) -> float:
        own = [str(item).strip() for item in row.get("labels") or []]
        base = _BOX_KIND_PREFERENCE.get(str(row.get("kind") or ""), 0.0)
        hint = str(title or "")
        for token in (row.get("column"), row.get("dimension")):
            name = str(token or "")
            if len(name) >= 2 and name in hint:
                base += 50.0
        if not given:
            return base + float(len(own))
        hit = sum(1 for item in given if item in own)
        if hit and hit * 2 >= len(given):
            return base + 1000.0 + float(hit)
        if len(own) == len(given):
            return base + 500.0
        return -1.0

    best = max(candidates, key=score)
    return {} if score(best) < 0 else best


def _requested_group_series(bag: dict | None, question: str) -> dict:
    groups = [row for row in (bag or {}).get("chart_series", [])
              if row.get("kind") == "group" and row.get("labels") and row.get("values")]
    dimension = _named_dimension_column(question, list(dict.fromkeys(str(row.get("dimension") or "") for row in groups)))
    if not dimension:
        return {}
    matching = [row for row in groups if row.get("dimension") == dimension]
    return _best_series_row({"chart_series": matching}, None, question)


def _boxed_chart_series(bag: dict | None, labels: list | None,
                        title: str) -> tuple[list, list, str, dict]:
    """模型点了横轴的名、没把数带回来：从本轮缓冲里取那一串数，按名对齐装箱。

    交回 ``(labels, values, 出处, 账上那一行)``；对不上就交回空——空装箱照旧走「这一轮没有数字」
    那句人话，绝不为了画出图而编一串数。出处只进日志，用来归因「这张图的数是模型给的还是自己装的」。
    """
    best = _best_series_row(bag, labels, title)
    if not best:
        return [], [], "", {}
    #: 模型点名的那一串横轴，归一化与上面 _best_series_row 同一枚。7c00d9a 把「按名对齐」这一段
    #: 搬进这枚函数时没把它一起搬过来：模型只给名、不给数的那一发当场 NameError——given 在这里
    #: 从来没被赋值。屏上现象＝零张图，图腿交回一段「您可以这样画」的散文（10-08 00:25 环 7 现读
    #: 就是这个形状：装箱不再顶穿窗口之后，模型这一发正是只点名不给数）。
    given = [str(item).strip() for item in (labels or []) if str(item).strip()]
    own_labels = [str(item).strip() for item in best.get("labels") or []]
    own_values = list(best.get("values") or [])
    if not given:
        use_labels, use_values = own_labels, own_values
    elif all(item in own_labels for item in given):
        by_label = dict(zip(own_labels, own_values))
        pairs = [(item, by_label[item]) for item in given]
        use_labels, use_values = [item[0] for item in pairs], [item[1] for item in pairs]
    elif len(given) == len(own_labels):
        # 模型换了写法（「1月」对「2026-01」）：按名次对齐，标签沿用它点名的写法。
        use_labels, use_values = given, own_values
    else:
        by_label = dict(zip(own_labels, own_values))
        pairs = [(item, by_label[item]) for item in given if item in by_label]
        use_labels, use_values = [item[0] for item in pairs], [item[1] for item in pairs]
    if not use_values or len(use_labels) != len(use_values):
        return [], [], "", {}
    return use_labels, use_values, f"{best.get('dimension')}×{best.get('column')}", best


#: 同一发画图请求在本轮里最多试几枚：10-07 12:43 现读，模型每 5 s 交回同一枚参数，八次之后
#: 本地模型服务端 500（Jinja: No user query found in messages），一轮白等 114 s。
_CHART_REPEAT_LIMIT = 2
_CHART_REPEAT_HEAD = "这一发画图请求本轮已经原样试过 {times} 次，结果一样，不必再试"

#: 模型没写标题时挂在屏上的那句占位话。写死成一枚常量，是为了让「它到底写没写」判得出来。
_DEFAULT_CHART_TITLE = "数据分析图表"


def _chart_face_labels(title: str, row: dict) -> tuple[str, str, str]:
    """标题与两条轴的名字：只从账上那一行取，不新造话（横轴＝dimension，纵轴＝column）。

    10-07 现读那一轮：图画对了，标题却还挂着「数据分析图表」，两条轴也没有名字——客户看不出
    这是报销金额按月。模型自己写了标题就留着它的，只有它没写（或抄了缺省值）才由名目填。
    """
    dimension = str((row or {}).get("dimension") or "").strip()
    column = str((row or {}).get("column") or "").strip()
    head = str(title or "").strip()
    if head in ("", _DEFAULT_CHART_TITLE):
        if column and dimension:
            head = f"{column}（按{dimension}）"
        else:
            head = column or dimension or _DEFAULT_CHART_TITLE
    return head, dimension, column


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
    title: str = _DEFAULT_CHART_TITLE,
) -> str:
    from app.storage.artifacts import ArtifactOwnerScopeMissing, owner_can_register_artifact
    from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
    from app.tools.visualize import gantt_chart, mindmap as _mindmap

    chart_type = _normalize_chart_type(chart_type)
    labels = [text for text in (_as_label(item) for item in _as_sequence(labels)) if text]
    values = [n for n in (_as_number(item) for item in _as_sequence(values)) if n is not None]
    #: 同一发参数原样重交：本轮缓冲里数着它，超过上限就直接交回那句「不必再试」，
    #: 不再跑 matplotlib、不再登记、也不再给本地模型一次 5 s 的往返。
    bag = bag_from_config(config)
    if bag is not None:
        fingerprint = json.dumps(
            {"type": chart_type, "labels": labels, "values": values,
             "datasets": sorted((datasets or {}).keys()), "title": str(title or "")},
            ensure_ascii=False, sort_keys=True, default=str,
        )
        attempts = bag.setdefault("chart_attempts", {})
        times = int(attempts.get(fingerprint, 0) or 0) + 1
        attempts[fingerprint] = times
        if times > _CHART_REPEAT_LIMIT:
            return _denial_text(
                config, tool="generate_chart", code="chart_refusal_repeated",
                head=_CHART_REPEAT_HEAD.format(times=times),
            )
    requested = _requested_group_series(bag, str(((config or {}).get("configurable") or {}).get("data_question") or ""))
    if requested and chart_type in ("bar", "line", "pie"):
        labels, values = list(requested["labels"]), list(requested["values"])
        if chart_type == "line":
            datasets = {str(requested.get("column") or "金额"): values}
    if chart_type in ("bar", "pie") and not values:
        values = _first_series(datasets)
    #: 模型给的名字轴与数值仍凑不齐一张图时，先回头看本轮算过的数——不猜、不编，只对得上才用。
    series_row: dict = requested
    if chart_type in ("bar", "line", "pie") and not values:
        box_labels, box_values, box_from, series_row = _boxed_chart_series(
            bag_from_config(config), labels, title)
        if box_values:
            labels = box_labels
            values = box_values
            logger.info(
                "[ChartBox] 图腿自己装箱 series=%s labels=%d values=%d title=%s",
                box_from,
                len(labels),
                len(values),
                title,
            )
    #: 名与数对不齐时多出来的那一截画不进同一根柱子，先按短的截齐——截齐比抛进 matplotlib
    #: 换回一句「生成失败」诚实，也不许为此偷偷补数。
    if chart_type in ("bar", "line", "pie") and labels and values and len(labels) != len(values):
        keep = min(len(labels), len(values))
        logger.info("[ChartBox] 名目与数值条数不齐 labels=%d values=%d，按 %d 截齐", len(labels), len(values), keep)
        labels, values = labels[:keep], values[:keep]
    if chart_type in ("bar", "pie") and not values:
        return _denial_text(
            config, tool="generate_chart", code="validation_error", head=_CHART_NO_NUMBERS_HEAD
        )
    if chart_type in ("line", "radar") and not values and not _first_series(datasets):
        return _denial_text(
            config, tool="generate_chart", code="validation_error", head=_CHART_NO_NUMBERS_HEAD
        )
    #: 名目：装箱那一腿顺手交回账上那一行；模型自己把数带回来了也要再问一次缓冲，
    #: 只为取「这串数是哪一列、按哪一维分的」——取不到就照旧留缺省，不编。
    if not series_row and chart_type in ("bar", "line", "pie"):
        series_row = _best_series_row(bag_from_config(config), labels, title)
    title, xlabel, ylabel = _chart_face_labels(title, series_row)
    chart_funcs = {
        "bar": lambda: bar_chart(labels or [], values or [], title=title,
                                 xlabel=xlabel, ylabel=ylabel),
        "line": lambda: line_chart(labels or [], datasets or {"数据": values or []}, title=title,
                                   xlabel=xlabel, ylabel=ylabel),
        "pie": lambda: pie_chart(labels or [], values or [], title=title),
        "radar": lambda: radar_chart(categories or labels or [], datasets or {"数据": values or []}, title=title),
        "gantt": lambda: gantt_chart(tasks or [], title=title),
        "mindmap": lambda: _mindmap(root or title, branches or {}, title=title),
    }

    if chart_type not in chart_funcs:
        return f"不支持的图表类型: {chart_type}，可选: bar/line/pie/radar/gantt/mindmap"

    try:
        principal = _artifact_principal(config, ACTION_ANALYZE)
        if principal is None:
            record_tool_status(
                bag_from_config(config), tool="generate_chart", status="rejected", error_code="authorization_required"
            )
            return _authorization_error()
        #: preflight：属主交不出部门 ⇒ 登记表当场必拒 ⇒ 一枚字节都不许先落盘（与导出腿同一次序）。
        if not owner_can_register_artifact(principal):
            return _denial_text(
                config,
                tool="generate_chart",
                code="department_scope_required",
                head=_CHART_NO_DEPARTMENT_HEAD,
            )
        path = chart_funcs[chart_type]()

        try:
            urls = _artifact_urls(path, "chart", config)
        except ArtifactOwnerScopeMissing as exc:
            #: 拒收真落在写盘之后（同一刻改的部门、另一枚根因）：孤儿字节当场收回。
            logger.warning(f"[Tool] chart registration refused: {type(exc).__name__}: {exc}")
            _discard_unregistrable_chart(path)
            return _denial_text(
                config,
                tool="generate_chart",
                code="department_scope_required",
                head=_CHART_REGISTRATION_REFUSED_HEAD,
            )
        if urls is None:
            _record_denial(
                config, tool="generate_chart", code="authorization_required", status="rejected"
            )
            return _authorization_error()
        url, _ = urls
        if path.lower().endswith(".html"):
            return f"图表已生成: [{title}]({url})"
        return f"图表已生成: ![{title}]({url})"
    except Exception as exc:  # noqa: BLE001 - 失败要说得出口，内部原句不许替它说话
        logger.warning(f"[Tool] chart generation failed: {type(exc).__name__}: {exc}")
        return _denial_text(
            config,
            tool="generate_chart",
            code="internal_error",
            head=_CHART_GENERATION_FAILED_HEAD,
        )



# ==================== Export Tool ====================

#: 导出腿失败的三张脸，每张一句人话加一枚公开码。旧形状只有一枚 f-string，而且它拼的是
#: 登记表内部的英文原句：走查环 8 现读到的那 51 字就是
#: 「报告生成失败: 」+「artifact owner must have a department scope」——既没有码（终态只剩
#: 一句人话，机器读不出因由），又把内部词表卖给了客户（同族旧账见
#: docs/current-functionality-2026-09-10-revision-log.md 的 R-新4），而那一轮已经先往盘上
#: 落了一枚谁都登记不上的 PDF。次序现在是反过来的：先问登记表收不收，收不下就不写盘。
_EXPORT_NO_DEPARTMENT_HEAD = (
    "本轮没有导出报告文件：产物台账要求发起这一轮的账号有部门归属，而这个账号的部门是空的。"
    "文件落盘也登记不进去、查不回来，所以本轮不写盘——请管理员先给这个账号补部门归属"
)
_EXPORT_REGISTRATION_REFUSED_HEAD = (
    "本轮的报告文件没能登记进产物台账：这一轮没有可下载的报告文件"
)
_EXPORT_GENERATION_FAILED_HEAD = "报告生成失败：这一轮没能写出报告文件"
_EXPORT_BAD_SECTIONS_HEAD = "报告没能导出：这一轮交来的报告章节读不出来"
_EXPORT_FAILURE_CODE_RE = re.compile(r"error_code=([a-z_]+)")


def _discard_unregistrable_report(path: object) -> None:
    """登记不上的那一枚报告文件不该留在盘上：产物口只认台账，落单的字节谁也查不回来。

    在册正例是 ``app/api/v1/data.py::upload_excel`` —— 登记失败时删的就是自己刚写的那一枚。
    这里删的也只可能是本函数这一次调用刚交回来的路径：私有化部署的机器上，一枚没有台账行、
    因而没有任何权限判定管得着它的 PDF，留着就是留着一个人人可读、系统却不认的原件。
    """
    if not path:
        return
    try:
        os.remove(str(path))
    except OSError as exc:
        logger.warning(f"[Tool] unregistered report left on disk: {exc}")


def _export_terminal_error_code(text: object) -> str:
    """导出腿没交出报告时，span 上写哪一枚码：读它自己那句话里带的码，读不到才兜底。

    正文与码同源（都出自 ``_denial_text`` 那一处），所以不会出现「说的是部门、码写的是内部错」
    这种两张皮。枚举之外的名字一律折回 ``internal_error``：``authorization_required`` 不在封闭
    枚举里（``tests/test_error_code_vocabulary.py`` 钉着这件事），本层不替它扩公开词表。
    """
    match = _EXPORT_FAILURE_CODE_RE.search(str(text or ""))
    return _public_error_code(match.group(1) if match else "", "internal_error")


def _verified_data_sections(filename: str, analysis: str) -> list[dict]:
    lines = []
    for line in analysis.splitlines():
        if line.startswith("--- 数据样本"):
            break
        if line == "数据分析结果:" or (line.startswith("📁 ") and "实际筛选：" not in line):
            continue
        if "实际筛选：" in line:
            line = line[line.index("实际筛选："):]
        lines.append(line)
    return [
        {"type": "heading", "content": "核验数据与筛选结果"},
        {"type": "text", "content": f"数据来源：{filename}"},
        {"type": "text", "content": "\n".join(lines)},
    ]


def _export_report(report_title: str, sections_json: str,
                    config: RunnableConfig, include_charts: str = "") -> str:
    from app.storage.artifacts import ArtifactOwnerScopeMissing, owner_can_register_artifact
    from app.tools.export import generate_pdf_report

    try:
        principal = _artifact_principal(config, ACTION_EXPORT)
        if principal is None:
            record_tool_status(
                bag_from_config(config), tool="export_report", status="rejected", error_code="authorization_required"
            )
            return _authorization_error()
        if not owner_can_register_artifact(principal):
            return _denial_text(
                config,
                tool="export_report",
                code="department_scope_required",
                head=_EXPORT_NO_DEPARTMENT_HEAD,
            )
        try:
            sections = json.loads(sections_json)
        except (TypeError, ValueError) as exc:
            #: 章节是模型自己拼的那枚参数：说成"读不出来"（validation_error），不冒充内部错。
            logger.warning(f"[Tool] report sections unreadable: {type(exc).__name__}")
            return _denial_text(
                config,
                tool="export_report",
                code="validation_error",
                head=_EXPORT_BAD_SECTIONS_HEAD,
            )
        if not isinstance(sections, list) or any(not isinstance(item, dict) for item in sections):
            return _denial_text(config, tool="export_report", code="validation_error", head=_EXPORT_BAD_SECTIONS_HEAD)
        conf = (config or {}).get("configurable", {}) or {}
        filename = str(conf.get("data_filename") or "").strip()
        if filename:
            # Re-read the selected table through the authorized data tool. This survives
            # HITL resumption without trusting another worker's model-written prose.
            from app.agents.evidence import new_evidence_bag
            verified_bag = new_evidence_bag()
            verified_config = {**(config or {}), "configurable": {**conf, "evidence_bag": verified_bag}}
            question = str(conf.get("data_question") or "按部门汇总金额与合计")
            analysis = _analyze_data(question, verified_config)
            if not verified_bag.get("datasets"):
                return _denial_text(config, tool="export_report", code="validation_error",
                                    head="选中数据未能完成授权核验，未生成报告。")
            sections = _verified_data_sections(filename, analysis)
            bag = bag_from_config(config)
            if bag is not None:
                bag.setdefault("datasets", []).extend(verified_bag["datasets"])
        # Chart paths supplied by a model are never filesystem authority.
        sections = [item for item in sections if item.get("type") != "chart"]
        #: 装箱由产品自己做：模型交回的 sections 里那一格图永远填不出来（它只拿到 URL，
        #: 拿不到容器路径），所以这里按台账取本轮的图，连同 include_charts 里它点名的那几枚。
        charts = _round_chart_paths(config, principal)
        asked = [item.strip() for item in re.split(r"[,;，；\n]", str(include_charts or "")) if item.strip()]
        logger.info("[R726ExportCharts] leg=export round_charts=%d asked=%d", len(charts), len(asked))
        path = generate_pdf_report(title=report_title, sections=sections, chart_paths=charts)

        try:
            urls = _artifact_urls(path, "report", config)
        except ArtifactOwnerScopeMissing as exc:
            logger.warning(f"[Tool] report registration refused: {type(exc).__name__}: {exc}")
            _discard_unregistrable_report(path)
            return _denial_text(
                config,
                tool="export_report",
                code="department_scope_required",
                head=_EXPORT_REGISTRATION_REFUSED_HEAD,
            )
        if urls is None:
            _record_denial(
                config, tool="export_report", code="authorization_required", status="rejected"
            )
            return _authorization_error()
        _, url = urls
        return f"报告已生成: [📋 下载报告]({url})"
    except Exception as exc:  # noqa: BLE001 - 失败要说得出口，内部原句不许替它说话
        logger.warning(f"[Tool] report generation failed: {type(exc).__name__}: {exc}")
        return _denial_text(
            config,
            tool="export_report",
            code="internal_error",
            head=_EXPORT_GENERATION_FAILED_HEAD,
        )


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
    """生成图表。参数契约（缺一项就画不出来）：
    - chart_type 只认 bar/line/pie/radar/gantt/mindmap 六个英文键，不要写中文；
    - labels 是横轴名称数组，values 是与它等长的纯数字数组（如 [67770, 52710]），两者必须同时给；
    - values 里的数必须逐字来自上一手 analyze_data 交回的结论；
    - 上一手没算出数字时不要调用本工具，直接用文字说明原因。"""
    with start_tool_call(
        config,
        tool_name="generate_chart",
        arguments={
            "chart_type": chart_type,
            "title": title,
            "label_count": len(labels or []),
            "value_count": len(values or []),
            #: 10-07 现读：图腿连着两发 value_count=0，光看这两格分不出「模型没给数」还是
            #: 「数在 datasets 里」。名字与条数是形状，不是客户数据，画不出图时它就是归因。
            "datasets_names": sorted(str(key) for key in datasets) if isinstance(datasets, dict) else None,
            "categories_count": len(categories or []),
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
            span.finish("failed", error_code=_chart_terminal_error_code(result))
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
            span.finish("failed", error_code=_export_terminal_error_code(result))
        return result


# ==================== 工具列表 ====================

ALL_TOOLS = [search_docs, analyze_data, query_data, generate_chart, export_report]
