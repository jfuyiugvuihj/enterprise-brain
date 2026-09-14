from pathlib import Path


def test_chat_panel_exposes_cancel_action_and_abort_controller():
    source = Path("frontend/src/components/ChatPanel.vue").read_text(encoding="utf-8")

    assert "AbortController" in source
    assert "/ask/${sessionId.value}/cancel" in source
    assert "取消生成" in source
