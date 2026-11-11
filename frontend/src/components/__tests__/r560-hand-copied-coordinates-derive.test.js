/**
 * R560 · 前端注释里手抄的坐标：一枚都不许躲，逐枚现读对账
 *
 * 病（09-30 与 10-01 各一例，同一族）：注释里抄着别人家的行号，后端或兄弟件一挪就撒谎。
 * r416 / r420 / r427 / r538 各治了自己那几枚，整个 frontend/src 从没被一次现扫覆盖过。
 * 本件的台账由现扫生成：注释里每一枚「文件:行号」（含同一注释块里继承上一枚文件名的裸 :行号）
 * 都在台账里有且只有一条，多一枚少一枚都红——删引用躲检查、手抄一枚新数字，当场撞。
 *
 * 甲 全覆盖：现扫枚数 == 台账枚数，且按（所在文件, 注释里写的引用名）逐组等长。
 * 乙 逐枚对账：真位置在 git show HEAD:<真源> 里按锚段当场推导；注释声称的那枚数字必须等于推导值，
 *    区间引用另比「区间长 <= 锚段长」。锚段找不到或不唯一 ⇒ 抛，绝不少测一枚、绝不 skip。
 * 丙 量具自证：锚段不存在必须抛；把推导的读法换成工作树，未提交态那一发必须对不上（HEAD 读法才绿）。
 * R562 收尾（本单的三格）：① 未锚定归零——每一枚都补上了当场推导的锚段，长区间一律锚到「区间长 <= 锚段长」；
 *   ② 归属定死——裸冒号与多义短名一律在注释里写出仓内全路径，继承那条正则一字未动（它是牙）；
 *   假坐标（声称行号越界、契约与实现张冠李戴）逐枚按真源改口，逐枚证据记在交回里。
 * 丁 自述对账：台账／已锚定／未锚定三枚枚数各自与这里写的自述相等；ROSTER 段以外 0 处坐标字面量；
 *    未锚定那一格逐枚点名在册，谁把 debt 藏起来谁红。
 *
 * 反证三把（读数在交回里逐枚点名）：刀一改歪一枚在册坐标 => 本件乙组红，同一发也咬在册钉 r538 甲组；
 * 刀二把锚段换成真源里不存在的串 => 当场抛；刀三把读法改成工作树 => 未提交态那一发红。
 */
