from pathlib import Path


CHAT_SOURCE = Path("frontend/src/components/ChatPanel.vue").read_text(encoding="utf-8")


def test_chat_session_persists_selected_data_filename():
    assert "dataFilename" in CHAT_SOURCE
    assert "activeDataFilename" in CHAT_SOURCE


def test_manual_followup_uses_selected_data_filename():
    assert "async function send(dataFilename = activeDataFilename.value)" in CHAT_SOURCE
