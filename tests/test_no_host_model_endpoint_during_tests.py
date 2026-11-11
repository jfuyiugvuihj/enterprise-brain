"""跟进单 R56：测试期不得真打宿主 Ollama（127.0.0.1:11434）。

判据形式（总控 09-17 改判，照此存档）：硬闸优先于计数。跟进单 §21.8 L700 的原判据
"统计全量 pytest 期间对 11434 的连接数为 0"与 §21.7 的禁止跑全量 pytest 互相矛盾；
计数又是事后的，挡不住新用例引入。闸门是事前的、可自证的：连接一开口就抛，同时留一条
跨 except 存活的 sticky 记录，由 tests/conftest.py 的 host_model_endpoint_tripwire 逐用例
兜底断言。依据：app/common/model_capabilities.py:95-100 的 except Exception 会把 transport
异常洗成 available=False / error_code=model_unavailable（app/rag/retriever.py:62 同理洗成
零向量），光靠 raise 一次测试根本不会红。

两条 _must_turn_red 用例默认绿（它们什么连接都不做）；置 EB_R56_COUNTERPROOF=1 之后必须红。
为什么用环境变量开关而不是"注释掉那一行"：判据等价，但不改文件、可复现，也不会把一条
永久红的用例留在套件里 —— 那本身就把验收基线 159 passed 打穿了。
"""
import os
import socket

COUNTERPROOF_ENV = "EB_R56_COUNTERPROOF"
HOST_MODEL_ADDRESS = ("127.0.0.1", 11434)


