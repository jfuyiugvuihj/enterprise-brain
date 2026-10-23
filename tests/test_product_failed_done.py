import json

import pytest

from app.api.v1.chat import done_frame_for_turn


@pytest.mark.parametrize("status", ["failed", "rejected"])
def test_failed_calculation_does_not_end_as_answered(status):
    frame = done_frame_for_turn(
        request_id="test-request",
        session_id="test-session",
        full_text="制度条款已找到，但数据筛选失败。",
        intr=None,
        visible_rows=[],
        dataset_files=[],
        agent_results={},
        terminal_status=status,
    )

    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload["terminal_state"] == status
    assert payload["answer_present"] is True
