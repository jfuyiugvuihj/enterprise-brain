"""R586 pins: the context window has two owners, and the compose file now carries both.

Facts these pins are built on (all read off this tree, 2026-10-03):

* ``MODEL_CONTEXT_TOKENS`` is the window *this process* computes its budget against
  (``app/common/model_budget.py``); the window actually served inside the model belongs to
  the model server. The product puts no ``num_ctx`` into any request payload -- R135 read
  that off ``app/**`` and it is restated at ``app/agents/contracts.py:165`` and
  ``app/api/v1/observability.py:1818`` -- so the server half is decided by the container's
  own environment, and nothing in our code can raise it.
* The shipped defaults stay 4096 (``.env.example`` and
  ``app.common.model_budget.DEFAULT_CONTEXT_TOKENS``). Raising the window is a per-machine
  decision, measured on this box by ``scripts/r586_context_window_probe.py`` and recorded in
  ``deploy/.env.server`` (untracked). So the compose half must default to 4096 too: a
  compose file that hard-codes 8192 would silently hand every customer a different window
  than the one the shipped defaults promise.
"""

import ast
import io
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "docker-compose.yml"
PROBE = REPO / "scripts" / "r586_context_window_probe.py"

SERVER_HALF = "OLLAMA_CONTEXT_LENGTH"
PRODUCT_HALF = "MODEL_CONTEXT_TOKENS"


def compose_text():
    return COMPOSE.read_text(encoding="utf-8")


def ollama_environment():
    doc = yaml.safe_load(compose_text())
    service = doc["services"]["ollama"]
    env = service.get("environment") or {}
    if isinstance(env, list):  # compose allows the KEY=VALUE list shape
        env = dict(item.split("=", 1) for item in env)
    return env


def test_the_model_server_half_of_the_window_is_carried_by_compose():
    env = ollama_environment()
    assert SERVER_HALF in env, "ollama 那格没有服务端窗口，客户端抬了也没用"


def test_the_shipped_default_of_the_server_half_matches_the_shipped_product_default():
    """Neither half may be quietly widened for every customer: both stay at 4096."""
    from app.common.model_budget import DEFAULT_CONTEXT_TOKENS

    value = ollama_environment()[SERVER_HALF]
    match = re.fullmatch(r"\$\{%s:-(\d+)\}" % SERVER_HALF, str(value))
    assert match, f"{SERVER_HALF} 必须是可插值的，客户按机器改，不改文件：{value!r}"
    assert int(match.group(1)) == DEFAULT_CONTEXT_TOKENS == 4096


def test_the_two_halves_are_documented_next_to_each_other():
    """The pairing is the whole point of the ticket, so it lives beside the knob, not in a
    ticket nobody reads: the compose comment has to name the product half."""
    text = compose_text()
    block = text[text.index(SERVER_HALF) - 1200 : text.index(SERVER_HALF) + 120]
    assert PRODUCT_HALF in block, "compose 里那两行注释没点名 MODEL_CONTEXT_TOKENS，配套关系会失传"
    assert re.search(r"restart|force-recreate|env_file", block), "没写明改完要重建容器这一手"


def test_the_probe_takes_its_corpus_from_the_registered_instrument_not_a_second_copy():
    """Same corpus as the W8 rate curves, or the numbers cannot be compared with them."""
    source = PROBE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.targets[0].id for node in ast.walk(tree)
             if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert "_SENTENCES" not in names, "探针自己抄了一份语料，就会有第二把尺"
    assert "perf_probe_rate.py" in source and "corpus()" in source


def test_the_probe_never_sends_anything_but_a_chat_request():
    """Measurement must not become a write: no product route, no container file, no POST
    anywhere except the native /api/chat we are measuring."""
    source = PROBE.read_text(encoding="utf-8")
    assert '/api/chat' in source
    for forbidden in ("/api/generate", "up -d", "compose build", "CREATE ", "INSERT ", "DROP TABLE"):
        assert forbidden not in source, forbidden


# --- counter-evidence knives -------------------------------------------------------
# Each knife strips one leg in memory and names the victim pin that must go red.


def _env_without_server_half():
    line = '      %s: ${%s:-4096}' % (SERVER_HALF, SERVER_HALF)
    text = compose_text().replace(line + '\n', '').replace(line + '\r\n', '')
    assert line not in text, 'the assignment line survived the strip, so this knife is a no-op'
    return text

def test_knife_one_losing_the_server_half_blinds_the_pairing():
    doc = yaml.safe_load(_env_without_server_half())
    env = doc["services"]["ollama"].get("environment") or {}
    assert SERVER_HALF not in env
    # the pin above must therefore fail, not silently pass on a missing key
    assert "assert SERVER_HALF in env" in inspect_source_of(
        "test_the_model_server_half_of_the_window_is_carried_by_compose"
    )


def inspect_source_of(fn_name):
    source = io.open(__file__, encoding="utf-8").read()
    start = source.index("def %s(" % fn_name)
    end = source.index("\ndef ", start + 1)
    return source[start:end]


def test_knife_two_widening_the_default_breaks_the_shipped_promise():
    """If somebody bakes 8192 into the file, the default-vs-shipped equality has to bite."""
    text = compose_text().replace("${%s:-4096}" % SERVER_HALF, "${%s:-8192}" % SERVER_HALF)
    assert "${%s:-8192}" % SERVER_HALF in text
    leg = "int(match.group(1)) == DEFAULT_CONTEXT_TOKENS == 4096"
    assert leg in inspect_source_of(
        "test_the_shipped_default_of_the_server_half_matches_the_shipped_product_default"
    ), "这一腿被改宽过，本钉就成了装饰"


def test_knife_three_a_second_corpus_copy_is_visible_from_the_ast():
    """Feed the AST rule a fake probe that copies the corpus; the rule must reject it."""
    fake = "\n".join([
        "import json",
        "_SENTENCES = json.loads('[]')",
        "def corpus():",
        "    return _SENTENCES",
    ])
    names = {node.targets[0].id for node in ast.walk(ast.parse(fake))
             if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert "_SENTENCES" in names