def _counterproof_enabled() -> bool:
    """反证开关：只有显式打开，用例才允许真去碰一次宿主模型端口。"""
    return os.environ.get(COUNTERPROOF_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def test_conftest_pins_the_local_model_name_before_app_import(model_endpoint_guard):
    """判据①之一：调用方不必再记着设环境变量，哨兵在 app 导入前就已生效。"""
    guard = model_endpoint_guard
    mark = guard.blocked_count()
    assert os.environ["LOCAL_MODEL_NAME"].strip(), "LOCAL_MODEL_NAME 必须是非空哨兵"
    assert (
        guard.model_config.get_local_model_settings().model_source == "configured"
    ), "解析模型配置时走进了发现分支：哨兵没有在 app 导入前生效"
    settings = guard.model_config.get_local_model_settings()
    assert settings.model_name, "哨兵生效时模型名不该为空"
    assert guard.blocked_count() == mark, "光是解析模型配置就不该开任何 socket"


def test_discovery_path_stays_offline_when_nothing_is_configured(
    model_endpoint_guard, monkeypatch
):
    """R56 的原始缺陷场景：两个模型名环境变量都为空，model_config.py:175 直接走发现。

    改前这一步真会 connect 127.0.0.1:11434（仓库外探针实测 9 次）；改后必须一个 socket
    都不开，同时留下"发现调用落在离线桩上"的证据。
    """
    guard = model_endpoint_guard
    monkeypatch.delenv(guard.env_name, raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    guard.model_config.reset_model_discovery_cache()
    mark = guard.blocked_count()
    offline_before = len(guard.offline_calls)

    settings = guard.model_config.get_local_model_settings()

    assert settings.model_name == ""
    assert settings.model_source == "none"
    assert guard.blocked_count() == mark, "发现路径开出了真 socket"
    assert len(guard.offline_calls) > offline_before, (
        "发现调用没有经过离线假 transport：_fetch_registry 的钉子被绕过了"
    )


def test_tripwire_is_armed_and_scoped_to_the_host_model_port(model_endpoint_guard, monkeypatch):
    """判据②：闸门在位、作用域准确。这里只做纯谓词判断，不允许留下任何连接尝试；

    "真抛一次"由下面两条反证用例负责，只有它们被允许制造记录。
    """
    guard = model_endpoint_guard
    mark = guard.blocked_count()
    assert getattr(socket.socket, "_eb_r56_tripwire", False) is True, "闸门没装"
    assert socket.socket.connect.__name__ == "guarded_connect"
    assert socket.socket.connect_ex.__name__ == "guarded_connect_ex"
    assert socket.create_connection.__name__ == "guarded_create_connection"
    assert guard.targets(HOST_MODEL_ADDRESS), "必须拦 127.0.0.1:11434"
    assert guard.targets(("localhost", 11434)), "必须拦 localhost:11434"
    assert guard.targets(("::1", 11434)), "必须拦 [::1]:11434"
    assert not guard.targets(("127.0.0.1", 1)), (
        "R20 的 PG 钉子走的就是 127.0.0.1:1，拦了会把既有失败语义改掉"
    )
    assert not guard.targets(("127.0.0.1", 6379)), "非模型端口不能误伤"
    assert not guard.targets(("10.0.0.8", 11434)), "远端模型主机不属于本单"
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11500")
    assert guard.targets(("127.0.0.1", 11500)), "OLLAMA_BASE_URL 指到的本地端口也要进闸"
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.8:11500")
    assert not guard.targets(("127.0.0.1", 11500)), (
        "base_url 指向远端主机时，本地同号端口不算宿主模型端口"
    )
    assert guard.blocked_count() == mark, "纯谓词检查不该留下连接尝试"


def test_counterproof_a_deliberate_socket_to_the_host_model_port_must_turn_red(
    model_endpoint_guard,
):
    """反证用例：故意连一次宿主模型端口，本用例必须红；不做这次连接（关开关）必须绿。

    红的三条来路任何一条都算数：
      - 闸门正常：create_connection 当场抛 HostModelEndpointBlocked，call 阶段就红；
      - 闸门被删掉、宿主 Ollama 在跑：连接真开出去，下面的 sticky 记录断言失败；
      - 闸门被删掉、宿主 Ollama 没在跑：ConnectionRefusedError，同样红。
    """
    guard = model_endpoint_guard
    mark = guard.blocked_count()
    attempted = False
    if _counterproof_enabled():
        attempted = True
        connection = socket.create_connection(HOST_MODEL_ADDRESS, timeout=1)
        connection.close()
    if attempted:
        assert guard.blocked_count() > mark, (
            "闸门没拦住这次连接：它没有进入 sticky 记录，"
            "说明 socket 真的开到网络上去了"
        )
    else:
        assert guard.blocked_count() == mark, (
            "反证开关关着却留下了连接尝试：另有用例在打宿主模型端口"
        )


def test_counterproof_the_real_registry_transport_must_turn_red(
    model_endpoint_guard, monkeypatch
):
    """反证用例：故意把出厂 transport 放回去让发现路径自己开 socket，本用例必须红。

    这条专治"只 raise 一次就够了"的错觉：闸门的异常一回到
    app/common/model_capabilities.py:95-100 的 except Exception 就被洗成
    available=False / model_unavailable，用例体里的断言全部照常通过，
    红只能由 tests/conftest.py 的 host_model_endpoint_tripwire 在收尾阶段按 sticky 记录补。
    所以这里刻意不写 pytest.fail：留一步给兜底断言，才证明那半套机制真的在工作。
    """
    guard = model_endpoint_guard
    mark = guard.blocked_count()
    attempted = False
    if _counterproof_enabled():
        attempted = True
        monkeypatch.setattr(
            guard.model_config, "_fetch_registry", guard.shipped_registry_fetch
        )
        monkeypatch.delenv(guard.env_name, raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        guard.model_config.reset_model_discovery_cache()
        settings = guard.model_config.get_local_model_settings()
        assert settings.model_source == "none", (
            "发现路径拿到了真模型名：宿主 Ollama 被打了，而且没人拦"
        )
    if attempted:
        assert guard.blocked_count() > mark, (
            "闸门没有记录这次发现连接：socket 层钩子被绕过"
        )
    else:
        assert guard.blocked_count() == mark, "反证开关关着却留下了连接尝试"