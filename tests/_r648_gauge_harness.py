# -*- coding: utf-8 -*-
"""R648 同名件共用的夹具：量具按文件名单独加载，影子只落 ``tmp_path``，默认态一枚子进程都不发。

在册纪律（本周同族事故 #96 / #107 / #113）：

* 🔴 影子端只在 ``tmp_path`` 的副本上动手，仓内原件每枚前后各核一次 sha256；锚点是**唯一
  文本**，不是行号，也不是「文件此刻的 sha」——身份设计里不许含行位。
* 默认态（``R648_REAL_PG`` 没设）由 ``Tripwire`` 把量具唯一的子进程出口换成计数器：
  响一枚就红，所以「常驻件不许偷偷连库」是可证的，不是纸上的话。
* 影子模块的 ``REPO`` 一律指回真仓，否则红得没有道理（同 R545 那套机械）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GAUGE_PATH = REPO / "scripts" / "r648_real_pg_gauge.py"
RETRIEVER_PATH = REPO / "app" / "rag" / "retriever.py"

#: 真腿复跑闸：与量具同一枚 env 名、同一组取值（默认关 ⇒ 一次 docker 往返都不发）。
REAL_PG_OPT_IN = str(os.environ.get("R648_REAL_PG", "") or "").strip().lower() in {
    "on", "1", "true", "yes"
}


def sha_of(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


GAUGE_BASELINE_SHA = sha_of(GAUGE_PATH)
RETRIEVER_BASELINE_SHA = sha_of(RETRIEVER_PATH)


def _load(text: str, directory, module_name: str, file_name: str):
    target = Path(directory) / file_name
    target.write_text(text, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location(module_name, str(target))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_gauge(tmp_path, name="pristine", *, edits=()):
    """加载量具的影子副本；``edits=()`` 就是正控，刀下与正控走**同一枚加载路径**。"""
    assert sha_of(GAUGE_PATH) == GAUGE_BASELINE_SHA, "进刀之前量具就不是原样"
    text = GAUGE_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    for anchor, replacement in edits:
        hits = text.count(anchor)
        assert hits == 1, (name + "：锚点出现 " + str(hits) + " 次，不唯一 ⇒ 这枚反证是空的")
        text = text.replace(anchor, replacement, 1)
    if edits:
        assert text != GAUGE_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n"), \
            name + "：改了个寂寞"
    os.environ["R648_REPO"] = str(REPO)
    module = _load(text, tmp_path, "r648_gauge_" + name, "r648_gauge_" + name + ".py")
    module.REPO = REPO
    assert sha_of(GAUGE_PATH) == GAUGE_BASELINE_SHA, name + "：影子跑完原件不是原样"
    return module


def load_retriever_copy(tmp_path, name, *, anchor=None, replacement=None):
    """把 ``app/rag/retriever.py`` 原样或按锚点改一处，加载成独立模块（同 R525 手法）。"""
    original = RETRIEVER_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    assert sha_of(RETRIEVER_PATH) == RETRIEVER_BASELINE_SHA, "进刀之前原件就不是原样"
    text = original
    if anchor is not None:
        hits = text.count(anchor)
        assert hits == 1, name + "：锚点在原件里出现 " + str(hits) + " 次，不唯一 ⇒ 这枚反证是空的"
        text = text.replace(anchor, replacement, 1)
        assert text != original, name + "：改了个寂寞"
    module = _load(text, tmp_path, "r648_retriever_" + name, "r648_" + name + ".py")
    assert sha_of(RETRIEVER_PATH) == RETRIEVER_BASELINE_SHA, name + "：反证跑完原件不是原样"
    return module


class Tripwire:
    """量具唯一子进程出口的计数器：默认态响一枚就红（K3 的靶子就是这枚计数）。"""

    def __init__(self, module):
        self.module = module
        self.calls = []

    def install(self):
        self.module.docker_exec = self._fake
        return self

    def _fake(self, argv, **kwargs):
        command = " ".join(str(item) for item in argv)
        self.calls.append(command)
        raise AssertionError("闸门关着却试图连库/发子进程：" + command[:200])

    @property
    def fired(self) -> int:
        return len(self.calls)