import { execFileSync } from 'node:child_process'
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
/* R560-ROSTER-BEGIN */
const ROSTER = [
  { f: "frontend/src/App.vue", t: "App.vue", p: "frontend/src/App.vue", a: ["const userRole = shallowRef('staff')"] },
  { f: "frontend/src/App.vue", t: "lib/http.js", p: "frontend/src/lib/http.js", a: ["emit({ type: 'unauthorized', message: '登录状态已失效，请重新登录。' })"] },
  { f: "frontend/src/App.vue", t: "frontend/src/lib/http.js", p: "frontend/src/lib/http.js", a: ["emit({ type: 'expiring', message: `登录状态将在约 ${minutes} 分钟后过期，请提前重新登录。` })"] },
  { f: "frontend/src/App.vue", t: "lib/http.js", p: "frontend/src/lib/http.js", a: ["export const TOKEN_KEY = 'eb_token'", "export const USER_KEY = 'eb_user'", "export const ROLE_KEY = 'eb_role'", "export const DEPARTMENT_KEY = 'eb_department'", "export const EXPIRES_KEY = 'eb_token_expires_at'"] },
  { f: "frontend/src/App.vue", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export const SESSIONS_KEY = 'eb_sessions_v2'", "const MESSAGE_KEY_PREFIX = 'eb_msg_'"] },
  { f: "frontend/src/__tests__/r278-logout-locality.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export async function readBackendSessionList() {"] },
  { f: "frontend/src/__tests__/r278-logout-locality.test.js", t: "frontend/src/lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export function mergeServerSessions(rows) {"] },
  { f: "frontend/src/__tests__/r278-logout-locality.test.js", t: "frontend/src/lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["activeId.value = ''", "sessions.value = []", "messages.value = []", "activeDataFilename.value = ''", "hitl.value = null", "scrollOffset.value = 0", "loading.value = false", "clearStoredSessions()", "}", "", "export async function removeSession(id) {", "const wasActive = id === activeId.value", "sessions.value = sessions.value.filter(s => s.id !== id)", "try { localStorage.removeItem(MESSAGE_KEY(id)) } catch (_) { /* 已不存在 */ }", "if (!sessions.value.length) newSession()"] },
  { f: "frontend/src/__tests__/r278-logout-locality.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export function resetSessions() {"] },
  { f: "frontend/src/__tests__/r278-topbar.test.js", t: "docs/frontend-plan-2026-09-14.md", p: "docs/frontend-plan-2026-09-14.md", a: ["- [ ] 顶栏无死控件；退出按钮有可及名称"] },
  { f: "frontend/src/__tests__/r278-topbar.test.js", t: "components/__tests__/r333-notification-bell.test.js", p: "frontend/src/components/__tests__/r333-notification-bell.test.js", a: ["describe('R333 判据① · 徽标的数字只可能来自后端全集未读', () => {"] },
  { f: "frontend/src/__tests__/r278-topbar.test.js", t: "frontend/src/components/__tests__/r333-notification-bell.test.js", p: "frontend/src/components/__tests__/r333-notification-bell.test.js", a: ["})", "", "it('is_exact=false 时徽标与读屏一起改口说「至少」：下界不许冒充全数', async () => {"] },
  { f: "frontend/src/__tests__/r278-topbar.test.js", t: "frontend/src/components/__tests__/r333-notification-bell.test.js", p: "frontend/src/components/__tests__/r333-notification-bell.test.js", a: ["})", "", "it('未读为零：徽标不画数字，读屏念的是「没有未读通知」；这一格与「还没读到」不是同一句话', async () => {"] },
  { f: "frontend/src/__tests__/r278-topbar.test.js", t: "frontend/src/components/__tests__/r333-notification-bell.test.js", p: "frontend/src/components/__tests__/r333-notification-bell.test.js", a: ["})", "", "it('可见的徽标数字对读屏是隐藏的：孤零零一个 3 不配上屏，可读表达只有 aria-label 那一处', async () => {"] },
  { f: "frontend/src/__tests__/r278-topbar.test.js", t: "frontend/src/components/__tests__/r333-notification-bell.test.js", p: "frontend/src/components/__tests__/r333-notification-bell.test.js", a: ["it('铃铛在顶栏里画的是「还没读出来」那一张脸：SSR 阶段一个数字都不许凭空摆（0 与未知不是 3）', async () => {"] },
  { f: "frontend/src/__tests__/r380-shape-table.test.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["", "", "@router.post(\"/login\")"] },
  { f: "frontend/src/__tests__/r380-shape-table.test.js", t: "alerts.py", p: "app/api/v1/alerts.py", a: ["raise HTTPException(status_code=400, detail=f\"非法操作符: {data.op}\")"] },
  { f: "frontend/src/__tests__/r380-shape-table.test.js", t: "app/common/auth.py", p: "app/common/auth.py", a: ["return False, \"用户名和密码不能为空\""] },
  { f: "frontend/src/__tests__/r380-shape-table.test.js", t: "common/authorization.py", p: "app/common/authorization.py", a: ["raise PermissionError(f\"权限不足: {action} ({decision.reason_code})\")"] },
  { f: "frontend/src/__tests__/r380-shape-table.test.js", t: "frontend/src/lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["export const FALLBACK_MESSAGE = '操作没有完成，请稍后重试。'"] },
  { f: "frontend/src/__tests__/r380-shape-table.test.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise HTTPException(", "status_code=403,", "detail={", "\"code\": DEPARTMENT_SELF_REPORT_DENIED,", "\"message\": \"department must match the authenticated principal\",", "},"] },
  { f: "frontend/src/__tests__/r399-trace-render.test.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["per_request[trace_id] = {"] },
  { f: "frontend/src/__tests__/r399-trace-render.test.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["\"segment_sum_ms\": segment_sum_ms,"] },
  { f: "frontend/src/components/AdminPanel.vue", t: "app/common/auth.py", p: "app/common/auth.py", a: ["if role not in CREATABLE_ROLES:  # R357：真源在 app/common/permissions.py，本处只 import"] },
  { f: "frontend/src/components/AdminPanel.vue", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["async def delete_user(user_id: int, request: Request):"] },
  { f: "frontend/src/components/AdminPanel.vue", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["role: str = \"staff\"", "department: str = \"\""] },
  { f: "frontend/src/components/ApprovalPanel.vue", t: "lib/__tests__/r281-dictionary-voice.test.js", p: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", a: ["expect(errorDetail(shape2(), '审批预审失败')).toBe(errorText('department_override_denied'))"] },
  { f: "frontend/src/components/ApprovalPanel.vue", t: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", p: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", a: ["expect(result.rawMessage).toBe(ANY_ENGLISH)"] },
  { f: "frontend/src/components/ApprovalPanel.vue", t: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", p: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", a: ["})", "}", ""] },
  { f: "frontend/src/components/ArtifactList.vue", t: "ChartViewer.vue", p: "frontend/src/components/ChartViewer.vue", a: ["caption: String,", "downloadName: String,", "})"] },
  { f: "frontend/src/components/ArtifactList.vue", t: "lib/artifacts.js", p: "frontend/src/lib/artifacts.js", a: ["error.code = 'missing_url'"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "app/common/reliable_queue.py", p: "app/common/reliable_queue.py", a: ["existing = self.redis.get(self._idempotency_key(key))", "if existing:", "request_id = existing.decode() if isinstance(existing, bytes) else str(existing)", "message = self.redis.get(self._message_key(request_id))"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "deploy/queue_worker.py", p: "deploy/queue_worker.py", a: ["def _scope_shape(field: str, value):"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["没有可判引用的那一轮原样交回。这不是放水：闸门裁的是文档的部门与密级，本轮既然没点名"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "reliable_queue.py", p: "app/common/reliable_queue.py", a: ["#:   1. `docs/api/contract-v1.md` 的 `## Long Task Status`：那枚同步钉用 AST 逐枚比对词表，"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "app/common/reliable_queue.py", p: "app/common/reliable_queue.py", a: ["#:   3. 量具停表 `scripts/eval_transport_ask_v2.py::_poll_queue`。"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "lib/provenance.js", p: "frontend/src/lib/provenance.js", a: ["if (status === 'cancel_requested') {"] },
  { f: "frontend/src/components/ChatPanel.vue", t: "lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["* 什么，与屏幕上画了什么无关。三条设计决定，逐条写清为什么：", "*   ① 为什么新开这一格，而不是扩既有的「错误码：xxx」小字（errorCodeLabel/formatError）：", "*      那条小字刻意只在「后端回了一枚字典收不下的码」时才出 —— errorCodeLabel 对已登记的 rawCode", "*      一律回空串，errcodes.test.js 拿「散文命中的已知码不追加「错误码：」小字」与「formatError", "*      对已知码不加噪声小字」两枚用例逐字钉着。而这次要留下的后端原文恰恰多半挂在**已登记**的码上", "*      （department_override_denied 就在 LEGACY_ALIASES 在册，后端那句英文正是这一发的信封 message）。", "*      走小字那条通道就得先把「未知码专属」改判成常开，再把自由散文塞进一枚短标签通道："] },
  { f: "frontend/src/components/ChatPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["② 没有同因复述 ⇒ 尺子那句原样搬（``report.degradation_sentence``），本格一个字不加工，"] },
  { f: "frontend/src/components/DataPanel.vue", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["raise HTTPException(status_code=404, detail=\"resource_not_found\")", "return path"] },
  { f: "frontend/src/components/DataPanel.vue", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["os.replace(temp_path, file_path)"] },
  { f: "frontend/src/components/DataPanel.vue", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["# tests/test_r200_restricted_single_source.py keeps every exit honest to it.", "restricted_withheld: list[tuple[str, str]] = []", "principal = principal_from_request(request) if request is not None else None", "for path in directory.iterdir():", "if not path.is_file() or path.suffix.lower() not in DATA_FILE_EXTENSIONS:", "continue", "record = dataset_registry.get_active_by_filename(path.name)", "if request is not None:", "if record is None:", "# Not a lie and not a refusal: an unregistered file is not part of the"] },
  { f: "frontend/src/components/DataPanel.vue", t: "data.py", p: "app/api/v1/data.py", a: ["if hasattr(value, \"isoformat\"):", "return value.isoformat()"] },
  { f: "frontend/src/components/DataPanel.vue", t: "app/agents/tools.py", p: "app/agents/tools.py", a: ["按它出牌）。它只决定**扣哪一档自己声明的** ``declared_max_tokens``，不改名次、不改门槛、", "不改台账字段。room 不再由本处或 ``retrieval_pipeline`` 各算一遍，而是问 ``ModelBudget", ".pack_room_tokens``——发请求前那道守卫判拒用的正是同一枚数（``app/agents/contracts.py``", "的 ``prompt_room``），所以装箱装到边界就是守卫的边界：再大一枚 token 当场少塞一片，而不是", "塞完之后由下游那道守卫把整发拒掉（跟进单 §133 五：装箱交出的 14 928 枚题面，加上该档", "自己声明的输出顶，恰好是判拒读数 ``required_n_ctx=16464 > MODEL_CONTEXT_TOKENS=16384``）。", "\"\"\"", "from app.common.model_budget import model_tier_budget", "from app.rag.retrieval_pipeline import (", "CONTEXT_HISTORY_RESERVE_TOKENS,", "CONTEXT_PACK_TIER,", "CONTEXT_SHELL_RESERVE_TOKENS,", "PROMPT_PACK_MARKER,", "pack_prefix_by_rank,", "text_pack_tokens,", ")"] },
  { f: "frontend/src/components/DataPanel.vue", t: "data.py", p: "app/api/v1/data.py", a: ["if not path.is_file() or path.suffix.lower() not in DATA_FILE_EXTENSIONS:", "continue", "record = dataset_registry.get_active_by_filename(path.name)", "if request is not None:"] },
  { f: "frontend/src/components/DataPanel.vue", t: "data.py", p: "app/api/v1/data.py", a: ["surface does not speak about owners\" are different answers.", ""] },
  { f: "frontend/src/components/DocPanel.vue", t: "chat.py", p: "app/api/v1/chat.py", a: ["answer_candidates.append(content)", "# R464：整段回放帧同样过闸门。落在中途而不接得上屏上正文的那一枚，"] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["classification: int = Form(1),"] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/common/rbac.py", p: "app/common/rbac.py", a: ["ROLE_CLEARANCE = {\"staff\": 1, \"manager\": 2, \"admin\": 3, \"auditor\": 3}"] },
  { f: "frontend/src/components/DocPanel.vue", t: "policy.py", p: "app/common/policy.py", a: ["\"core\": 4,"] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["def _pdf_extraction_cell(extraction: DocumentExtraction | None) -> dict | None:"] },
  { f: "frontend/src/components/DocPanel.vue", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["`GET /api/v1/sessions/{id}` re-runs `scope.allows` on read-back instead of trusting `is_owned_by`"] },
  { f: "frontend/src/components/DocPanel.vue", t: "chat.py", p: "app/api/v1/chat.py", a: ["这一支。不返回 ``{}`` —— 一个空对象读起来像「查过了，什么都没查到」，而那恰恰是判据③"] },
  { f: "frontend/src/components/DocPanel.vue", t: "chat.py", p: "app/api/v1/chat.py", a: ["``source_counts`` 里的 ``blank`` 与 ``ocr-empty`` 各自说话，不合并、不引申。"] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/rag/loader.py", p: "app/rag/loader.py", a: ["SCANNED_PAGE_TEXT_CHARS = 48", "", "#: 运维覆盖入口（与 app/documents/index_policy.py 的 DOCUMENT_INDEX_MIN_CHARS 同风格：", "#: **调用期**读环境变量，不在 import 期固化，避开 conftest R70 那一段坑）。", "SCANNED_PAGE_TEXT_CHARS_ENV = \"PDF_SCANNED_PAGE_TEXT_CHARS\""] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["\"resource_status\": str(declared.get(\"status\") or \"active\"),"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: [":title=\"noticeTitle\""] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["v-if=\"notice\""] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["noticeTitle.value = title"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["function raiseNotice(title, detail, retryable) {"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["raiseNotice('文档列表没加载出来', errorDetail(err, '文档列表加载失败'), true)"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["raiseNotice('文件没能下载', errorDetail(err, '文件下载失败'), false)"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["if (failed.length) raiseNotice('部分文档没能删除', `有 ${failed.length} 个文档未能删除：${failed.join('、')}`, false)"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["raiseNotice('删除没有完成', errorDetail(err, '删除失败'), false)"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["notice.value = ''"] },
  { f: "frontend/src/components/DocPanel.vue", t: "lib/provenance.js", p: "frontend/src/lib/provenance.js", a: ["export function classificationLabel(value) {"] },
  { f: "frontend/src/components/DocPanel.vue", t: "DataPanel.vue", p: "frontend/src/components/DataPanel.vue", a: ["const restrictedNotice = computed(() => {"] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/documents/index_policy.py", p: "app/documents/index_policy.py", a: ["return \"该文档未进入知识库索引，文件与目录记录均已保留。\""] },
  { f: "frontend/src/components/DocPanel.vue", t: "tests/test_frontend_upload_auth.py", p: "tests/test_frontend_upload_auth.py", a: ["assert \"function createUploadItem(file) {\" in source", "assert \"return reactive({\" in source", "assert \"const item = createUploadItem(file)\" in source"] },
  { f: "frontend/src/components/DocPanel.vue", t: "tests/test_frontend_upload_auth.py", p: "tests/test_frontend_upload_auth.py", a: ["upload_fn = source.split(\"async function uploadSingleFile(file) {\", 1)[1]"] },
  { f: "frontend/src/components/DocPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["def _pdf_extraction_cell(extraction: DocumentExtraction | None) -> dict | None:"] },
  { f: "frontend/src/components/GraphPanel.vue", t: "app/api/v1/intelligence.py", p: "app/api/v1/intelligence.py", a: ["is allowed, naming another one is refused with ``department_override_denied``, so a"] },
  { f: "frontend/src/components/NotificationBell.vue", t: "r278-topbar.test.js", p: "frontend/src/__tests__/r278-topbar.test.js", a: ["*   ② 通知：今天没有一句诚实的「条数」可摆。GET /hitl/pending 的 count 是一页过滤后的长度"] },
  { f: "frontend/src/components/TracePanel.vue", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["analysis: '允许进数据分析与图表，但不产文件',"] },
  { f: "frontend/src/components/TracePanel.vue", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const router = useRouter()"] },
  { f: "frontend/src/components/__tests__/panel-states.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["}", "pendingSessionDelete.value = ''"] },
  { f: "frontend/src/components/__tests__/r168-hitl-decision.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["\"Cache-Control\": \"no-cache\",", "\"X-Accel-Buffering\": \"no\",", "**_lane_readout_headers(lane_readout or {}),"] },
  { f: "frontend/src/components/__tests__/r171-auth-event-copy.test.js", t: "lib/http.js", p: "frontend/src/lib/http.js", a: ["emit({ type: 'unauthorized', message: '登录状态已失效，请重新登录。' })"] },
  { f: "frontend/src/components/__tests__/r171-auth-event-copy.test.js", t: "frontend/src/lib/http.js", p: "frontend/src/lib/http.js", a: ["emit({ type: 'expiring', message: `登录状态将在约 ${minutes} 分钟后过期，请提前重新登录。` })"] },
  { f: "frontend/src/components/__tests__/r171-auth-event-copy.test.js", t: "lib/http.js", p: "frontend/src/lib/http.js", a: ["emit({ type: 'unauthorized', message: '登录状态已失效，请重新登录。' })"] },
  { f: "frontend/src/components/__tests__/r186-row-scope-voices.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["raise HTTPException(status_code=404, detail=\"resource_not_found\")", "return path"] },
  { f: "frontend/src/components/__tests__/r186-row-scope-voices.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["os.replace(temp_path, file_path)"] },
  { f: "frontend/src/components/__tests__/r186-row-scope-voices.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["# tests/test_r200_restricted_single_source.py keeps every exit honest to it.", "restricted_withheld: list[tuple[str, str]] = []", "principal = principal_from_request(request) if request is not None else None", "for path in directory.iterdir():", "if not path.is_file() or path.suffix.lower() not in DATA_FILE_EXTENSIONS:", "continue", "record = dataset_registry.get_active_by_filename(path.name)", "if request is not None:", "if record is None:", "# Not a lie and not a refusal: an unregistered file is not part of the"] },
  { f: "frontend/src/components/__tests__/r186-row-scope-voices.test.js", t: "app/agents/tools.py", p: "app/agents/tools.py", a: ["cached = False", "_retrieval_pack_support[key] = cached", "return cached", "", "", "def _pack_into_prompt_room(", "config, *, leg: str, units, keep_first_truncated: bool = False, profile: str | None = None", ") -> list:", "\"\"\"按名次把 ``units`` 装进本轮剩余 room，打一行的账，返回装进去的那几段。", "", "``units`` 必须已按优先级从高到低排好（检索腿回来的顺序就是 RRF/重排分数降序，数据腿", "按文件与结论的既有顺序）：装箱只从尾部裁，不在这里重新发明排序。", ""] },
  { f: "frontend/src/components/__tests__/r186-row-scope-voices.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["if not path.is_file() or path.suffix.lower() not in DATA_FILE_EXTENSIONS:", "continue", "record = dataset_registry.get_active_by_filename(path.name)", "if request is not None:"] },
  { f: "frontend/src/components/__tests__/r197-turn-key-inheritance.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["// 后端早就把这些字段吐到线上了（R41 的 sources、R35 的 cached 三枚、R26 的 queued），"] },
  { f: "frontend/src/components/__tests__/r197-turn-key-inheritance.test.js", t: "SourceCard.vue", p: "frontend/src/components/SourceCard.vue", a: ["const ariaOf = (row, signal) => feedbackAriaLabel(signal, rowFilename(row))"] },
  { f: "frontend/src/components/__tests__/r197-turn-key-inheritance.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["<CacheFace v-if=\"cacheFaceOf(msg, i)\" :face=\"cacheFaceOf(msg, i)\" :key=\"`cache-${turnKey(msg, i)}`\" />"] },
  { f: "frontend/src/components/__tests__/r197-turn-key-inheritance.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["if (msg && typeof msg.mid === 'string' && msg.mid) return `m${msg.mid}`"] },
  { f: "frontend/src/components/__tests__/r197-turn-key-inheritance.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["if (!chatEl.value) return"] },
  { f: "frontend/src/components/__tests__/r197-turn-key-inheritance.test.js", t: "sessions.js", p: "frontend/src/lib/sessions.js", a: ["messages.value = entry ? [...entry.messages] : []"] },
  { f: "frontend/src/components/__tests__/r198-queue-poll-stop.test.js", t: "lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["rawCode: token,", "message: cleanText(alias.message) || target.message,"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["// 顶栏那个绿点以前是写死的：不管机器上有没有模型，它都显示「本地模型」。", "// 现在改成读 /health/details 的 problems，读不到就显示「状态未知」——不确定不是坏消息，", "// 把不确定画成健康才是。", "const runtimeHealth = ref(null)", "const modelStateValue = computed(() => modelState(runtimeHealth.value))"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["//", "// 改前（本单基点 09c968f 的现读：本文件那三行 refreshRuntimeHealth 与挂载期那一句）：挂载"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["/**", "* 把终态帧那四枚键抄进这一轮：袋里那份管当场重渲染，消息对象那份管随会话落盘与刷新复原。"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["* 把缺席写成空串或 null 会说成「后端交了空值」（后端明明没说话），写成请求值就是说假话。"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const kept = {}"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["kept[key] = data[key]"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["if (!Object.keys(kept).length) return"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const kept = {}"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["kept[key] = data[key]"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["return principal", "", "", "def _agent_user_context(principal) -> dict | None:"] },
  { f: "frontend/src/components/__tests__/r202-queue-poll-stop-authz.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["\"\"\"Build the Agent runtime context that grants a request its authorization scope.\"\"\""] },
  { f: "frontend/src/components/__tests__/r221-queue-deadline.test.js", t: "app/common/reliable_queue.py", p: "app/common/reliable_queue.py", a: ["existing = self.redis.get(self._idempotency_key(key))", "if existing:", "request_id = existing.decode() if isinstance(existing, bytes) else str(existing)", "message = self.redis.get(self._message_key(request_id))"] },
  { f: "frontend/src/components/__tests__/r221-queue-deadline.test.js", t: "deploy/queue_worker.py", p: "deploy/queue_worker.py", a: ["def _scope_shape(field: str, value):"] },
  { f: "frontend/src/components/__tests__/r221-queue-deadline.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["没有可判引用的那一轮原样交回。这不是放水：闸门裁的是文档的部门与密级，本轮既然没点名"] },
  { f: "frontend/src/components/__tests__/r221-queue-deadline.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["没有可判引用的那一轮原样交回。这不是放水：闸门裁的是文档的部门与密级，本轮既然没点名"] },
  { f: "frontend/src/components/__tests__/r237-r40-standard-auto.test.js", t: "frontend/src/devFixtures/approval-demo.js", p: "frontend/src/devFixtures/approval-demo.js", a: ["// resolve_standard_from_knowledge_base），取不到就如实报「未给出」，而不是由前端塞一枚"] },
  { f: "frontend/src/components/__tests__/r237-r49-index-face.test.js", t: "app/documents/index_policy.py", p: "app/documents/index_policy.py", a: ["INDEX_STATUS_INDEXED = \"indexed\"", "INDEX_STATUS_EXCLUDED = \"excluded\"", "INDEX_STATUS_UNKNOWN = \"unknown\""] },
  { f: "frontend/src/components/__tests__/r237-r49-index-face.test.js", t: "app/documents/catalog.py", p: "app/documents/catalog.py", a: ["", "", "def public_document_row(row: dict) -> dict:"] },
  { f: "frontend/src/components/__tests__/r237-r49-index-face.test.js", t: "catalog.py", p: "app/documents/catalog.py", a: ["public[\"size_bytes\"] = _resolved_size(storage_path, row.get(\"size_bytes\"))", "public[\"parse_status\"] = _normalise_parse_status(row.get(\"parse_status\"))", "# R49: index_status / index_reason answer \"will the assistant find this document\", and a", "# row that was excluded has to say so out loud -- that is the whole point of the slice.", "# A row that recorded no decision at all (everything stored before R49, and any row the", "# sidecar cannot describe) stays silent instead of being stamped \"unknown\": absence is", "# the only honest answer there, and it keeps a client from rendering a historical", "# document as \"deliberately not indexed\". Clients must read the three cases as:", "#   index_status == \"excluded\"  -> 未索引，index_reason says why", "#   index_status == \"indexed\"   -> 已入索引", "#   key absent                  -> 本单之前入库的历史行，按 parse_status 显示，不得显示未索引", "recorded_status = row.get(\"index_status\")", "if recorded_status in (None, \"\"):", "public.pop(\"index_status\", None)"] },
  { f: "frontend/src/components/__tests__/r237-r49-index-face.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["f\"拦下的字数={[len(body) for body in answer_stream.held]}\""] },
  { f: "frontend/src/components/__tests__/r237-r49-index-face.test.js", t: "app/documents/index_policy.py", p: "app/documents/index_policy.py", a: ["REASON_UNCHANGED_CONTENT = \"unchanged_content\"", "REASON_INDEX_REFUSED = \"index_refused\"", "", "#: 由本模块的内容判定得出的排除原因。", "POLICY_REASONS = ("] },
  { f: "frontend/src/components/__tests__/r247-approval-mount-dedupe.test.js", t: "panel-states.test.js", p: "frontend/src/components/__tests__/panel-states.test.js", a: ["expect(s).toContain('onMounted(submitCheck)')"] },
  { f: "frontend/src/components/__tests__/r267-overview-no-self-fed-rows.test.js", t: "app/api/v1/dashboard.py", p: "app/api/v1/dashboard.py", a: ["alerts = _alert_counts(request)", "if alerts is not None:", "payload[\"alerts\"] = alerts"] },
  { f: "frontend/src/components/__tests__/r267-overview-no-tech-note.test.js", t: "DashboardPanel.vue", p: "frontend/src/components/DashboardPanel.vue", a: ["async function loadDashboard() {"] },
  { f: "frontend/src/components/__tests__/r267-overview-real-status.test.js", t: "DashboardPanel.vue", p: "frontend/src/components/DashboardPanel.vue", a: ["// 这个 catch 原先把错误整个吞掉，于是「查失败了」和「还没查」都长成", "// 「查询指标口径后显示证据」那一句空话——R1(c) 要拆的就是这种同脸。"] },
  { f: "frontend/src/components/__tests__/r267-overview-real-status.test.js", t: "frontend/src/components/DashboardPanel.vue", p: "frontend/src/components/DashboardPanel.vue", a: ["await loadDashboard()", "if (!error.value) await loadTrend()"] },
  { f: "frontend/src/components/__tests__/r268-chat-panel-shell.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["}", "", "// ==================== 会话管理 ===================="] },
  { f: "frontend/src/components/__tests__/r268-chat-panel-shell.test.js", t: "ArtifactList.vue", p: "frontend/src/components/ArtifactList.vue", a: ["*/", "export function openErrorView(state) {"] },
  { f: "frontend/src/components/__tests__/r268-chat-panel-shell.test.js", t: "DataPanel.vue", p: "frontend/src/components/DataPanel.vue", a: ["import ArtifactList, { advanceDelete, deleteButtonLabel, deleteErrorView, isPendingDelete } from './ArtifactList.vue'"] },
  { f: "frontend/src/components/__tests__/r268-chat-panel-shell.test.js", t: "frontend/src/router/index.js", p: "frontend/src/router/index.js", a: ["// （POST /approve），而「报销」是一枚业务专属词 —— 客户一装机就以为产品只管报销。"] },
  { f: "frontend/src/components/__tests__/r268-data-table.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export const activeDataFilename = shallowRef('')"] },
  { f: "frontend/src/components/__tests__/r268-queue-cancel.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "def _receipt_degradation_note(report: PdfExtractionReport) -> str:"] },
  { f: "frontend/src/components/__tests__/r268-queue-cancel.test.js", t: "QueueFace.vue", p: "frontend/src/components/QueueFace.vue", a: ["data-testid=\"queue-face\"", ":data-kind=\"face.kind\"", ":data-ahead=\"face.ahead === null ? 'unknown' : face.ahead\"", "role=\"status\"", "aria-live=\"polite\"", ">", "<span class=\"queue-headline\" data-testid=\"queue-headline\">{{ face.headline }}</span>", "<span v-if=\"face.detail\" class=\"queue-detail\" data-testid=\"queue-detail\">{{ face.detail }}</span>", "<span v-if=\"stats\" class=\"queue-stats\" data-testid=\"queue-stats\">{{ stats.headline }}</span>", "<UiButton", "v-if=\"face.retryable\"", "class=\"queue-retry\"", "size=\"sm\"", "data-testid=\"queue-retry\"", "@click=\"emit('retry')\"", ">按原文再问一次</UiButton>", "<!-- R260 · 挂起待批准那一轮给一件能点的东西：这一枚只做【去哪一屏】，", "批准本身仍由「审批与待办」那两枚既有组件（HitlPendingPanel / HitlPendingRow）", "发到 POST /approve —— 本组件不开第二套批准路径，也不在这里判归属（鉴权在服务端）。"] },
  { f: "frontend/src/components/__tests__/r268-queue-cancel.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["if (runtimeRecheck.value.phase === 'sending') return", "runtimeRecheck.value = { phase: 'idle', outcome: '' }", "}", "", "/** 读数「长得一不一样」只由既有那两把尺算，面板不碰后端键名。 */"] },
  { f: "frontend/src/components/__tests__/r268-queue-cancel.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["② 没有同因复述 ⇒ 尺子那句原样搬（``report.degradation_sentence``），本格一个字不加工，"] },
  { f: "frontend/src/components/__tests__/r268-runtime-faces.test.js", t: "lib/health.js", p: "frontend/src/lib/health.js", a: ["export async function fetchRuntimeHealth({ force = false } = {}) {"] },
  { f: "frontend/src/components/__tests__/r268-runtime-faces.test.js", t: "app/common/monitoring.py", p: "app/common/monitoring.py", a: ["problems.append(\"embedding_model_missing\")"] },
  { f: "frontend/src/components/__tests__/r268-runtime-faces.test.js", t: "app/common/monitoring.py", p: "app/common/monitoring.py", a: ["problems.append(\"queue_unavailable\")"] },
  { f: "frontend/src/components/__tests__/r268-runtime-faces.test.js", t: "app/common/monitoring.py", p: "app/common/monitoring.py", a: ["problems.append(f\"{name}_read_only\")"] },
  { f: "frontend/src/components/__tests__/r268-session-pull.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["# 的对象，所以停在 HITL 的会话被按过停止之后，随后的批准会拿到一个生来就置位的"] },
  { f: "frontend/src/components/__tests__/r268-session-pull.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export function loadSessions() {", "let raw = null", "try {", "raw = localStorage.getItem(SESSIONS_KEY)", "} catch (_) { return '' }", "if (!raw) return ''", "try {", "const data = JSON.parse(raw)", "sessions.value = (data.sessions || []).map(s => {", "let msgs = []", "try {", "const mr = localStorage.getItem(MESSAGE_KEY(s.id))", "if (mr) msgs = JSON.parse(mr) || []", "} catch (_) { msgs = [] }", "return { ...s, messages: msgs }", "})", "return data.activeId || ''", "} catch (_) {", "return ''", "}", "}"] },
  { f: "frontend/src/components/__tests__/r268-session-pull.test.js", t: "App.vue", p: "frontend/src/App.vue", a: ["", "function persistRememberedUsername() {", "const normalizedUsername = loginUser.value.trim()", "if (rememberMe.value && normalizedUsername) {", "localStorage.setItem(REMEMBER_KEY, normalizedUsername)", "} else {", "localStorage.removeItem(REMEMBER_KEY)", "}", "}", "", "async function doLogin() {", "loginError.value = ''", "persistRememberedUsername()", "try {", "const res = await http.post('/login', {"] },
  { f: "frontend/src/components/__tests__/r274-catalog-failure-face.test.js", t: "app/api/v1/dashboard.py", p: "app/api/v1/dashboard.py", a: ["not. This is not a count of askable documents, and the frontend wording", "「N 篇还没解析完」 is written against parse, not index.", "\"\"\""] },
  { f: "frontend/src/components/__tests__/r277-approval-selfcheck-truth.test.js", t: "errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["// 出处：app/common/open_platform.py 的 STORAGE_REFUSAL_UNCONFIGURED，同一枚词也会出现在"] },
  { f: "frontend/src/components/__tests__/r285-overview-alert-silence.test.js", t: "app/api/v1/dashboard.py", p: "app/api/v1/dashboard.py", a: ["not. This is not a count of askable documents, and the frontend wording", "「N 篇还没解析完」 is written against parse, not index.", "\"\"\""] },
  { f: "frontend/src/components/__tests__/r285-overview-alert-silence.test.js", t: "dashboard.py", p: "app/api/v1/dashboard.py", a: ["# ownership clause of its own on purpose: ``alerts.alert_row_scope_sql`` is the one place"] },
  { f: "frontend/src/components/__tests__/r285-overview-alert-silence.test.js", t: "alerts.py", p: "app/api/v1/alerts.py", a: ["", "if _database_available():"] },
  { f: "frontend/src/components/__tests__/r285-overview-alert-silence.test.js", t: "permissions.py", p: "app/common/permissions.py", a: ["\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),"] },
  { f: "frontend/src/components/__tests__/r288-upload-parse-face.test.js", t: "catalog.py", p: "app/documents/catalog.py", a: ["_write_sidecar(path, kept)"] },
  { f: "frontend/src/components/__tests__/r288-upload-parse-face.test.js", t: "catalog.py", p: "app/documents/catalog.py", a: ["# A row that recorded no decision at all (everything stored before R49, and any row the", "# sidecar cannot describe) stays silent instead of being stamped \"unknown\": absence is", "# the only honest answer there, and it keeps a client from rendering a historical", "# document as \"deliberately not indexed\". Clients must read the three cases as:", "#   index_status == \"excluded\"  -> 未索引，index_reason says why", "#   index_status == \"indexed\"   -> 已入索引", "#   key absent                  -> 本单之前入库的历史行，按 parse_status 显示，不得显示未索引", "recorded_status = row.get(\"index_status\")", "if recorded_status in (None, \"\"):", "public.pop(\"index_status\", None)"] },
  { f: "frontend/src/components/__tests__/r288-upload-parse-face.test.js", t: "catalog.py", p: "app/documents/catalog.py", a: ["# documents root can never write into that root by accident."] },
  { f: "frontend/src/components/__tests__/r288-upload-parse-face.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["answer_candidates.append(content)", "# R464：整段回放帧同样过闸门。落在中途而不接得上屏上正文的那一枚，"] },
  { f: "frontend/src/components/__tests__/r288-upload-parse-face.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["await asyncio.sleep(0)", "break", "if intr:"] },
  { f: "frontend/src/components/__tests__/r291-raw-detail.test.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["{", "\"code\": \"permission_denied\",", "\"message\": \"resource access is not permitted\",", "\"retryable\": false,", "\"details\": {}", "}", "```"] },
  { f: "frontend/src/components/__tests__/r291-raw-detail.test.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["completed answer: the stream emits `error` plus `request.failed` with"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["} else if (read && !QUEUE_SETTLED.includes(read.status)"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["face = msg.queue ? queueFace(msg.queue) : null"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["restoreQueuedTurns()"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const storedActive = loadSessions()", "if (!activeId.value && storedActive && !linked) activeId.value = storedActive", "}", "if (!activeId.value) activeId.value = genId()", "// 只在 store 里还没有这份会话时回填，避免把正在写入的流替换掉。", "if (!messages.value.length && !linked) restoreActive(activeId.value)"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["face = msg.queue ? queueFace(msg.queue) : null"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["onUnmounted(() => {"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["function flushScroll() {"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export function rememberScroll() {"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "frontend/src/lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export function syncActive() {"] },
  { f: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", t: "frontend/src/lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["persist()", "}", "", "export function ensureSession() {"] },
  { f: "frontend/src/components/__tests__/r307b-app-uibutton.test.js", t: "theme.css", p: "frontend/src/assets/theme.css", a: ["/* R307 第二棒残留：顶栏退出按钮原语化后，本枚选择器 (0,2,1) 被 .ui-button--ghost:hover:not(:disabled) (0,3,0) 压掉，hover 文字色从 #5beaff 掉成 --text-2。正解在此处补一枚 .ui-button 限定把特异性抬到 (0,3,1)，零新色值；旧 selector 保留，非原语按钮不受影响。全站没有任何一枚 token 等于 #5beaff，故不许改用 token。 */"] },
  { f: "frontend/src/components/__tests__/r307b-app-uibutton.test.js", t: "theme.css", p: "frontend/src/assets/theme.css", a: ["/* R307 第二棒残留：顶栏退出按钮原语化后，本枚选择器 (0,2,1) 被 .ui-button--ghost:hover:not(:disabled) (0,3,0) 压掉，hover 文字色从 #5beaff 掉成 --text-2。正解在此处补一枚 .ui-button 限定把特异性抬到 (0,3,1)，零新色值；旧 selector 保留，非原语按钮不受影响。全站没有任何一枚 token 等于 #5beaff，故不许改用 token。 */"] },
  { f: "frontend/src/components/__tests__/r313-restricted-tally.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["\"resource_status\": str(declared.get(\"status\") or \"active\"),"] },
  { f: "frontend/src/components/__tests__/r313-restricted-tally.test.js", t: "DataPanel.vue", p: "frontend/src/components/DataPanel.vue", a: ["restrictedFiles.value = res.data.restricted || null"] },
  { f: "frontend/src/components/__tests__/r313-restricted-tally.test.js", t: "frontend/src/components/DataPanel.vue", p: "frontend/src/components/DataPanel.vue", a: ["const restrictedNotice = computed(() => {"] },
  { f: "frontend/src/components/__tests__/r313-upload-classification.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "def _cited_document_rows(content: str, catalog: list[dict]) -> list[dict]:", "\"\"\"那一轮正文点名过的文档：唯一形状是「当前目录里的文件名原样出现在正文里」。", ""] },
  { f: "frontend/src/components/__tests__/r338-pdf-readout.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["def _pdf_extraction_cell(extraction: DocumentExtraction | None) -> dict | None:"] },
  { f: "frontend/src/components/__tests__/r338-pdf-readout.test.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["`GET /api/v1/sessions/{id}` re-runs `scope.allows` on read-back instead of trusting `is_owned_by`"] },
  { f: "frontend/src/components/__tests__/r338-pdf-readout.test.js", t: "DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["const filteredDocs = computed(() => {", "if (!searchQuery.value) return docs.value", "const q = searchQuery.value.toLowerCase()", "return docs.value.filter(row => row.filename.toLowerCase().includes(q))", "})", ""] },
  { f: "frontend/src/components/__tests__/r338-pdf-readout.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["reading, not a ledger -- nothing here persists it, because a column for one would need a"] },
  { f: "frontend/src/components/__tests__/r338-pdf-readout.test.js", t: "loader.py", p: "app/rag/loader.py", a: ["SCANNED_PAGE_TEXT_CHARS = 48", "", "#: 运维覆盖入口（与 app/documents/index_policy.py 的 DOCUMENT_INDEX_MIN_CHARS 同风格：", "#: **调用期**读环境变量，不在 import 期固化，避开 conftest R70 那一段坑）。", "SCANNED_PAGE_TEXT_CHARS_ENV = \"PDF_SCANNED_PAGE_TEXT_CHARS\""] },
  { f: "frontend/src/components/__tests__/r412-one-screen-one-name.test.js", t: "frontend/src/router/index.js", p: "frontend/src/router/index.js", a: ["{", "path: `/${FEED_SCREEN}`,"] },
  { f: "frontend/src/components/__tests__/r412-one-screen-one-name.test.js", t: "src/components/DocPanel.vue", p: "frontend/src/components/DocPanel.vue", a: ["<strong>喂料</strong>"] },
  { f: "frontend/src/components/__tests__/r423-no-borrowed-screen-name.test.js", t: "r267-overview-real-status.test.js", p: "frontend/src/components/__tests__/r267-overview-real-status.test.js", a: ["expect(docRows(html).map(row => row.index)).toEqual(['已入检索索引', '未索引', '索引状态未知'])"] },
  { f: "frontend/src/components/__tests__/r423-no-borrowed-screen-name.test.js", t: "r141-lane-picker.test.js", p: "frontend/src/components/__tests__/r141-lane-picker.test.js", a: ["it('换档要说得出代价：三档各自的承诺不同句', async () => {", "const promises = {", "qa: '只用文字回答，不算数、不出图、不产文件',", "analysis: '允许进数据分析与图表，但不产文件',", "report: '一定走导出这一腿（会先请你确认）',", "}", "for (const [lane, copy] of Object.entries(promises)) {", "const html = await bareWithQuery(`/chat?lane=${lane}`)", "expect(html, `${lane} 的承诺没跟着地址变`).toContain(copy)", "}", "})"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "lib/health.js", p: "frontend/src/lib/health.js", a: ["* not_configured / degraded），名单外的新状态界面不照抄码名：屏上那一句是给人读的，"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "frontend/src/lib/health.js", p: "frontend/src/lib/health.js", a: ["}", "return out"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "frontend/src/lib/health.js", p: "frontend/src/lib/health.js", a: ["return await read", "} finally {"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "frontend/src/lib/health.js", p: "frontend/src/lib/health.js", a: ["const key = String(face.kind) + (face.id || '') + (face.headline || '')"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["import CacheFace from './CacheFace.vue'"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["if (!content) return charts"] },
  { f: "frontend/src/components/__tests__/r452-degradation-banner.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["if (preview.blobUrl) {", "URL.revokeObjectURL(preview.blobUrl)", "preview.blobUrl = ''", "}", "preview.open = true"] },
  { f: "frontend/src/components/__tests__/r48-headline-card.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["export const messages = shallowRef([])"] },
  { f: "frontend/src/components/__tests__/r48-headline-card.test.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["// 把读数一起带出去：store 的 messages 是 shallowRef，光往消息对象上塞属性，", "// 面板不会重渲染。缓存那张脸要能当场出现，就得有一条能触发的通道。"] },
  { f: "frontend/src/components/__tests__/r503-artifact-lineage-face.test.js", t: "app/api/v1/artifacts.py", p: "app/api/v1/artifacts.py", a: ["def _artifact_row(record) -> dict:", "\"\"\"One artifact as the list reports it: delivery URLs, its scope, and its generation lineage.", "", "The two lineage keys come from ``record.lineage_payload()``, i.e. from the artifact row's", "own ``session_id`` / ``request_id`` columns (R509 / migration 0017) - never off the reading", "Principal, which would make the same row claim a different source for every visitor. A", "column that is NULL publishes no key at all, so \"this deployment never recorded which turn", "produced it\" stays visibly different from \"it was produced by the empty string\".", "\"\"\"", "row = record.public_payload()", "row.update(", "{", "\"filename\": record.filename,", "\"owner_id\": record.owner_id,", "\"department_ids\": list(record.department_ids),"] },
  { f: "frontend/src/components/__tests__/r519-queue-lane-data-filename.test.js", t: "deploy/queue_worker.py", p: "deploy/queue_worker.py", a: ["return frozenset(anchors)"] },
  { f: "frontend/src/components/__tests__/r519-queue-lane-data-filename.test.js", t: "deploy/queue_worker.py", p: "deploy/queue_worker.py", a: ["f\"(reason={NON_RETRYABLE_DEAD_REASON} \"", "f\"attempts={bookkeeping.get('attempts')} max_attempts={bookkeeping.get('max_attempts')})\"", ")", "else:"] },
  { f: "frontend/src/components/__tests__/r519-queue-lane-data-filename.test.js", t: "deploy/queue_worker.py", p: "deploy/queue_worker.py", a: ["approval=chat.hitl_approval_handle("] },
  { f: "frontend/src/components/__tests__/r519-queue-lane-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["return attach_terminal_data_filename(payload, dataset_files)"] },
  { f: "frontend/src/components/__tests__/r519-queue-lane-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["\"filename\": filename,", "\"files_removed\": len(removed),", "\"catalog_rows_remaining\": len(remaining),"] },
  { f: "frontend/src/components/__tests__/r519-queue-lane-data-filename.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["\"filename\": filename,", "\"files_removed\": len(removed),", "\"catalog_rows_remaining\": len(remaining),"] },
  { f: "frontend/src/components/hitl/HitlPendingPanel.vue", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["\"approval\": approval,", "}", "return attach_terminal_data_filename(payload, dataset_files)"] },
  { f: "frontend/src/components/hitl/HitlPendingPanel.vue", t: "chat.py", p: "app/api/v1/chat.py", a: ["# 新身份账上，所以 worker 一发现它对不上现取结果就判失效，不猜、不补、不改用新部门。"] },
  { f: "frontend/src/components/hitl/HitlPendingPanel.vue", t: "chat.py", p: "app/api/v1/chat.py", a: ["row[\"published_at\"] = moment", "return rows", "", "", "# 清单键的标记前缀。它出现在 ``answer:`` 命名空间里，所以读它的路径与答案缓存共用同一把"] },
  { f: "frontend/src/components/hitl/HitlPendingPanel.vue", t: "app/storage/sessions.py", p: "app/storage/sessions.py", a: ["self.metadata_path.parent.mkdir(parents=True, exist_ok=True)"] },
  { f: "frontend/src/components/ui/UiLoadingState.vue", t: "theme.css", p: "frontend/src/assets/theme.css", a: ["/* 阴影：3 档（卡片 / 浮层 / 弹层） */"] },
  { f: "frontend/src/components/ui/__tests__/loading.test.js", t: "theme.css", p: "frontend/src/assets/theme.css", a: ["/* 阴影：3 档（卡片 / 浮层 / 弹层） */"] },
  { f: "frontend/src/components/ui/__tests__/loading.test.js", t: "states.test.js", p: "frontend/src/components/ui/__tests__/states.test.js", a: ["const ruleBodies = (css, selector) => {"] },
  { f: "frontend/src/components/ui/error-detail.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["`permission_denied`) when the scope cannot be built, and internal exception text is no"] },
  { f: "frontend/src/components/ui/error-detail.js", t: "contract-v1.md", p: "docs/api/contract-v1.md", a: ["\"retryable\": false,"] },
  { f: "frontend/src/components/ui/error-detail.js", t: "contract-v1.md", p: "docs/api/contract-v1.md", a: ["* `row_scope_denied` - the frame had rows and the caller may see none of them, and rbac can show", "the department dimension really hid them. The rows exist; they are outside this account's", "visibility. This is the only member of the domain that carries a `message`.", "* `no_visible_rows` - the frame came back empty and the row layer **deliberately declines to say", "why**. The department dimension had not hidden a row, so the clearing came from some other,", "unratified dimension (classification is H13, owner-open). Guessing a cause here would present an", "unratified dimension as a permission call, which R62/R64 ruled out.", "* `\"\"` - nothing for this layer to report: a normal answer (some or all rows visible), or a table", "that genuinely has no rows. A genuinely empty table is *not* a permission event; it stays with", "the R170 `profile.empty` marker, and consumers must not dress it in visibility wording.", "", "`message` is attached under the same condition as `row_scope_denied`, so the two cannot disagree.", "The sentence is the tool leg's own - `app/agents/tools.py::_row_scope_reason`, one translation", "source for both the streaming tool answers and this route - and it is composed from rbac counters", "only. Example, with the shape the route actually returns:", ""] },
  { f: "frontend/src/lib/__tests__/r270-department-voice.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["#: 收口名单不是另一份手抄：它就是 app/tools/excel.py 那张「扩展名 -> 读引擎」的声明表"] },
  { f: "frontend/src/lib/__tests__/r270-department-voice.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: [")", "continue"] },
  { f: "frontend/src/lib/__tests__/r270-department-voice.test.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["logger.exception(f\"[Data] dataset file could not be removed: {record.filename}\")"] },
  { f: "frontend/src/lib/__tests__/r270-department-voice.test.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["DEPARTMENT_SELF_REPORT_DENIED = \"department_override_denied\""] },
  { f: "frontend/src/lib/__tests__/r270-department-voice.test.js", t: "authorization.py", p: "app/common/authorization.py", a: ["claimed = str(claimed_department or \"\").strip()", "if not claimed or claimed in own:", "return str(principal.department or \"\")"] },
  { f: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise HTTPException(", "status_code=403,", "detail={", "\"code\": DEPARTMENT_SELF_REPORT_DENIED,", "\"message\": \"department must match the authenticated principal\",", "},"] },
  { f: "frontend/src/lib/__tests__/r281-dictionary-voice.test.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise HTTPException(", "status_code=403,", "detail={", "\"code\": DEPARTMENT_SELF_REPORT_DENIED,", "\"message\": \"department must match the authenticated principal\",", "},"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "lib/provenance.js", p: "frontend/src/lib/provenance.js", a: ["export function queueFace(queue) {"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "frontend/src/lib/provenance.js", p: "frontend/src/lib/provenance.js", a: ["if (status === 'cancelled') {"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "frontend/src/lib/provenance.js", p: "frontend/src/lib/provenance.js", a: ["* （今天在里面的是 queued / processing / cancel_requested / done / cancelled / failed / dead /"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["* `cancel_requested` (non-terminal, written by the queue): `cancel()` was called after the task had", "already left the pending list, so the cancel mark is recorded and the owning worker settles the task", "on its next check. From here the task ends `cancelled`; it never becomes `done`."] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "app/common/reliable_queue.py", p: "app/common/reliable_queue.py", a: ["\"cursor\": 0,", "\"pieces\": 0,", "\"chars\": 0,", "\"discarded\": 0,", "\"truncated\": 0,", "\"legs\": [],", "\"reason\": \"\",", "}", "raw = self.redis.lrange(self._pieces_key(request_id), 0, -1)"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["``len(page_numbers)`` 是这一堆的真枚数，``shown`` 只是画下来的那几枚：N 一律由", "真枚数减去画下来的枚数，绝不拿 ``shown`` 的长度冒充总数。", "\"\"\"", "shown = page_numbers[:PDF_DEGRADATION_PAGE_LIST_CAP]", "omitted = len(page_numbers) - len(shown)", "label = \"、\".join(str(number) for number in shown)", "tail = f\"，另有 {omitted} 页未列出\" if omitted else \"\"", "return f\"第{label}页{tail}：{reason}\""] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["return { ...bag.value, [key]: value }"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["/** 这一轮的脸挂在哪个键上：优先消息自带的 mid（随会话落盘），退回「会话 + 序号」。 */"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["`status` is one of `queued`, `processing`, `cancel_requested`, `done`, `cancelled`, `failed`, `dead`, `awaiting_approval`, or `expired`."] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["", "``omitted_groups`` 是**没逐条列出的**类数（``len(groups) - len(shown_groups)``），不是画下来的"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const read = queueReads.value[key] || null", "let face", "if (cancel && cancel.phase === 'failed') {", "face = queueCancelFailedFace(cancel.error)", "} else if (read && !QUEUE_SETTLED.includes(read.status)", "&& (read.status === 'cancel_requested' || (cancel && cancel.phase === 'requested'))) {"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "components/__tests__/r293-cancel-requested-persist.test.js", p: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", a: ["/**", "* R293 第二棒 · 判据①②③④ —— 「取消已登记」那一格落盘这条路的真路径凭据"] },
  { f: "frontend/src/lib/__tests__/r282-cancel-requested-face.test.js", t: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", p: "frontend/src/components/__tests__/r293-cancel-requested-persist.test.js", a: ["* 反证怎么算红（四把，逐把现跑，跑完按字节还原复验 ChatPanel.vue sha256 前 16 = 1fbdb3b96c7fe2f8）："] },
  { f: "frontend/src/lib/__tests__/r316-users-contract.test.js", t: "lib/errcodes.test.js", p: "frontend/src/lib/errcodes.test.js", a: ["* 为什么不许 readFileSync 工作树：fe-trunk 的 app/** 停在分支点，那里的 app/agents/contracts.py", "* 只有 16 码，拿它对账等于拿过期副本对账，会稳定假绿。三个 worktree 共享同一个 object DB，", "* `git show <ref>:<path>` 读到什么与工作树新旧无关。"] },
  { f: "frontend/src/lib/__tests__/r316-users-contract.test.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise PermissionError(f\"权限不足: {action} ({decision.reason_code})\")"] },
  { f: "frontend/src/lib/__tests__/r341-trend-contract.test.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["the assignment reddens the every-row-has-an-owner pin; (b) answering `\"\"` for an unowned row reddens"] },
  { f: "frontend/src/lib/__tests__/r360-user-writes.test.js", t: "lib/errcodes.test.js", p: "frontend/src/lib/errcodes.test.js", a: ["*", "* 为什么不许 readFileSync 工作树：fe-trunk 的 app/** 停在分支点，那里的 app/agents/contracts.py", "* 只有 16 码，拿它对账等于拿过期副本对账，会稳定假绿。三个 worktree 共享同一个 object DB，", "* `git show <ref>:<path>` 读到什么与工作树新旧无关。", "*", "* 取不到 ref / 解析不出来一律抛错让测试红。禁止 skip：skip 等于把这条对账退回成装饰。", "*/", "const CONTRACT_REF = 'codex/data-file-catalog'"] },
  { f: "frontend/src/lib/__tests__/r360-user-writes.test.js", t: "r316-users-contract.test.js", p: "frontend/src/lib/__tests__/r316-users-contract.test.js", a: ["try {", "text = execFileSync('git', ['show', `${REPO_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })", "} catch (cause) {", "throw new Error(`读不到真源 ${REPO_REF}:${path}（git show 失败：${cause.message}）。列账本不许降级，这里必须红，skip 等于回到装饰。`)", "}", "if (!text.trim()) throw new Error(`git show ${REPO_REF}:${path} 返回空内容，无法对账。`)", "return text.replace(/\\r\\n/g, '\\n')", "}", "", "/** 剥注释：块注释、行注释、模板注释都不参与「词」的扫描（同 r136 那枚 helper 的口径）。 */", "function withoutComments(text) {"] },
  { f: "frontend/src/lib/__tests__/r360-user-writes.test.js", t: "lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["context_limit_exceeded: {", "message: '这一轮的问题连同对话历史太长了，模型的上下文窗口装不下，请缩短问题或另起一轮会话再问。',", "retryable: false,", "},", "retrieval_unavailable: { message: '知识库检索暂不可用，回答可能缺少资料依据。', retryable: true },", "// 唯一出处 app/api/v1/chat.py:1303：/hitl/pending 取待确认列表时抛 PendingApprovalStoreMissing，", "// 也就是那张表还不存在（迁移没跑），503 的 detail 原样就是这个码。刻意不与下面 LEGACY_ALIASES 里", "// storage_read_only → internal_error 那句共用：「表不存在」要有人去跑迁移，「存储被切成只读」是", "// 另一回事，运维修的不是同一个故障，合并成一句就会把两条排查路都指错。"] },
  { f: "frontend/src/lib/__tests__/r360-user-writes.test.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["if data.username != principal.username and ACTION_MANAGE_USERS not in principal.permissions:", "raise HTTPException(status_code=403, detail=\"权限不足: users:manage\")"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "r208-dictionary-voice.test.js", p: "frontend/src/lib/r208-dictionary-voice.test.js", a: ["const RETRY_LATER = /稍后重试|稍后再试|请稍等|稍等|过一会儿|一会儿再|待会儿|回头再/"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "frontend/src/components/__tests__/insight-alerts.test.js", p: "frontend/src/components/__tests__/insight-alerts.test.js", a: ["expect(broken.retryable).toBe(false)"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "frontend/src/components/__tests__/insight-alerts.test.js", p: "frontend/src/components/__tests__/insight-alerts.test.js", a: ["expect(offline.retryable).toBe(true)"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "frontend/src/components/__tests__/insight-alerts.test.js", p: "frontend/src/components/__tests__/insight-alerts.test.js", a: ["expect(missing.retryable).toBe(false)"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "frontend/src/components/__tests__/insight-alerts.test.js", p: "frontend/src/components/__tests__/insight-alerts.test.js", a: ["expect(offline.retryable).toBe(true)"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "r316-users-contract.test.js", p: "frontend/src/lib/__tests__/r316-users-contract.test.js", a: ["try {", "text = execFileSync('git', ['show', `${REPO_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })", "} catch (cause) {", "throw new Error(`读不到真源 ${REPO_REF}:${path}（git show 失败：${cause.message}）。列账本不许降级，这里必须红，skip 等于回到装饰。`)", "}", "if (!text.trim()) throw new Error(`git show ${REPO_REF}:${path} 返回空内容，无法对账。`)", "return text.replace(/\\r\\n/g, '\\n')", "}"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "r208-dictionary-voice.test.js", p: "frontend/src/lib/r208-dictionary-voice.test.js", a: ["const RETRY_LATER = /稍后重试|稍后再试|请稍等|稍等|过一会儿|一会儿再|待会儿|回头再/"] },
  { f: "frontend/src/lib/__tests__/r368-retryable-source.test.js", t: "app/api/v1/artifacts.py", p: "app/api/v1/artifacts.py", a: ["raise HTTPException(status_code=500, detail=\"internal_error\") from exc"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "alerts.js", p: "frontend/src/lib/alerts.js", a: ["* R375 判据①：写路径（disposalFailureView 的 error 那一档、lib/notifications.js 的 writeFailureView）"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "frontend/src/lib/alerts.js", p: "frontend/src/lib/alerts.js", a: ["}", "if (face === 'denied') {"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "alerts.js", p: "frontend/src/lib/alerts.js", a: ["}", "if (code === 'conflict') {"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "InsightPanel.vue", p: "frontend/src/components/InsightPanel.vue", a: ["<div v-if=\"actionFailure\" class=\"alert-action-error\" data-testid=\"alert-action-failure\">", "<UiErrorState", ":title=\"actionFailure.title\"", ":description=\"actionFailure.description\"", ":code-label=\"actionFailure.codeLabel\"", ":retryable=\"actionFailure.retryable\"", "retry-text=\"再试这一件\"", ":busy=\"disposing !== ''\"", "dense", "@retry=\"retryDisposal\"", "/>"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "notifications.js", p: "frontend/src/lib/notifications.js", a: ["* retryable 同出一把尺（R375 判据①）：吃 lib/alerts.js 那一枚 failureRetryable，本层不自判码、"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "NotificationBell.vue", p: "frontend/src/components/NotificationBell.vue", a: ["", "/** 台账里没答上的那些格——屏上要说话的就是它们。 */"] },
  { f: "frontend/src/lib/__tests__/r375-write-retryable-dict.test.js", t: "frontend/src/components/NotificationBell.vue", p: "frontend/src/components/NotificationBell.vue", a: ["})", "const payload = response && response.data", "const cells = ledgerCells(payload)"] },
  { f: "frontend/src/lib/__tests__/r399-traces-contract.test.js", t: "r316-users-contract.test.js", p: "frontend/src/lib/__tests__/r316-users-contract.test.js", a: ["function showAtRef(path) {", "let text", "try {", "text = execFileSync('git', ['show', `${REPO_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })", "} catch (cause) {", "throw new Error(`读不到真源 ${REPO_REF}:${path}（git show 失败：${cause.message}）。列账本不许降级，这里必须红，skip 等于回到装饰。`)", "}", "if (!text.trim()) throw new Error(`git show ${REPO_REF}:${path} 返回空内容，无法对账。`)", "return text.replace(/\\r\\n/g, '\\n')", "}"] },
  { f: "frontend/src/lib/__tests__/r399-traces-contract.test.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["STAGE_DESCRIPTIONS: dict[str, str] = {"] },
  { f: "frontend/src/lib/__tests__/r411-screen-never-waits-on-server.test.js", t: "lib/errcodes.test.js", p: "frontend/src/lib/errcodes.test.js", a: ["* 为什么不许 readFileSync 工作树：fe-trunk 的 app/** 停在分支点，那里的 app/agents/contracts.py", "* 只有 16 码，拿它对账等于拿过期副本对账，会稳定假绿。三个 worktree 共享同一个 object DB，", "* `git show <ref>:<path>` 读到什么与工作树新旧无关。"] },
  { f: "frontend/src/lib/__tests__/r411-screen-never-waits-on-server.test.js", t: "r368-retryable-source.test.js", p: "frontend/src/lib/__tests__/r368-retryable-source.test.js", a: ["* 读后端口径一律 git show HEAD，绝不 readFileSync 工作树的 app/**：那条教训记在", "* r316-users-contract.test.js:52-59（工作树那一版可能与判据所依据的版本不同，读它就是永远绿的假绿）。"] },
  { f: "frontend/src/lib/__tests__/r424-terminal-data-on-the-wire.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["piece_stream = _AnswerPieceStream()", "# 判据④：一轮之内所有 text 帧共用同一份缓存字段。R35 的既有裁定是\"未命中的那一"] },
  { f: "frontend/src/lib/__tests__/r424-terminal-data-on-the-wire.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["# trace 载荷）发出去的是同一份对象。算两次就是留一道口子：哪天其中一处换了口径，"] },
  { f: "frontend/src/lib/__tests__/r424-terminal-data-on-the-wire.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "def terminal_data_filename(dataset_files: list[str]) -> str:"] },
  { f: "frontend/src/lib/__tests__/r465-single-flight.test.js", t: "frontend/src/lib/health.js", p: "frontend/src/lib/health.js", a: ["*/", "import { http } from './http.js'", "", "export const MODEL_NOT_AVAILABLE = 'model_not_available'", "export const EMBEDDING_MODEL_MISSING = 'embedding_model_missing'", "export const QUEUE_UNAVAILABLE = 'queue_unavailable'", "export const USERS_STORE_NOT_PERSISTENT = 'users_store_not_persistent'", "", "const CACHE_MS = 60_000", "", "let cached = null"] },
  { f: "frontend/src/lib/__tests__/r465-single-flight.test.js", t: "App.vue", p: "frontend/src/App.vue", a: ["async function readRuntimeHealth() {", "healthRead.value = { tried: true, health: await fetchRuntimeHealth() }", "}"] },
  { f: "frontend/src/lib/__tests__/r465-single-flight.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const detail = e.detail", "const query = typeof detail === 'string' ? detail : detail?.query", "if (!query) return", "activeDataFilename.value = typeof detail === 'string'", "? activeDataFilename.value", ": detail?.filename || activeDataFilename.value", "input.value = query", "send(activeDataFilename.value)", "}", "", "", "// 面板被 v-show 常驻，切工作区不会触发卸载钩子，所以「切走时写回 scrollTop」这条路", "// 以前是断的：整页刷新后位置就丢。改成滚动本身去抖写回，与切页时机解耦。", "let scrollSaveTimer = null"] },
  { f: "frontend/src/lib/__tests__/r465-single-flight.test.js", t: "App.vue", p: "frontend/src/App.vue", a: ["async function readRuntimeHealth() {", "healthRead.value = { tried: true, health: await fetchRuntimeHealth() }", "}"] },
  { f: "frontend/src/lib/__tests__/r465-single-flight.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const detail = e.detail", "const query = typeof detail === 'string' ? detail : detail?.query", "if (!query) return", "activeDataFilename.value = typeof detail === 'string'", "? activeDataFilename.value", ": detail?.filename || activeDataFilename.value", "input.value = query", "send(activeDataFilename.value)", "}", "", "", "// 面板被 v-show 常驻，切工作区不会触发卸载钩子，所以「切走时写回 scrollTop」这条路", "// 以前是断的：整页刷新后位置就丢。改成滚动本身去抖写回，与切页时机解耦。", "let scrollSaveTimer = null"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["def attach_terminal_data_filename(payload: dict, dataset_files: list[str] | None) -> dict:"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["return attach_terminal_data_filename(payload, dataset_files)"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["return sse_event(\"done\", attach_terminal_data_filename(payload, dataset_files))"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["async def cached_response():"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["yield done_frame_for_turn(", "request_id=request_id,", "session_id=thread_id,", "full_text=cached,", "intr=None,", "visible_rows=cached_visible if manifest else None,", "sources_error=\"\" if manifest else SOURCES_ERROR_NO_MANIFEST,", ")"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "sessions.js", p: "frontend/src/lib/sessions.js", a: ["if (typeof data.data_filename === 'string') state.terminalDataFilename = data.data_filename"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["# 表里没写\"或反之，面板与流各说一套。"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["status=\"completed\",", "data={", "\"session_id\": thread_id,", "# R414(b)：这一轮的数字是从哪份数据文件算的，终态必须说得出。"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["task_id=task_id,", "sequence=sequence,", "status=\"completed\",", "data={", "\"session_id\": thread_id,", "\"sources\": visible_rows,"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["# 本单对 legacy 只加不减，旧客户端收到 done 才是既有契约。"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: [") -> tuple[dict, AuthorizationDecision]:"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["status=\"running\",", "data=data,"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "sessions.js", p: "frontend/src/lib/sessions.js", a: ["if (typeof data.data_filename === 'string') state.terminalDataFilename = data.data_filename"] },
  { f: "frontend/src/lib/__tests__/r512-legacy-done-adopts-data-filename.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["payload = {", "\"type\": \"done\",", "\"terminal_state\": terminal_state,", "\"answer_present\": bool(answer_present),", "\"sources_present\": bool(sources_present),", "\"sources\": [row for row in (sources or []) if isinstance(row, dict)],", "\"sources_error\": str(sources_error or \"\"),", "\"usage\": usage,", "\"approval\": approval,", "}"] },
  { f: "frontend/src/lib/alerts.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),"] },
  { f: "frontend/src/lib/alerts.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"manager\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS, ACTION_APPROVE}),"] },
  { f: "frontend/src/lib/alerts.js", t: "app/api/v1/alerts.py", p: "app/api/v1/alerts.py", a: ["return owner", "return _joined_departments(_principal_departments(principal))", "", "", "def _dataset_department_index() -> dict[str, str]:", "\"\"\"登记表里每份数据的部门（filename -> \"a,b\"）；登记不可用时退回空表，不猜。\"\"\"", "from app.storage.datasets import dataset_registry", "", "try:", "records = list(dataset_registry.active_records())"] },
  { f: "frontend/src/lib/alerts.js", t: "app/api/v1/alerts.py", p: "app/api/v1/alerts.py", a: ["return departments", "return _split_departments(row.get(\"department\"))", "", "", "def alert_row_visible(principal, row) -> bool:", "\"\"\"行级判定：这一条告警是不是他部门的。过了资源级那道门不等于每一条都归他读。", "", "无归属行（历史行，以及既有用例依赖的 ``{\"id\": 1, \"read\": False}`` 那种形状）既不认作任何"] },
  { f: "frontend/src/lib/alerts.js", t: "app/api/v1/alerts.py", p: "app/api/v1/alerts.py", a: ["判的两件事都是本件既有的读数，一枚都不新造、也不另算一遍: 库在不在取", "``_database_available()``（本模块唯一那枚探针），是不是生产取", "``_is_production_environment()``（就在上面）。两支同时成立才拒，回的必须是仓里", "已有的那一码 —— ``app/api/v1/dashboard.py:143``、``app/api/v1/notifications.py:161``、", "``app/api/v1/chat.py:3037`` 三处出口都是 503 ``storage_unavailable``，本单零新增错误码。", "", "为什么不许退成「200 + 空数组」: ``_MEM_ALERTS`` 是客户机上永远为空的那张进程内表，", "于是每一次存储拒答都长成「这家公司现在没有异常」的样子，而那一屏照字面画的就是这句", "话（``frontend/src/lib/alerts.js`` 的 ALERTS_EMPTY_TITLE）。读侧不许把存储拒答翻译成", "空集 —— 与 ``/users``（R356）、``/dashboard``（R332）、通知（R299）是同一条裁定，", "告警是这四条里最后还在沉默回空的那一条。", "", "为什么开发态一个字都不改: 裸机与开发环境里内存 store 今天就是合法后端（``_ensure()``", "还替它就地建表），那一支的回包形状、行数、排序逐字保持。本单分开的是两张脸，不是一律", "503 —— 把开发态一起打死同样是在说假话，只不过反着说。", "", "调用点一律排在授权之后（``_require_alert_management``）、排在 ``_ensure()`` 与任何一次"] },
  { f: "frontend/src/lib/alerts.js", t: "app/api/v1/alerts.py", p: "app/api/v1/alerts.py", a: ["path", "for path in sorted(root.iterdir())", "if path.is_file()", "and not path.name.startswith(\".\")", "and path.suffix.lower() in _data_file_extensions()", "]", "", "", "def _permitted_dataset_files(principal, root: Path) -> list[Path]:", "\"\"\"带 Principal 的巡检：限定在该 Principal 有权 analyze 的 Dataset 集合内。\"\"\""] },
  { f: "frontend/src/lib/alerts.js", t: "app/api/v1/alerts.py", p: "app/api/v1/alerts.py", a: ["ALERT_ACTION_CLOSE = \"close\"", "ALERT_ACTION_ASSIGN = \"assign\"", "ALERT_ACTIONS: tuple[str, ...] = (ALERT_ACTION_ACK, ALERT_ACTION_CLOSE, ALERT_ACTION_ASSIGN)", "", "#: 每一枚动作唯一的合法形状：``(允许出发的当前状态, 写入后的状态)``，目标为 ``None`` 即状态不动。", "#: assign 有意不动状态：派出去说的是「现在归他」，不是「有人决定了」，接手的本人还得自己确认一次；", "#: 已关闭那一枚不再改派，那等于替别人重开一笔已经销掉的账。", "ALERT_DISPOSAL_RULES: dict[str, tuple[frozenset[str], str | None]] = {", "ALERT_ACTION_ACK: (", "frozenset({ALERT_STATUS_OPEN}),", "ALERT_STATUS_ACKNOWLEDGED,", "),"] },
  { f: "frontend/src/lib/alerts.js", t: "app/api/v1/alerts.py", p: "app/api/v1/alerts.py", a: ["就是改别人的账。这里也不新抛第二枚 503：它把结论交给 ``_require_ready_store``，", "全模块那道存储门仍然只有一扇。"] },
  { f: "frontend/src/lib/artifacts.test.js", t: "artifacts.js", p: "frontend/src/lib/artifacts.js", a: ["const target = resolveArtifactUrl(url)", "if (!target) {", "const error = new Error('缺少图表地址')", "error.code = 'missing_url'"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["@router.get(\"/audit/events\", responses=_ERROR_RESPONSES)"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/common/audit.py", p: "app/common/audit.py", a: ["def get_audit_events("] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["filters = {", "key: str(value or \"\").strip()", "for key, value in ((\"username\", username), (\"action\", action), (\"outcome\", outcome))", "if str(value or \"\").strip()", "}"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"event_count\": len(page),", "\"events_total\": len(matching),"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"events_total\": len(matching),"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"recorded_total\": len(events),"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"truncated\": len(matching) > len(page),"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"limits\": {", "\"default_limit\": DEFAULT_AUDIT_EVENTS,", "\"max_limit\": MAX_AUDIT_EVENTS,", "\"applied_limit\": applied_limit,", "\"requested_limit\": limit,", "\"clamped\": limit_clamped,", "},"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"order\": \"newest_first\","] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/common/audit.py", p: "app/common/audit.py", a: ["event: dict[str, Any] = {", "\"event_id\": f\"aud-{uuid4().hex}\",", "\"timestamp\": \"\",", "\"created_at\": \"\",", "\"username\": str(getattr(principal, \"username\", \"\") or \"anonymous\"),", "\"role\": str(getattr(principal, \"role\", \"\") or \"unknown\"),", "\"owner_id\": str(getattr(principal, \"user_id\", \"\") or \"\"),", "\"auth_source\": str(getattr(principal, \"auth_source\", \"\") or \"\"),", "\"actor_clearance\": _truncate(getattr(principal, \"clearance\", None)),", "\"actor_departments\": sorted(value for value in departments if value),", "\"action\": str(action or \"\"),", "\"resource\": str(resource or \"\"),", "\"outcome\": str(outcome or \"\"),", "\"reason\": str(reason or \"\"),", "\"request_id\": _resolve_request_id(principal, request_id),", "\"resource_scope\": scope_projection,", "\"resource_scope_source\": scope_source,", "\"policy_version\": version,", "\"policy_version_source\": version_source,", "\"before_summary\": _summarize(before_summary),", "\"after_summary\": _summarize(after_summary),", "\"retention_days\": resolved_retention,", "\"expires_at\": \"\",", "\"persisted\": False,", "\"storage_mode\": MEMORY_ONLY,", "}"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["@router.get(\"/audit/events\", responses=_ERROR_RESPONSES)"] },
  { f: "frontend/src/lib/auditEvents.js", t: "observability.py", p: "app/api/v1/observability.py", a: ["),", "instrument_paths=(\"scripts/eval_transport_ask_v2.py\", \"scripts/eval_frame_caliber_readout.py\"),"] },
  { f: "frontend/src/lib/auditEvents.js", t: "observability.py", p: "app/api/v1/observability.py", a: ["roster_cell=\"p95_wall_ms\",", "window_admissible=True,", "reader_landed=False,", "reader_path=_A_READER,", "prerequisite=_A_PREREQ,", "reference_readout=\"docs/testing/sidecar-run9.jsonl\",", "reference_field=\"wall_ms\",", "),", "(\"report\", \"end_to_end_p95_ms\"): SloSlotCaliber("] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/common/audit.py", p: "app/common/audit.py", a: ["event: dict[str, Any] = {", "\"event_id\": f\"aud-{uuid4().hex}\",", "\"timestamp\": \"\",", "\"created_at\": \"\",", "\"username\": str(getattr(principal, \"username\", \"\") or \"anonymous\"),", "\"role\": str(getattr(principal, \"role\", \"\") or \"unknown\"),", "\"owner_id\": str(getattr(principal, \"user_id\", \"\") or \"\"),", "\"auth_source\": str(getattr(principal, \"auth_source\", \"\") or \"\"),", "\"actor_clearance\": _truncate(getattr(principal, \"clearance\", None)),", "\"actor_departments\": sorted(value for value in departments if value),", "\"action\": str(action or \"\"),", "\"resource\": str(resource or \"\"),", "\"outcome\": str(outcome or \"\"),", "\"reason\": str(reason or \"\"),", "\"request_id\": _resolve_request_id(principal, request_id),", "\"resource_scope\": scope_projection,", "\"resource_scope_source\": scope_source,", "\"policy_version\": version,", "\"policy_version_source\": version_source,", "\"before_summary\": _summarize(before_summary),", "\"after_summary\": _summarize(after_summary),", "\"retention_days\": resolved_retention,", "\"expires_at\": \"\",", "\"persisted\": False,", "\"storage_mode\": MEMORY_ONLY,", "}"] },
  { f: "frontend/src/lib/auditEvents.js", t: "app/common/audit.py", p: "app/common/audit.py", a: ["event: dict[str, Any] = {", "\"event_id\": f\"aud-{uuid4().hex}\",", "\"timestamp\": \"\",", "\"created_at\": \"\",", "\"username\": str(getattr(principal, \"username\", \"\") or \"anonymous\"),", "\"role\": str(getattr(principal, \"role\", \"\") or \"unknown\"),", "\"owner_id\": str(getattr(principal, \"user_id\", \"\") or \"\"),", "\"auth_source\": str(getattr(principal, \"auth_source\", \"\") or \"\"),", "\"actor_clearance\": _truncate(getattr(principal, \"clearance\", None)),", "\"actor_departments\": sorted(value for value in departments if value),", "\"action\": str(action or \"\"),", "\"resource\": str(resource or \"\"),", "\"outcome\": str(outcome or \"\"),", "\"reason\": str(reason or \"\"),", "\"request_id\": _resolve_request_id(principal, request_id),", "\"resource_scope\": scope_projection,", "\"resource_scope_source\": scope_source,", "\"policy_version\": version,", "\"policy_version_source\": version_source,", "\"before_summary\": _summarize(before_summary),", "\"after_summary\": _summarize(after_summary),", "\"retention_days\": resolved_retention,", "\"expires_at\": \"\",", "\"persisted\": False,", "\"storage_mode\": MEMORY_ONLY,", "}"] },
  { f: "frontend/src/lib/dashboard.js", t: "app/api/v1/dashboard.py", p: "app/api/v1/dashboard.py", a: ["alerts = _alert_counts(request)", "if alerts is not None:", "payload[\"alerts\"] = alerts"] },
  { f: "frontend/src/lib/dashboard.js", t: "dashboard.py", p: "app/api/v1/dashboard.py", a: ["principal = alerts_api._require_alert_management(request)"] },
  { f: "frontend/src/lib/dashboard.js", t: "alerts.py", p: "app/api/v1/alerts.py", a: ["principal = _require_alert_management(request, ALERT_LEDGER_RESOURCE)", "_require_ready_store(\"list_alerts\")"] },
  { f: "frontend/src/lib/dashboard.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),"] },
  { f: "frontend/src/lib/dashboard.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["## The overview page grows a period: `GET /api/v1/dashboard/trend` (2026-09-26, R332)"] },
  { f: "frontend/src/lib/dashboard.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["**A caller without alert rights gets no `alerts` and no `alerts_open` in any bucket** -- the keys are absent,"] },
  { f: "frontend/src/lib/dashboard.js", t: "docs/api/contract-v1.md", p: "docs/api/contract-v1.md", a: ["**Series totals are not the tile totals.** `sum(bucket.documents)` counts only rows created inside the", "window, while `/summary` counts every visible row; on a corpus older than `buckets` periods the series"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise HTTPException(", "status_code=403,", "detail={", "\"code\": DEPARTMENT_SELF_REPORT_DENIED,", "\"message\": \"department must match the authenticated principal\",", "},"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["raise HTTPException(status_code=401, detail=\"用户名或密码错误\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["username: str", "password: str", "", "", "class CreateUserRequest(BaseModel):", "username: str", "password: str", "role: str = \"staff\"", "department: str = \"\"", "", "", "class ChangePasswordRequest(BaseModel):", "username: str", "old_password: str"] },
  { f: "frontend/src/lib/errcodes.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["const hit = payload && typeof payload === 'object' && 'cached' in payload"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/contracts.py", p: "app/agents/contracts.py", a: ["\"\"\"", "return max(0, self.prompt_room_tokens - max(0, int(prefix_tokens)))", "", "def prefill_seconds(self, prompt_tokens: int | None = None) -> float:", "tokens = self.input_budget_tokens if prompt_tokens is None else max(0, int(prompt_tokens))", "return tokens / max(0.1, float(self.prefill_tokens_per_second))"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["# （判据二）。后端只认调用方显式写进请求里的字符串，markers 由调用方自己判。"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["_RETRIABLE_CODES = {\"model_unavailable\", \"retrieval_unavailable\", \"task_timeout\", \"rate_limited\", \"queue_unavailable\"}"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["_RETRIABLE_CODES = {\"model_unavailable\", \"retrieval_unavailable\", \"task_timeout\", \"rate_limited\", \"queue_unavailable\"}"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["retryable=error_code in _RETRIABLE_CODES,", "details={\"worker\": worker, \"status\": status},"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["retryable=error_code in _RETRIABLE_CODES,", "details={\"status\": status},"] },
  { f: "frontend/src/lib/errcodes.js", t: "data.py", p: "app/api/v1/data.py", a: ["#: 收口名单不是另一份手抄：它就是 app/tools/excel.py 那张「扩展名 -> 读引擎」的声明表"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: [")", "continue"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["logger.exception(f\"[Data] dataset file could not be removed: {record.filename}\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["now = datetime.now(_tz).isoformat()", "if not _session_database_available():", "session = _ensure_session(session_id)", "_MEM_SESSION_MESSAGES.setdefault(session_id, []).append(", "{\"role\": role, \"content\": content, \"steps\": steps or [], \"created_at\": now}", ")", "if role == \"user\" and not session[\"title\"]:", "session[\"title\"] = content[:30]", "session[\"updated_at\"] = now", "return", "with _sess_conn() as conn:", "conn.execute(", "\"INSERT INTO session_messages (session_id, role, content, steps, created_at) VALUES (%s, %s, %s, %s, %s)\",", "(session_id, role, content, json.dumps(steps or [], ensure_ascii=False), now),", ")", "if role == \"user\":", "title = content[:30]"] },
  { f: "frontend/src/lib/errcodes.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["* 同样没带过这三枚，那样推会把它们一一标错。"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/contracts.py", p: "app/agents/contracts.py", a: [")", "return needed <= float(self.timeout_ceiling_seconds) + 1e-9", "", "def context_window_code(self, prompt_tokens: int | None) -> str | None:", "\"\"\"Stable code for \"this call cannot fit n_ctx\", or None when it can.", "", "``None`` also means \"prompt size unknown\", which is why the guard judges a number", "rather than guessing at a message list.", "", "R463: the judgement is ``prompt <= prompt_room_tokens``, the same number the packing"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/tools.py", p: "app/agents/tools.py", a: [") from exc", ""] },
  { f: "frontend/src/lib/errcodes.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["_RETRIABLE_CODES = {\"model_unavailable\", \"retrieval_unavailable\", \"task_timeout\", \"rate_limited\", \"queue_unavailable\"}"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/intelligence.py", p: "app/api/v1/intelligence.py", a: ["# the deployment, which is exactly the fact 409 carries. Hiding that behind \"not"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/open_platform.py", p: "app/api/v1/open_platform.py", a: ["# open_platform_unconfigured. Not 503: \"temporarily unavailable, retry later\" is"] },
  { f: "frontend/src/lib/errcodes.js", t: "alerts.py", p: "app/api/v1/alerts.py", a: ["", "判的两件事都是本件既有的读数，一枚都不新造、也不另算一遍: 库在不在取"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/artifacts.py", p: "app/api/v1/artifacts.py", a: ["raise HTTPException(status_code=403, detail=decision.reason_code)"] },
  { f: "frontend/src/lib/errcodes.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["", "旧 ``/chat`` 端点把 ``retriever.search`` 的返回字典直接喂给 ``scope.allows``；Agent 路径里"] },
  { f: "frontend/src/lib/errcodes.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["已经写死的纪律：本轮没有检索过的文档不允许凭着答案文本出现在来源里。"] },
  { f: "frontend/src/lib/errcodes.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["return {", "\"username\": principal.username,"] },
  { f: "frontend/src/lib/errcodes.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["# 有声明在上一条就 400 了，所以这里 declared 必为空串，只发 x-lane-source 一枚。"] },
  { f: "frontend/src/lib/errcodes.js", t: "data.py", p: "app/api/v1/data.py", a: ["", "R337 gives one more shape that same answer: a record object carrying no owner column at all (a"] },
  { f: "frontend/src/lib/errcodes.js", t: "data.py", p: "app/api/v1/data.py", a: ["raise HTTPException(status_code=403, detail=OWNER_SCOPE_REQUIRED) from exc"] },
  { f: "frontend/src/lib/errcodes.js", t: "data.py", p: "app/api/v1/data.py", a: ["try:", "df = await asyncio.to_thread(load_excel, str(path))"] },
  { f: "frontend/src/lib/errcodes.js", t: "intelligence.py", p: "app/api/v1/intelligence.py", a: ["class RelationRequest(BaseModel):"] },
  { f: "frontend/src/lib/errcodes.js", t: "policy.py", p: "app/common/policy.py", a: ["return _decision(False, \"authentication_required\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "policy.py", p: "app/common/policy.py", a: ["return _decision(False, \"permission_denied\", (\"department_scope_mismatch\",))"] },
  { f: "frontend/src/lib/errcodes.js", t: "policy.py", p: "app/common/policy.py", a: ["return _decision(False, \"clearance_insufficient\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "policy.py", p: "app/common/policy.py", a: ["return _decision(False, \"resource_scope_missing\")", "if \"department\" not in resource and \"department_ids\" not in resource:"] },
  { f: "frontend/src/lib/errcodes.js", t: "policy.py", p: "app/common/policy.py", a: ["return _decision(False, \"resource_scope_missing\")", "if not resource_departments.intersection(principal_departments):"] },
  { f: "frontend/src/lib/errcodes.js", t: "policy.py", p: "app/common/policy.py", a: ["return _decision(False, \"resource_scope_invalid\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["DEPARTMENT_SELF_REPORT_DENIED = \"department_override_denied\""] },
  { f: "frontend/src/lib/errcodes.js", t: "ApprovalPanel.vue", p: "frontend/src/components/ApprovalPanel.vue", a: ["degraded.value = false", "loading.value = false"] },
  { f: "frontend/src/lib/errcodes.js", t: "lib/http.js", p: "frontend/src/lib/http.js", a: ["return errorCodeOf(err) === PERMISSION_DENIED"] },
  { f: "frontend/src/lib/errcodes.js", t: "authorization.py", p: "app/common/authorization.py", a: ["# A caller-named department that is not the caller's own is a refused request, not a", "# scope to compute with. Kept as one constant so the audit trail and the response", "# cannot drift apart over the name of the same judgment."] },
  { f: "frontend/src/lib/errcodes.js", t: "authorization.py", p: "app/common/authorization.py", a: ["claimed = str(claimed_department or \"\").strip()", "if not claimed or claimed in own:", "return str(principal.department or \"\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["if not _session_database_available():", "session = _ensure_session(session_id)"] },
  { f: "frontend/src/lib/errcodes.js", t: "lib/sessions.js", p: "frontend/src/lib/sessions.js", a: ["* 同样没带过这三枚，那样推会把它们一一标错。", "*/", "export function cacheFromFrame(payload) {", "const hit = payload && typeof payload === 'object' && 'cached' in payload", "return {"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["raise HTTPException(status_code=401, detail=\"用户名或密码错误\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["@router.delete(\"/users/{user_id}\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["principal,", "ACTION_MANAGE_USERS,", "\"failure\","] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["", "", "@router.post(\"/sso/login\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["async def sso_login(request: Request):"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["async def update_my_profile(data: UpdateProfileRequest, request: Request):"] },
  { f: "frontend/src/lib/errcodes.js", t: "alerts.py", p: "app/api/v1/alerts.py", a: ["raise HTTPException(status_code=400, detail=f\"非法操作符: {data.op}\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/common/auth.py", p: "app/common/auth.py", a: ["return False, \"用户名和密码不能为空\""] },
  { f: "frontend/src/lib/errcodes.js", t: "common/authorization.py", p: "app/common/authorization.py", a: ["raise PermissionError(f\"权限不足: {action} ({decision.reason_code})\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "frontend/src/lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["export const FALLBACK_MESSAGE = '操作没有完成，请稍后重试。'"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["if not _session_database_available():", "session = _ensure_session(session_id)"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["raise HTTPException(status_code=401, detail=\"用户名或密码错误\")"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise HTTPException(", "status_code=403,", "detail={", "\"code\": DEPARTMENT_SELF_REPORT_DENIED,", "\"message\": \"department must match the authenticated principal\",", "},"] },
  { f: "frontend/src/lib/errcodes.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["title = content[:30]"] },
  { f: "frontend/src/lib/errcodes.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["\"classification\": version.get(\"classification\"),"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["request.session_id,", "approved=request.approved,"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/artifacts.py", p: "app/api/v1/artifacts.py", a: ["raise HTTPException(status_code=403, detail=decision.reason_code)"] },
  { f: "frontend/src/lib/errcodes.js", t: "intelligence.py", p: "app/api/v1/intelligence.py", a: ["raise HTTPException(status_code=403, detail=decision.reason_code)"] },
  { f: "frontend/src/lib/errcodes.js", t: "alerts.py", p: "app/api/v1/alerts.py", a: ["", "", "def _joined_departments(departments) -> str:"] },
  { f: "frontend/src/lib/errcodes.js", t: "data.py", p: "app/api/v1/data.py", a: ["return str(value)"] },
  { f: "frontend/src/lib/errcodes.js", t: "app/api/v1/data.py", p: "app/api/v1/data.py", a: ["\"classification\": record.classification,", "\"size_bytes\": size_before,"] },
  { f: "frontend/src/lib/errcodes.js", t: "feedback.py", p: "app/api/v1/feedback.py", a: ["raise HTTPException(status_code=403, detail=reason_code)", "record_audit(principal, ACTION_VIEW, \"success\", resource=filename, reason=reason_code)"] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"app/common/stage_timing.py\","] },
  { f: "frontend/src/lib/evaluations.js", t: "observability.py", p: "app/api/v1/observability.py", a: ["\"runs_on_request\": False,"] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["raw_readout=_A_RAW,", "raw_field=_A_FIELD,", "denominator=_A_DENOM,", "roster_cell=\"p95_wall_ms\",", "window_admissible=True,", "reader_landed=False,", "reader_path=_A_READER,", "prerequisite=_A_PREREQ,", "reference_readout=\"docs/testing/sidecar-run9.jsonl\",", "reference_field=\"wall_ms\",", "),", "(\"analysis\", \"end_to_end_p95_ms\"): SloSlotCaliber("] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["window_admissible=True,", "reader_landed=False,", "reader_path=_A_READER,", "prerequisite=_A_PREREQ,", "reference_readout=\"docs/testing/sidecar-run9.jsonl\",", "reference_field=\"wall_ms\",", "),", "(\"analysis\", \"end_to_end_p95_ms\"): SloSlotCaliber("] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["EVALUATION_COMMAND_TEMPLATE = ("] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"再谈落数\""] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"status\": \"unreadable\","] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["record[\"status\"] = \"too_large\""] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["record[\"status\"] = \"ok\""] },
  { f: "frontend/src/lib/evaluations.js", t: "observability.py", p: "app/api/v1/observability.py", a: ["_A_RAW = \"docs/testing/sidecar-{window}.jsonl（下一扇 = docs/testing/sidecar-run10.jsonl）\""] },
  { f: "frontend/src/lib/evaluations.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"app/common/stage_timing.py\","] },
  { f: "frontend/src/lib/evaluations.js", t: "observability.py", p: "app/api/v1/observability.py", a: ["def _clamped("] },
  { f: "frontend/src/lib/health.js", t: "App.vue", p: "frontend/src/App.vue", a: ["healthRead.value = { tried: true, health: await fetchRuntimeHealth() }"] },
  { f: "frontend/src/lib/health.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["const detail = e.detail"] },
  { f: "frontend/src/lib/http.js", t: "app/common/policy.py", p: "app/common/policy.py", a: ["if action not in permissions:", "return _decision(False, \"permission_denied\")"] },
  { f: "frontend/src/lib/http.js", t: "errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["},", "dataset_filename_conflict: { message: '已存在同名数据文件，请重命名或先删除旧的。', retryable: false },"] },
  { f: "frontend/src/lib/http.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["raise HTTPException(", "status_code=403,", "detail={", "\"code\": DEPARTMENT_SELF_REPORT_DENIED,", "\"message\": \"department must match the authenticated principal\",", "},"] },
  { f: "frontend/src/lib/http.test.js", t: "policy.py", p: "app/common/policy.py", a: ["if resource is None:", "if require_resource_scope:", "return _decision(False, \"resource_scope_missing\")", "return _decision(True, \"permission_granted\", (\"action_permission\",))"] },
  { f: "frontend/src/lib/http.test.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["", "", "def _collect_document_sources(agent_results: dict, sink: dict) -> None:"] },
  { f: "frontend/src/lib/no-bare-code.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["if not _session_database_available():", "session = _ensure_session(session_id)"] },
  { f: "frontend/src/lib/notifications.js", t: "app/api/v1/notifications.py", p: "app/api/v1/notifications.py", a: ["@router.get('/notifications')"] },
  { f: "frontend/src/lib/notifications.js", t: "app/api/v1/notifications.py", p: "app/api/v1/notifications.py", a: ["@router.post('/notifications/read')"] },
  { f: "frontend/src/lib/notifications.js", t: "app/api/v1/notifications.py", p: "app/api/v1/notifications.py", a: ["@router.post('/notifications/dismiss')"] },
  { f: "frontend/src/lib/provenance.js", t: "app/rag/filters.py", p: "app/rag/filters.py", a: ["", "", "def _resolve_document_retrieval_scope(principal: Principal | None) -> DocumentRetrievalScope:"] },
  { f: "frontend/src/lib/provenance.js", t: "app/rag/filters.py", p: "app/rag/filters.py", a: [")", "if principal.clearance <= 0:"] },
  { f: "frontend/src/lib/provenance.js", t: "app/documents/catalog.py", p: "app/documents/catalog.py", a: ["OWNERSHIP_LEGACY = \"legacy\""] },
  { f: "frontend/src/lib/provenance.js", t: "app/documents/catalog.py", p: "app/documents/catalog.py", a: ["``int()`` inside ``_local_version_rows``. So \"which version is current\" is a comparison over"] },
  { f: "frontend/src/lib/provenance.js", t: "app/documents/catalog.py", p: "app/documents/catalog.py", a: ["directory = Path(DOCUMENTS_DIR)"] },
  { f: "frontend/src/lib/provenance.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["\"复核\","] },
  { f: "frontend/src/lib/provenance.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["\"score_type\": \"rerank\" if score is not None else None,"] },
  { f: "frontend/src/lib/provenance.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["REPORT_LANE_REASON = \"report_lane\"", "", "", "def _report_lane_via_queue_enabled() -> bool:", "\"\"\"默认关：没配环境变量的现网，不会因为本单多走一条道。\"\"\""] },
  { f: "frontend/src/lib/provenance.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "``omitted_groups`` 是**没逐条列出的**类数（``len(groups) - len(shown_groups)``），不是画下来的"] },
  { f: "frontend/src/lib/provenance.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["error: '',"] },
  { f: "frontend/src/lib/provenance.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["data={", "\"session_id\": thread_id,", "\"error_code\": \"no_answer_produced\",", "\"worker_count\": len(latest_worker_results),", "},", ")", "sequence += 1"] },
  { f: "frontend/src/lib/r150-event-claims.test.js", t: "app/rag/indexing.py", p: "app/rag/indexing.py", a: ["_MIRROR_COLUMNS = {"] },
  { f: "frontend/src/lib/r208-alias-coverage.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["// 名单逐格说（lib/health.js 一族一句，六族六张脸）。这里只做挂载，本面板不当第二套判断。"] },
  { f: "frontend/src/lib/r208-alias-coverage.test.js", t: "errcodes.test.js", p: "frontend/src/lib/errcodes.test.js", a: ["function showAtRef(path) {", "let text", "try {", "text = execFileSync('git', ['show', `${CONTRACT_REF}:${path}`], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })", "} catch (cause) {", "throw new Error(", "`读不到真源 ${CONTRACT_REF}:${path}（git show 失败：${cause.message}）。` +", "'码表对账不许降级：这里必须红，skip 等于回到装饰。',", ")", "}", "if (typeof text !== 'string' || !text.trim()) {", "throw new Error(`git show ${CONTRACT_REF}:${path} 返回空内容，无法对账。`)", "}", "return text", "}"] },
  { f: "frontend/src/lib/r208-dictionary-voice.test.js", t: "lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["*   列 C  前端 ERROR_CODES。"] },
  { f: "frontend/src/lib/r208-dictionary-voice.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["}", "", "onMounted(() => {"] },
  { f: "frontend/src/lib/r208-dictionary-voice.test.js", t: "frontend/src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["// 名单逐格说（lib/health.js 一族一句，六族六张脸）。这里只做挂载，本面板不当第二套判断。"] },
  { f: "frontend/src/lib/sessions-error-text.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "def _session_principal_or_error(request: FastAPIRequest):"] },
  { f: "frontend/src/lib/sessions-error-text.test.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["return", "conn.execute(\"\"\""] },
  { f: "frontend/src/lib/sessions.js", t: "lib/sessions-error-text.test.js", p: "frontend/src/lib/sessions-error-text.test.js", a: ["expect(s).toContain(\"import { formatError } from './errcodes'\")"] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["document_terms = (", "\"制度\",", "\"流程\",", "\"报销\",", "\"标准\",", "\"审批\",", "\"规定\",", "\"政策\",", "\"凭证\",", "\"发票\",", "\"复核\",", "\"材料\",", "\"依据\",", "\"谁承担\",", ")", "data_terms = ("] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["session_id,", "owner_user_id,", "list(intr.get(\"pending\") or []),", "request_id=request_id,", "trace_id=trace_id,", "task_id=task_id,", "declared_lane=declared_lane,", ")", "except Exception:", "logger.exception(", "f\"[R37][HITL] 后台挂起待办没能写入 session={session_id}，审批面板可能少一条待办\"", ")", "return False", "return True", "", ""] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["\"材料\","] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["\"source_id\": str(evidence.get(\"source_id\") or source),", "\"chunk_index\": locator.get(\"chunk_index\"),", "\"score\": evidence.get(\"score\"),", "\"score_type\": evidence.get(\"score_type\"),", "# R154 判据①：命中句从证据袋原样搬过来。它是 ``app/agents/evidence.py", "# ::record_document_hits`` 在工具边界上记下的那一段正文（400 字以内），不是从回答", "# 文本里反推的。这一格骑在行本身的放行结论上：行过了 ``scope.allows`` 才谈得上看它", "# 的摘录，这里不新增任何放行分支。", "\"excerpt\": str(evidence.get(\"excerpt\") or \"\"),", "\"document_version_id\": evidence.get(\"document_version_id\"),", "\"index_version_id\": evidence.get(\"index_version_id\"),", "\"content_sha256\": metadata.get(\"content_sha256\"),"] },
  { f: "frontend/src/lib/sessions.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["\"excerpt\": str(hit.get(\"content\") or \"\")[:_EXCERPT_LIMIT],"] },
  { f: "frontend/src/lib/sessions.js", t: "app/rag/indexing.py", p: "app/rag/indexing.py", a: ["_MIRROR_COLUMNS = {"] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["REPORT_LANE_REASON = \"report_lane\"", "", "", "def _report_lane_via_queue_enabled() -> bool:", "\"\"\"默认关：没配环境变量的现网，不会因为本单多走一条道。\"\"\"", "return os.getenv(REPORT_LANE_QUEUE_ENV, \"\").strip().lower() in REPORT_LANE_ON_VALUES", "", "", "def _queue_lane(request) -> str:", "\"\"\"档位判别：只读请求字段，纯规则，零模型往返。"] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["_MEASURE_WORDS = \"份张篇页条笔位名种\"", "#: \"这个月\"\"那周\"是时间状语；\"这个标准\"才是指代 —— 哪个标准得由上文指出", "_TEMPORAL_NOUNS = \"月年周日次号期季\"", "_FOLLOWUP_PREFIXES = (", "\"那\", \"它\", \"他\", \"她\", \"这\", \"换\", \"改成\", \"如果\", \"要是\", \"请给\", \"只给\",", ")", "#: 要求改判／重算：换掉上一轮里的某个成分再走一遍", "_REWRITE_MARKERS = (\"换成\", \"改成\", \"改为\", \"调成\", \"再算\", \"重新算\", \"换个\", \"换种\")", "#: 指令下在\"上一答怎么说\"上，而不是下在新事实上", "_FORM_MARKERS = (\"更简单\", \"简单点\", \"说得更\", \"一点\", \"通俗\", \"大白话\", \"总结\", \"不要引用\")", "#: 拿上一答当对照对象"] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["def _queue_lane(request) -> str:"] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "def _session_principal_or_error(request: FastAPIRequest):"] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["return", "conn.execute(\"\"\""] },
  { f: "frontend/src/lib/sessions.js", t: "test_legacy_chat_retrieval_scope.py", p: "tests/test_legacy_chat_retrieval_scope.py", a: ["assert \"[错误]\" in response.text"] },
  { f: "frontend/src/lib/sessions.js", t: "chat.py", p: "app/api/v1/chat.py", a: ["def _queue_lane(request) -> str:"] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["", "", "# ==================== Pydantic ===================="] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["\"\"\"Build the Agent runtime context that grants a request its authorization scope.\"\"\""] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["record_audit(principal, action, \"denied\", filename, decision.reason_code)"] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["if not session_registry.is_owned_by(session_id, principal):"] },
  { f: "frontend/src/lib/sessions.js", t: "app/api/v1/chat.py", p: "app/api/v1/chat.py", a: ["# 串味：查缓存用的是 _rewrite_followup 把指代补全之后的问题文本，追问会改写成另一个键。"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["and self.instrument"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"the only tier with a second addressable surface: /ask answers it and \""] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["MIN_SLO_SAMPLES = 100"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"export leg is not a ledger stage at all\""] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["population=(", "\"one request in this lane that reached a terminal event, including \"", "\"failed and cancelled ones\"", "),", "source=SLO_SOURCE_LEDGER,", "blockers=(\"lane_attribution_absent\",),", "),", "SloMetric(", "name=\"progress_interval_p95_ms\","] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"one request in this lane that reached a terminal event, including \"", "\"failed and cancelled ones\"", "),", "source=SLO_SOURCE_LEDGER,", "blockers=(\"lane_attribution_absent\",),", "),", "SloMetric(", "name=\"progress_interval_p95_ms\","] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["#: Readout verdicts. ``insufficient_samples`` exists because the alternative is a lie:"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["SLO_TARGET_PENDING = \"awaiting_real_samples\""] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["#: Every target slot in the contract starts empty on purpose. 乙半 fills it from the D14甲"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["),", "),", "SloTier(", "lane=LANE_REPORT,"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["),", "source=SLO_SOURCE_LEDGER,", "blockers=(\"lane_attribution_absent\", \"export_leg_has_no_stage\"),"] },
  { f: "frontend/src/lib/slo.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["and self.instrument"] },
  { f: "frontend/src/lib/traces.js", t: "docs/version-roadmap-and-next-week-plan-2026-09-22.md", p: "docs/version-roadmap-and-next-week-plan-2026-09-22.md", a: ["- 管理员可以查看一次运行的关键 Trace。"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"server_verified\": False,"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"limits\": {", "\"default_top_k\": DEFAULT_TOP_K,"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["limit, default=MAX_TRACE_EVENTS, maximum=MAX_TRACE_EVENTS"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["f\"trace replay failed: {type(exc).__name__}\","] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["details={\"stage\": \"trace_store\"},", ")", "events = list(events or [])"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: [")", "events = list(events or [])"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["_fail(", "404,", "\"resource_not_found\",", "f\"No trace events are recorded for trace_id {trace_id!r}.\","] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["", "normalized = str(trace_id or \"\").strip()"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["per_request[trace_id] = {"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["\"requests\": len(per_request),"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["in-process rolling window is reported, the same block ``/health/details`` carries."] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"event_count\": len(page),", "\"events_total\": len(events),"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["report[\"enabled\"] = stage_timing_enabled()"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["raw = os.getenv(\"STAGE_TIMING_ENABLED\")"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"admin\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"auditor\": frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT}),"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"manager\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS, ACTION_APPROVE}),"] },
  { f: "frontend/src/lib/traces.js", t: "lib/alerts.js", p: "frontend/src/lib/alerts.js", a: ["export const UNRECORDED = '未记录'"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["_fail(", "404,", "\"resource_not_found\",", "f\"No trace events are recorded for trace_id {trace_id!r}.\","] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"server_verified\": False,"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["", "normalized = str(trace_id or \"\").strip()"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["in-process rolling window is reported, the same block ``/health/details`` carries."] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["per_request[trace_id] = {"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["\"segment_sum_ms\": segment_sum_ms,"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["CANONICAL_STAGES: tuple[str, ...] = (\"classify\", \"rewrite\", \"retrieve\", \"generate\", \"reflect\")"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["500,", "\"internal_error\",", "f\"trace replay failed: {type(exc).__name__}\",", "details={\"stage\": \"trace_store\"},", ")", "events = list(events or [])", "page = events[:applied_limit]", "if not page:", "_fail(", "404,", "\"resource_not_found\",", "f\"No trace events are recorded for trace_id {normalized!r}.\",", "details={\"trace_id\": normalized},", ")", "return {"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["\"sample_count\": len(items),"] },
  { f: "frontend/src/lib/traces.js", t: "app/common/stage_timing.py", p: "app/common/stage_timing.py", a: ["\"missing_stages\": [stage for stage in CANONICAL_STAGES if not stages[stage][\"count\"]],"] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["f\"trace replay failed: {type(exc).__name__}\","] },
  { f: "frontend/src/lib/traces.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["details={\"stage\": \"trace_store\"},", ")", "events = list(events or [])"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["}", "", "", "# ==================== 用户管理 ===================="] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["\"\"\"", "authorize_request(request, ACTION_MANAGE_USERS, resource_name=\"users\")", "try:"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["\"\"\"列出所有用户。"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["", "", "@router.post(\"/users\")"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["department=data.department or None,"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["", "@router.put(\"/users/password\")"] },
  { f: "frontend/src/lib/users.js", t: "app/common/auth.py", p: "app/common/auth.py", a: ["#: `tests/test_r356_users_refusal_face.py` 里那把形状尺子按名字判\"生产代码里唯一的"] },
  { f: "frontend/src/lib/users.js", t: "app/common/auth.py", p: "app/common/auth.py", a: ["#（口径同 app/main.py:138：中途 import 带 noqa: E402 并在旁边写下理由）。", "from app.common.permissions import CREATABLE_ROLES  # noqa: E402 - 理由见上面五行", "", "#: `list_users(denial=...)` 撞上「生产环境 + 进程内内存表」那道闸时的两种形状（R356）。"] },
  { f: "frontend/src/lib/users.js", t: "app/common/authorization.py", p: "app/common/authorization.py", a: ["def authorize_request(request, action: str, resource: dict | None = None, resource_name: str = \"\") -> bool:", "principal = principal_from_request(request)", "if principal is None:", "raise HTTPException(status_code=401, detail=\"authentication_required\")", "try:", "return authorize(principal, action, resource, resource_name)", "except PermissionError as exc:", "raise HTTPException(status_code=403, detail=str(exc)) from exc"] },
  { f: "frontend/src/lib/users.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["ROLE_PERMISSIONS = {", "\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),", "\"manager\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS, ACTION_APPROVE}),", "\"admin\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),", "\"auditor\": frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT}),", "}"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["return {\"users\": users}"] },
  { f: "frontend/src/lib/users.js", t: "app/common/auth.py", p: "app/common/auth.py", a: ["#: `tests/test_r356_users_refusal_face.py` 里那把形状尺子按名字判\"生产代码里唯一的"] },
  { f: "frontend/src/lib/users.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["ROLE_PERMISSIONS = {", "\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),", "\"manager\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS, ACTION_APPROVE}),", "\"admin\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),", "\"auditor\": frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT}),", "}"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["\"department\": u.get(\"department\") or \"\",   # 阶段 2"] },
  { f: "frontend/src/lib/users.js", t: "lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["context_limit_exceeded: {", "message: '这一轮的问题连同对话历史太长了，模型的上下文窗口装不下，请缩短问题或另起一轮会话再问。',", "retryable: false,", "},", "retrieval_unavailable: { message: '知识库检索暂不可用，回答可能缺少资料依据。', retryable: true },", "// 唯一出处 app/api/v1/chat.py:1303：/hitl/pending 取待确认列表时抛 PendingApprovalStoreMissing，", "// 也就是那张表还不存在（迁移没跑），503 的 detail 原样就是这个码。刻意不与下面 LEGACY_ALIASES 里", "// storage_read_only → internal_error 那句共用：「表不存在」要有人去跑迁移，「存储被切成只读」是", "// 另一回事，运维修的不是同一个故障，合并成一句就会把两条排查路都指错。"] },
  { f: "frontend/src/lib/users.js", t: "app/agents/evidence.py", p: "app/agents/evidence.py", a: ["_RETRIABLE_CODES = {\"model_unavailable\", \"retrieval_unavailable\", \"task_timeout\", \"rate_limited\", \"queue_unavailable\"}"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["async def delete_user(user_id: int, request: Request):"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["role: str = \"staff\"", "department: str = \"\""] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["\"\"\"", "authorize_request(request, ACTION_MANAGE_USERS, resource_name=\"users\")", "principal = principal_from_request(request)", "", "target = auth.get_user(data.username)", "if target is None:", "# 账号不存在也要留痕：有人拿别人的用户名为探针试这扇门，是本仓 R163 那族账在记的事。", "audit_log.record_audit(", "principal,", "ACTION_MANAGE_USERS,"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["async def delete_user(user_id: int, request: Request):"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["data.username,"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["except auth.UserStoreUnavailable as exc:"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["ok = auth.delete_user(user_id)"] },
  { f: "frontend/src/lib/users.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["", "after = data.department.strip()", "ok, msg = auth.update_department(data.username, after or None)", "if not ok:", "if msg == auth.USER_NOT_FOUND:", "raise HTTPException(status_code=404, detail=msg)"] },
  { f: "frontend/src/lib/users.js", t: "lib/errcodes.js", p: "frontend/src/lib/errcodes.js", a: ["context_limit_exceeded: {", "message: '这一轮的问题连同对话历史太长了，模型的上下文窗口装不下，请缩短问题或另起一轮会话再问。',", "retryable: false,", "},", "retrieval_unavailable: { message: '知识库检索暂不可用，回答可能缺少资料依据。', retryable: true },", "// 唯一出处 app/api/v1/chat.py:1303：/hitl/pending 取待确认列表时抛 PendingApprovalStoreMissing，", "// 也就是那张表还不存在（迁移没跑），503 的 detail 原样就是这个码。刻意不与下面 LEGACY_ALIASES 里", "// storage_read_only → internal_error 那句共用：「表不存在」要有人去跑迁移，「存储被切成只读」是", "// 另一回事，运维修的不是同一个故障，合并成一句就会把两条排查路都指错。"] },
  { f: "frontend/src/router/__tests__/r136-feed-merge.test.js", t: "routes.test.js", p: "frontend/src/router/__tests__/routes.test.js", a: ["expect(fallbacks[0].redirect).toEqual({ path: `/${DEFAULT_SCREEN}` })"] },
  { f: "frontend/src/router/__tests__/r136-feed-merge.test.js", t: "navigation.test.js", p: "frontend/src/__tests__/navigation.test.js", a: ["expect(existsSync(new URL('../components/__tests__/panel-states.test.js', import.meta.url))).toBe(true)"] },
  { f: "frontend/src/router/__tests__/r136-screen-names.test.js", t: "src/components/ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["revisions,"] },
  { f: "frontend/src/router/__tests__/r136-screen-names.test.js", t: "docs/frontend-plan-2026-09-14.md", p: "docs/frontend-plan-2026-09-14.md", a: ["| （新增） | — | 「交成果」 | 新增 | B-1 / R2 | 不做该视图 |"] },
  { f: "frontend/src/router/__tests__/r136-screen-names.test.js", t: "docs/handoff/2026-09-15-backend-followup-requests.md", p: "docs/handoff/2026-09-15-backend-followup-requests.md", a: ["- **四、\"说人话\"的硬规矩（要写成用例钉住，不靠自觉）**：① 每个错误态必须回答\"我下一步该怎么办\"，屏上不许出现错误码原文／接口路径／字段名（`src/lib/no-bare-code.test.js` 已在钉，扩到全部屏）；② 空态三张脸必须可区分：**确实没有** / **你没权限看到** / **系统坏了**（后两张缺的随 R26 补）；③ 每个入口的名字要跟员工的话一致（评测题里的词：问一句、交成果、报销自查、异常与告警、口径对不上），顶栏与页内同源（R136 判据①）；④ 越权题的界面答复必须是\"这份你看不到\"而不是\"没有这个文件\"（6 道跨部门权限题就是这条的验收样本）。"] },
  { f: "frontend/src/router/__tests__/r136-screen-names.test.js", t: "ChatPanel.vue", p: "frontend/src/components/ChatPanel.vue", a: ["revisions,"] },
  { f: "frontend/src/router/__tests__/r316-admin-entry.test.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["authorize_request(request, ACTION_MANAGE_USERS, resource_name=\"users\")", "try:"] },
  { f: "frontend/src/router/__tests__/r316-admin-entry.test.js", t: "app/common/policy.py", p: "app/common/policy.py", a: ["_ADMINISTRATOR_ROLES = frozenset({\"admin\"})"] },
  { f: "frontend/src/router/__tests__/r316-admin-entry.test.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"admin\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),"] },
  { f: "frontend/src/router/__tests__/r316-admin-entry.test.js", t: "App.vue", p: "frontend/src/App.vue", a: ["import { DEFAULT_SCREEN, FEED_SCREEN, cachedScreens, navigationForRole, screenRouteIds } from './router'"] },
  { f: "frontend/src/router/__tests__/r316-admin-entry.test.js", t: "App.vue", p: "frontend/src/App.vue", a: ["v-for=\"item in navigationForRole(userRole)\""] },
  { f: "frontend/src/router/__tests__/r316-admin-entry.test.js", t: "App.vue", p: "frontend/src/App.vue", a: ["const userRole = shallowRef('staff')"] },
  { f: "frontend/src/router/feed-tabs.js", t: "App.vue", p: "frontend/src/App.vue", a: ["// 这枚 import 刻意落在 27 行之后：App.vue:27 是在册坐标（r420 L-6 现读对账钉着它），本单不许"] },
  { f: "frontend/src/router/index.js", t: "docs/frontend-plan-2026-09-14.md", p: "docs/frontend-plan-2026-09-14.md", a: ["| （新增） | — | 「交成果」 | 新增 | B-1 / R2 | 不做该视图 |"] },
  { f: "frontend/src/router/index.js", t: "app/api/v1/auth.py", p: "app/api/v1/auth.py", a: ["authorize_request(request, ACTION_MANAGE_USERS, resource_name=\"users\")", "try:"] },
  { f: "frontend/src/router/index.js", t: "app/common/policy.py", p: "app/common/policy.py", a: ["_ADMINISTRATOR_ROLES = frozenset({\"admin\"})"] },
  { f: "frontend/src/router/index.js", t: "App.vue", p: "frontend/src/App.vue", a: ["v-for=\"item in navigationForRole(userRole)\""] },
  { f: "frontend/src/router/index.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"admin\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),"] },
  { f: "frontend/src/router/index.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"auditor\": frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT}),"] },
  { f: "frontend/src/router/index.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"staff\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_ANALYZE}),"] },
  { f: "frontend/src/router/index.js", t: "app/common/permissions.py", p: "app/common/permissions.py", a: ["\"manager\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS, ACTION_APPROVE}),"] },
  { f: "frontend/src/router/index.js", t: "app/api/v1/observability.py", p: "app/api/v1/observability.py", a: ["\"replay_path\": f\"/api/v1/traces/{trace_id}\","] },
  { f: "frontend/src/router/index.js", t: "app/common/policy.py", p: "app/common/policy.py", a: ["_ADMINISTRATOR_ROLES = frozenset({\"admin\"})"] },
  { f: "frontend/src/router/index.js", t: "permissions.py", p: "app/common/permissions.py", a: ["\"admin\": frozenset({ACTION_VIEW, ACTION_UPLOAD, ACTION_DOWNLOAD, ACTION_DELETE, ACTION_ANALYZE, ACTION_EXPORT, ACTION_APPROVE, ACTION_AUDIT, ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS}),"] },
]
/* R560-ROSTER-END */
const SELF = fileURLToPath(import.meta.url)
const UP = '../../../../'
const SKIP_DIRS = new Set(['node_modules', 'dist', '.git', 'coverage', '.vite'])
const OWNED = new Set(['r416-comments-cite-live-coordinates.test.js', 'r420-stale-coordinates-second-blade.test.js',
  'r427-borrowed-name-and-live-coordinates.test.js', 'r538-hand-copied-coordinates.test.js'])
const TOKEN = '[\\w.@+/-]+\\.(?:py|js|jsx|ts|vue|css|md|json|sql|toml|ya?ml|html|txt)'
const BODY = new RegExp('(?:(' + TOKEN + ')|(?<![\\w.@/-])):\\s*(\\d+)((?:\\s*[-,]\\s*\\d+)*)', 'g')
const isComment = line => /^\s*(\/\/|\*|\/\*|<!--|#)/.test(line) || line.includes('//') || line.includes('/*')
const disk = rel => readFileSync(new URL(UP + rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const work = (rel, override) => (override && override[rel] !== undefined ? override[rel] : disk(rel))
const CACHE = new Map()
function headLines(repoPath) {
  if (CACHE.has(repoPath)) return CACHE.get(repoPath)
  let text
  try {
    text = execFileSync('git', ['show', 'HEAD:' + repoPath], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  } catch (cause) {
    throw new Error('读不到真源 HEAD:' + repoPath + '（git show 失败：' + cause.message + '）：行号对账不许降级成 skip')
  }
  if (!String(text).trim()) throw new Error('git show HEAD:' + repoPath + ' 返回空内容，无法对账')
  // R560 取证的坑：裸 CR 在 git／rg／python 眼里都不是换行，只有 \n 才是。
  // 这一行过去把孤立 CR 也当换行切，碰到带裸 CR 的文档时每一枚行号整体下漂（漂的枚数＝此前的裸 CR 枚数），
  // 于是注释里写的行号与当场推导的行号量的不是同一把尺。口径统一到 \n 切分，与生成台账那一侧同源。
  const lines = String(text).replace(/\r\n/g, '\n').split('\n')
  CACHE.set(repoPath, lines)
  return lines
}
function derive(repoPath, anchor, rows) {
  const body = rows || headLines(repoPath)
  const want = anchor.map(line => line.trim()).join('\n')
  const hits = []
  for (let i = 0; i + anchor.length <= body.length; i += 1) {
    if (body.slice(i, i + anchor.length).map(line => line.trim()).join('\n') === want) hits.push(i + 1)
  }
  if (hits.length === 0) throw new Error('现读推导落空：' + repoPath + ' 的真源里找不到锚段 ' + JSON.stringify(anchor))
  if (hits.length > 1) throw new Error('锚段在 ' + repoPath + ' 里有 ' + hits.length + ' 处（行 ' + hits.join('、') + '）：这一枚坐标已成歧义，对账不该绿')
  return hits[0]
}
function scanClaims(files, override) {
  const out = []
  for (const rel of files) {
    const lines = work(rel, override).split('\n')
    let last = null
    let i = 0
    while (i < lines.length) {
      if (!isComment(lines[i])) { last = null; i += 1; continue }
      let j = i
      while (j < lines.length && isComment(lines[j])) j += 1
      for (let k = i; k < j; k += 1) {
        const re = new RegExp(BODY.source, 'g')
        let m
        while ((m = re.exec(lines[k])) !== null) {
          if (m[1]) last = m[1]
          if (!last) continue
          const seps = m[3].match(/[-,]/g) || []
          const nums = [Number(m[2])].concat((m[3].match(/\d+/g) || []).map(Number))
          let pos = 0
          while (pos < nums.length) {
            if (pos + 1 < nums.length && pos < seps.length && seps[pos] === '-') {
              out.push({ f: rel, line: k + 1, col: m.index, t: last, start: nums[pos], end: nums[pos + 1] })
              pos += 2
            } else {
              out.push({ f: rel, line: k + 1, col: m.index, t: last, start: nums[pos], end: null })
              pos += 1
            }
          }
        }
      }
      i = j
    }
  }
  out.sort((a, b) => (a.f < b.f ? -1 : a.f > b.f ? 1 : a.line - b.line || a.col - b.col))
  return out
}
function censusFiles() {
  const root = new URL('../../', import.meta.url)
  return readdirSync(root, { recursive: true })
    .map(name => String(name).replace(/\\/g, '/'))
    .filter(name => /\.(js|vue|ts|css|html)$/.test(name))
    .filter(name => !name.split('/').some(part => SKIP_DIRS.has(part)))
    .filter(name => !OWNED.has(name.split('/').pop()))
    .map(name => 'frontend/src/' + name)
    .filter(rel => fileURLToPath(new URL(UP + rel, import.meta.url)) !== SELF)
    .sort()
}
const join = c => c.f + ' ' + c.t
function groupBy(list) {
  const map = new Map()
  for (const item of list) {
    const k = join(item)
    if (!map.has(k)) map.set(k, [])
    map.get(k).push(item)
  }
  return map
}
const FILES = censusFiles()
const LIVE = scanClaims(FILES)
const LEDGER = ROSTER.map(entry => ({ f: entry.f, t: entry.t }))
const LIVE_K = groupBy(LIVE)
const LEDGER_K = groupBy(LEDGER)
const ANCHORED = ROSTER.filter(entry => entry.a)
const UNANCHORED = ROSTER.filter(entry => !entry.a)
const GLOBAL_SLOT = new Map()
ROSTER.forEach((entry, index) => {
  const k = join(entry)
  if (!GLOBAL_SLOT.has(k)) GLOBAL_SLOT.set(k, 0)
  GLOBAL_SLOT.set(entry, GLOBAL_SLOT.get(k))
  GLOBAL_SLOT.set(k, GLOBAL_SLOT.get(k) + 1)
})
const claimAt = entry => {
  const live = LIVE_K.get(join(entry)) || []
  return live[GLOBAL_SLOT.get(entry)]
}
describe('R560甲 · 现扫 census 全覆盖', () => {
  it('现扫枚数 == 台账枚数（删引用躲检查＝红，手抄新数字＝红）', () => {
    expect(LIVE.length, '现扫 ' + LIVE.length + ' 枚，台账 ' + ROSTER.length + ' 枚：census 漂了').toBe(ROSTER.length)
  })
  it('逐组等长：每个（所在文件, 引用名）的枚数一一对得上', () => {
    for (const [k, entries] of LEDGER_K) {
      const live = LIVE_K.get(k) || []
      expect(live.length, k + '：注释现扫 ' + live.length + ' 枚，台账登记 ' + entries.length + ' 枚').toBe(entries.length)
    }
    for (const [k, live] of LIVE_K) {
      expect(LEDGER_K.has(k), k + ' 有 ' + live.length + ' 枚坐标在台账之外：账外引用先入账').toBe(true)
    }
  })
})
describe('R560乙 · 逐枚现读对账（锚串当场推导，不读快照）', () => {
  for (const entry of ANCHORED) {
    it(entry.f + ' 引 ' + entry.t + ' 的那一枚 == HEAD 里锚段的真位置', () => {
      const claim = claimAt(entry)
      if (!claim) throw new Error('台账里这一枚在现扫里不见了：' + entry.f + ' / ' + entry.t + '（引用被删不等于坐标修好）')
      const derived = derive(entry.p, entry.a)
      expect(claim.start, entry.f + ' 的注释写 ' + entry.t + ':' + claim.start + '，HEAD 里那截锚段在第 ' + derived + ' 行：行号漂了，注释必须跟着改口').toBe(derived)
      if (claim.end !== null && claim.end !== undefined) {
        expect(entry.a.length, entry.f + ' 说 ' + entry.t + ' 的区间长 ' + (claim.end - claim.start + 1) + ' 行，锚段只有 ' + entry.a.length + ' 行：区间被改短或真源那一截缩了').toBeGreaterThanOrEqual(claim.end - claim.start + 1)
      }
    })
  }
})
describe('R560丙 · 量具自证', () => {
  it('刀二：锚段换成真源里不存在的串，当场抛，不许蒙成绿', () => {
    const probe = ANCHORED[0]
    expect(() => derive(probe.p, ['__r560_no_such_anchor__'])).toThrow(/找不到锚段/)
  })
  it('刀三：推导的读法换成工作树 ⇒ 未提交态那一发必须对不上（HEAD 读法才对得上）', () => {
    const probe = ANCHORED.find(entry => entry.p.startsWith('frontend/') && entry.a.length === 1)
    expect(probe, '台账里没有一枚以前端件为真源的锚段：这一把刀没材料').toBeTruthy()
    const claim = claimAt(probe)
    const headPos = derive(probe.p, probe.a)
    expect(headPos, '正控：HEAD 读法就对不上，台账本身漂了').toBe(claim.start)
    const shifted = disk(probe.p).split('\n')
    shifted.splice(1, 0, '// r560 knife-three：临时插一行，制造未提交态')
    const wtPos = derive(probe.p, probe.a, shifted)
    expect(wtPos, '读法换成工作树后位置没挪：那一发根本没在量未提交态').not.toBe(headPos)
    expect(wtPos).toBe(headPos + 1)
  })
  it('刀四：同一枚锚段在真源里长出第二处命中 ⇒ 当场抛「已成歧义」，不许挑一处算对', () => {
    const probe = ANCHORED.find(entry => entry.a.length === 1 && entry.p.startsWith('app/'))
    expect(probe, '台账里没有一枚单行锚段的前端以外真源：这一把刀没材料').toBeTruthy()
    const base = headLines(probe.p)
    expect(derive(probe.p, probe.a), '正控：这一枚锚段在 HEAD 里就该只有一处命中').toBe(claimAt(probe).start)
    const dup = base.concat(['// r560 knife-four：把同一行再写一遍，制造歧义'], probe.a)
    expect(() => derive(probe.p, probe.a, dup), '锚段重复之后还肯返回一个行号，就是把「挑一处」当成了「对上了」').toThrow(/已成歧义/)
  })
  it('本件 0 枚降级记号（跳过／放宽／独占）：锚串找不到就抛，躲检查不算修好', () => {
    const self = readFileSync(SELF, 'utf8').replace(/\r\n/g, '\n')
    const a = self.indexOf('/* R560-ROSTER-BEGIN */')
    const b = self.indexOf('/* R560-ROSTER-END */')
    expect(a, '起手标记不见了').toBeGreaterThan(-1)
    expect(b, '收尾标记不见了').toBeGreaterThan(a)
    const body = self.slice(0, a) + self.slice(b)
    for (const needle of ['.sk' + 'ip', 'xi' + 't(', 'it.' + 'only', 'describe.' + 'only', 'xf' + 'ail', 'test.' + 'skip']) {
      expect(body.includes(needle), '本件里出现了 ' + needle + '：锚串找不到要抛，不许降级').toBe(false)
    }
  })
})
describe('R560丁 · 自述对账与坐标字面量', () => {
  it('台账／已锚定／未锚定三枚枚数各自与自述相等：改台账不改自述，当场红', () => {
    expect(ROSTER.length).toBe(516)
    expect(ANCHORED.length).toBe(516)
    expect(UNANCHORED.length).toBe(0)
  })
  it('未锚定那一格逐枚仍在现扫里（debt 不许隐身，也不许被悄悄删掉）', () => {
    for (const entry of UNANCHORED) {
      expect(claimAt(entry), entry.f + ' 引 ' + entry.t + ' 那一枚未锚定坐标在现扫里不见了：它被删了，不是被修好了').toBeTruthy()
    }
  })
  it('ROSTER 段以外 0 处坐标字面量：写死数字的钉叫快照，不叫派生钉', () => {
    const self = readFileSync(SELF, 'utf8').replace(/\r\n/g, '\n')
    const start = self.indexOf('/* R560-ROSTER-BEGIN */')
    const end = self.indexOf('/* R560-ROSTER-END */')
    expect(start, 'ROSTER 段起手标记不见了').toBeGreaterThan(-1)
    expect(end, 'ROSTER 段收尾标记不见了').toBeGreaterThan(start)
    const outside = []
    for (const hit of (self.slice(0, start) + self.slice(end)).matchAll(/\.(?:py|js|jsx|ts|vue|css|md|json|sql|toml|ya?ml|html|txt):\d+/g)) {
      outside.push(hit[0])
    }
    expect(outside, '本件在台账段以外写死了坐标（' + outside.join(' ') + '）：判据②不许').toHaveLength(0)
  })
})