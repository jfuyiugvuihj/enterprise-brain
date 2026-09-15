from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_login_page_does_not_offer_anonymous_registration():
    source = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")

    assert "doRegister" not in source
    assert '"/api/v1/users"' not in source
    # 重指向（V2-a 改版后文案为「没有账号？联系管理员在工作台内开通」，App.vue:283）：
    # 钉的是政策而不是整句文案——全页不得出现「注册」二字（实测 0 次），同时保留
    # 「没有账号该找谁」这条指引的三个要素，改标点不再触发假红，重新加注册入口一定触发。
    assert "注册" not in source
    assert "没有账号？" in source
    assert "联系管理员" in source
    assert "开通" in source


def test_login_page_handles_empty_error_response_gracefully():
    source = (ROOT / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")

    # 重指向：readJsonSafe 的后继是 lib/http.js 的 errorDetail()。
    #   App.vue:125  if (!data.token) —— 2xx 但缺令牌也不进会话，另给明确文案
    #   App.vue:134  loginError.value = errorDetail(err, '登录服务暂时不可用')
    #   lib/http.js:148/156 —— 空 body、非 JSON、以及 axios 自带的
    #     "Request failed with status code NNN" 一律落回兜底文案，不抛未捕获异常
    http_source = (ROOT / "frontend" / "src" / "lib" / "http.js").read_text(encoding="utf-8")

    assert "if (!data.token) {" in source
    assert "登录响应缺少令牌" in source
    assert "loginError.value = errorDetail(err, '登录服务暂时不可用')" in source
    assert "登录服务暂时不可用" in source
    assert "export function errorDetail(err, fallback = '请求失败')" in http_source
    assert "^Request failed with status code \\d+$/.test(message)" in http_source
