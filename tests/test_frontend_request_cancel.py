from pathlib import Path


def test_chat_panel_exposes_cancel_action_and_abort_controller():
    source = Path("frontend/src/components/ChatPanel.vue").read_text(encoding="utf-8")
    sessions = Path("frontend/src/lib/sessions.js").read_text(encoding="utf-8")

    # 重指向（2026-09-15 集成后）：AbortController 收进了 SSE 读流层，面板只调 abortStream()。
    #   ChatPanel.vue:5 / :29   import { abortStream, ... } from '../lib/sessions'
    #   ChatPanel.vue:236       abortStream()
    #   lib/sessions.js:191     controller = new AbortController()
    #   lib/sessions.js:201     export function abortStream()
    assert "abortStream," in source
    assert "} from '../lib/sessions'" in source
    assert "abortStream()" in source
    assert "controller = new AbortController()" in sessions
    assert "export function abortStream()" in sessions
    # 重指向：会话主键改名 sessionId.value -> activeId.value（ChatPanel.vue:243）
    assert "/ask/${activeId.value}/cancel" in source
    # V7-4 把旧断言的方向反过来了：「取消生成」是假承诺——它既不拒绝挂起动作，也不撤销
    # 后端已受理的动作，所以这个字样必须消失；按钮要说真话，二次确认要写清副作用边界。
    assert "取消生成" not in source
    assert "中断本次回答" in source
    assert 'data-testid="chat-cancel"' in source
    assert "不会撤销任何动作" in source
