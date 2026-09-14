from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_login_page_does_not_offer_anonymous_registration():
    source = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")

    assert "doRegister" not in source
    assert '"/api/v1/users"' not in source
    assert "没有账号？联系管理员开通" in source
def test_login_page_handles_empty_error_response_gracefully():
    source = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")

    assert "async function readJsonSafe" in source
    assert "登录服务暂时不可用" in source
