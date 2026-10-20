#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R581（10-03）：GPU 计算进程的「三分归因」真源 —— 影子 → 容器 → 计算 pid 同名同槽。

为什么要有这一枚
----------------
在册开窗前置闸 `scripts/r530_run10_window_preflight.py` 的 `gpu_apps` 那一格，改前只有
一条判据：nvidia-smi 报的计算进程里只要有一枚可执行文件不在仓库里就 FAIL。本机（Windows +
Docker Desktop vGPU）的真实形状是：**容器里跑的 llama-server 在宿主侧一律显示为
`4, [Insufficient Permissions]`（pid=4）**，而 pid=4 是 Windows System，这台机上它永远在
—— 只要模型载进显存，那一格就永远红。于是队列 v2（`%TEMP%\eb-rescue\R570\queue_v2.py`，
10-02 23:2x）给同一件事另写了一套判定，10-03 00:21–00:26 连吃六轮 REFUSE 就是它在干的活。
AGENTS.md 明令不许复制平行实现 —— 本单把那套已验证的姿势**收进在册件**，真源只写在这一枚
文件里，别的调用点改调它（`attribute(state)` 交回 (状态, 读数) 两元组）。

🔴 不许往「看起来不像负载」退
--------------------------
放行必须逐枚交出四腿，少一条就红：

  L1 影子      宿主侧这一行 process_name 读不出（`[Insufficient Permissions]` 一类），且这个
               pid 能在宿主进程表里点到名，且点到的名字在宿主代理名册里（system 等）；若它反而
               解析出一枚仓库外的可执行文件、或读到名册外的进程名 —— FOREIGN（影子不是自家的）。
  L2 容器      目标容器在 `docker ps` 里点得到，且容器内 `nvidia-smi` 跑通（rc=0）。
               docker 问不到 rc —— UNMEASURED；docker 问得到但没有在跑的 ollama 容器 —— FOREIGN（无人认领）。
  L3 同槽      每一枚影子行的 `gpu_uuid` 必须出现在容器侧计算进程的 `gpu_uuid` 集合里。
               字段读空 —— UNMEASURED（不许拿「大概是同一张卡」放行）；容器侧不认领这个槽 —— FOREIGN。
  L4 同名      同槽那一格上容器侧必须能**叫出**至少一枚计算进程的名字：nvidia-smi 直接给名，或容器内
               `/proc/<pid>/exe` 解析出可执行文件。本机 10-03 现取：容器侧 nvidia-smi 自己也只会
               报 `[Not Found]`，名字只能靠 `/proc` 补 —— 所以 `/proc/<pid>/exe` 才是「同名」的真凭据。

四态与「问不到」
--------------
  CLEAN        宿主侧零计算行，或全部属于本仓/本栈 —— 没有需要归因的东西
  ATTRIBUTED   有匿名影子行，且 L1–L4 逐腿通过（读数里逐腿点名）
  FOREIGN      可解析名却不属于本仓/本栈的计算行；或影子行的槽位容器侧不认领（容器不在场／容器侧
               零计算行／槽位不符／影子 pid 反解出一枚仓库外可执行文件）—— 即「真有人在抢 GPU」
  UNMEASURED   任何一条腿问不到：nvidia-smi 跑不成、宿主进程表读不到该 pid、docker 不可达、容器内
               nvidia-smi 非零、`gpu_uuid` 字段为空、容器侧一枚名字都叫不出
FOREIGN 与 UNMEASURED 一律拦窗（调用方 P-20 把两者映射成 FAIL）。🔴 「问不到」绝不写进 CLEAN，
也不许当成「没有」—— 与本仓 09-28「两班假零」同源的教训。

本机现取（10-03 10:0x，模型在显存里时的真形状，逐字；全程只读 `nvidia-smi`／`docker exec`）：
  宿主   4, [Insufficient Permissions], GPU-0e7f33ad-cc4a-7a1a-e9a4-7dd69f9032ab, [N/A]
  容器   50983, [Not Found], GPU-0e7f33ad-cc4a-7a1a-e9a4-7dd69f9032ab, [N/A]
         51023, [Not Found], GPU-0e7f33ad-... （同槽）
         readlink /proc/50983/exe -> /usr/lib/ollama/llama-server
  宿主进程表现取：ProcessId=4 -> Name=System，ExecutablePath 空
  => `used_memory` 本机恒为 `[N/A]`（WDDM），所以归因不拿显存做凭据，槽位只认 `gpu_uuid`。

🔴 本格不治任何时延读数：ATTRIBUTED 只证「占卡的是自家容器」，不证「这一窗干净」，
A(1)／A(4) 不许因为本格变绿。

离线可测：`classify()` 是纯函数，读数由 `collect()` 注进来，测试里不碰 docker／nvidia-smi。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CLEAN = "CLEAN"
ATTRIBUTED = "ATTRIBUTED"
FOREIGN = "FOREIGN"
UNMEASURED = "UNMEASURED"
#: 拦窗的两态；调用方（P-20）把它们映射成 FAIL，CLEAN/ATTRIBUTED 映射成 PASS
BLOCKING = (FOREIGN, UNMEASURED)
#: 放行用的两态（调用方映射成 PASS）；P-20 之外的一切调用点都照这一对判，别自己写第二套
PASSING = (CLEAN, ATTRIBUTED)
#: nvidia-smi 读不出进程名时交回的占位符（本机实测两枚：宿主 [Insufficient Permissions]、容器 [Not Found]）
UNREADABLE_NAMES = ("[insufficient permissions]", "[not found]", "[unknown]", "[n/a]", "[none]", "")
#: L1 允许把影子归给谁。本机 10-03 现取只有 System 这一枚是被证过的；其余是 Docker Desktop 在同一
#: 台机上会充当 vGPU 宿主代理的服务进程名。**名册外一律 FOREIGN**（宁可红，不许凭「看着像服务」放行）。
SHADOW_HOST_OWNERS = ("system", "vmmem", "vmmemcompute", "com.docker.backend.exe")

NVIDIA_QUERY_FIELDS = "pid,process_name,gpu_uuid,used_memory"
NVIDIA_CMD = ["nvidia-smi", "--query-compute-apps=" + NVIDIA_QUERY_FIELDS, "--format=csv,noheader"]
DOCKER_PS_CMD = ["docker", "ps", "--format", "{{.Names}}"]
OLLAMA_CONTAINER_ENV = "R581_OLLAMA_CONTAINER"
OLLAMA_CONTAINER_DEFAULT = "enterprise-brain-ollama-1"
OLLAMA_HINT = "ollama"
#: 🔴 宿主行的「自家」只认**树名册**（这棵树／主树／跑分树），不认 ollama 一类松散文件名：
#: 一枚装在 D:``ollama 的宿主原生 ollama.exe 与自家容器无关，一样是 FOREIGN。
#: 容器侧解析出来的 /usr/lib/ollama/llama-server 只作 L4 的点名凭据，不参与宿主行的所有权判定。
REPO_TREE_SIBLINGS = ("企业智脑", "be-eval95")
PS_PROCESS_BY_ID = ("Get-CimInstance Win32_Process -Filter @F"
                    " | Select-Object Name,ExecutablePath | ConvertTo-Json -Compress")


def repo_tokens():
    """自家三棵树的绝对路径（小写）：这棵工作树、主树、跑分树。问不到 Nothing——空串一律不算自家。"""
    tokens = [str(ROOT).lower()]
    tokens += [str(ROOT.parent / sibling).lower() for sibling in REPO_TREE_SIBLINGS]
    return tuple(dict.fromkeys([token for token in tokens if token]))


def is_repo_path(path_text):
    text = str(path_text or "").lower()
    return bool(text) and any(token in text for token in repo_tokens())


@dataclass
class ComputeRow:
    pid: str = ""
    exe: str = ""
    gpu_uuid: str = ""
    used_memory: str = ""
    source: str = "host"

    @property
    def anonymous(self):
        return str(self.exe).strip().lower() in UNREADABLE_NAMES

    def label(self):
        return "pid=" + str(self.pid) + " exe=" + str(self.exe) + " 槽=" + (str(self.gpu_uuid) or "<空>")


@dataclass
class HostProcess:
    pid: str = ""
    name: str = ""
    exe_path: str = ""
    resolved: bool = False


@dataclass
class ContainerState:
    requested: str = OLLAMA_CONTAINER_DEFAULT
    name: str = ""
    docker_ok: bool = False
    running: bool = False
    query_ok: bool = False
    rows: list = field(default_factory=list)
    exe_names: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


@dataclass
class GpuState:
    host_rows: list = field(default_factory=list)
    host_seen: bool = False
    host_note: str = ""
    host_processes: dict = field(default_factory=dict)
    container: object = None


@dataclass
class Leg:
    ident: str
    ok: bool
    text: str


@dataclass
class Verdict:
    status: str
    detail: str
    legs: list = field(default_factory=list)

    @property
    def blocking(self):
        return self.status in BLOCKING


def default_run(cmd, timeout=180):
    """只读命令的统一出口：rc=0 才算问到了，跑不成一律 rc=2（调用方据此落 UNMEASURED）。"""
    try:
        done = subprocess.run([str(part) for part in cmd], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, type(exc).__name__ + ": " + str(exc)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def parse_rows(text, source="host"):
    rows = []
    for cells in csv.reader(io.StringIO(text or "")):
        clean = [str(cell).strip().strip(chr(34)).strip() for cell in cells]
        if len(clean) < 2 or not clean[0]:
            continue
        rows.append(ComputeRow(pid=clean[0], exe=clean[1],
                               gpu_uuid=clean[2] if len(clean) > 2 else "",
                               used_memory=clean[3] if len(clean) > 3 else "", source=source))
    return rows


def as_rows(value, source="host"):
    rows = []
    for item in (value or []):
        if isinstance(item, ComputeRow):
            rows.append(item)
            continue
        name = item.get("exe", item.get("process_name", ""))
        rows.append(ComputeRow(pid=str(item.get("pid", "")), exe=str(name or ""),
                               gpu_uuid=str(item.get("gpu_uuid", "") or ""),
                               used_memory=str(item.get("used_memory", "") or ""),
                               source=item.get("source", source)))
    return rows


def read_host_process(pid, run=default_run):
    """影子 pid 在宿主进程表里到底是谁。读不到就 resolved=False —— L1 落 UNMEASURED，不许当「没人」。"""
    script = PS_PROCESS_BY_ID.replace("@F", chr(34) + "ProcessId=" + str(pid) + chr(34))
    code, out = run(["powershell", "-NoProfile", "-Command", script])
    text = (out or "").strip()
    if code != 0 or not text:
        return HostProcess(str(pid), "", "", False)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return HostProcess(str(pid), "", "", False)
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return HostProcess(str(pid), "", "", False)
    name = str(data.get("Name") or "").strip()
    exe_path = str(data.get("ExecutablePath") or "").strip()
    return HostProcess(str(pid), name, exe_path, bool(name) or bool(exe_path))


def read_container_state(run=default_run, container=None):
    """L2–L4 的读数：容器在不在场、容器内 nvidia-smi 点到了谁、那些 pid 能不能叫出名字。"""
    requested = container or os.environ.get(OLLAMA_CONTAINER_ENV) or OLLAMA_CONTAINER_DEFAULT
    state = ContainerState(requested=requested)
    code, out = run(DOCKER_PS_CMD)
    state.docker_ok = code == 0
    names = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if not state.docker_ok:
        state.notes.append("docker ps rc=" + str(code) + "（问不到）")
        return state
    chosen = requested if requested in names else ""
    if not chosen:
        chosen = next((line for line in names if OLLAMA_HINT in line.lower()), "")
    if not chosen:
        state.notes.append("docker ps 在册 " + str(len(names)) + " 枚容器里没有 " + OLLAMA_HINT
                           + "（问得到，答案是没有）")
        return state
    state.name = chosen
    state.running = True
    code, out = run(["docker", "exec", chosen, "nvidia-smi",
                     "--query-compute-apps=" + NVIDIA_QUERY_FIELDS, "--format=csv,noheader"])
    state.query_ok = code == 0
    if not state.query_ok:
        state.notes.append("容器内 nvidia-smi rc=" + str(code) + "（问不到）")
        return state
    state.rows = parse_rows(out, "container")
    for row in state.rows:
        if not row.pid.isdigit():
            continue
        exe_code, exe_out = run(["docker", "exec", chosen, "readlink", "/proc/" + row.pid + "/exe"])
        target = str((exe_out or "").strip().splitlines()[0] if (exe_out or "").strip() else "").strip()
        if exe_code == 0 and target:
            state.exe_names[row.pid] = target
    return state


def collect(run=default_run, container=None):
    """现取一枚 GpuState（只在真有匿名影子时才追加 docker／进程表取证 —— 干净机上零额外开销）。"""
    code, out = run(NVIDIA_CMD)
    state = GpuState(host_rows=parse_rows(out), host_seen=(code == 0),
                     host_note="" if code == 0 else "nvidia-smi rc=" + str(code))
    shadows = [row for row in state.host_rows if row.anonymous]
    if state.host_seen and shadows:
        state.host_processes = dict((row.pid, read_host_process(row.pid, run)) for row in shadows)
        state.container = read_container_state(run, container)
    return state


def classify(state):
    """三分法真源：给定读数交回 CLEAN／ATTRIBUTED／FOREIGN／UNMEASURED。纯函数，不起进程。"""
    rows = as_rows(state.host_rows)
    if not state.host_seen:
        return Verdict(UNMEASURED, UNMEASURED + "｜nvidia-smi 问不到（"
                       + (state.host_note or "rc 非零")
                       + "）—— 问不到既不能算没人占卡，也不能算干净", [])
    foreign = [row for row in rows if not row.anonymous and not is_repo_path(row.exe)]
    ours = [row for row in rows if not row.anonymous and is_repo_path(row.exe)]
    shadows = [row for row in rows if row.anonymous]

    if foreign:
        return Verdict(FOREIGN, FOREIGN + "｜外来计算进程 " + str(len(foreign)) + " 枚占着 GPU："
                       + "；".join(row.label() for row in foreign)
                       + "。A(1) 的 p95 时延读数不可采信（改前的默认行为，本格不许放松）", [])
    if not shadows:
        if not rows:
            return Verdict(CLEAN, CLEAN + "｜GPU 计算进程 0 枚（nvidia-smi rc=0 点名零枚），"
                           "没有匿名影子需要归因。本格只证此刻占卡表为空，不证任何时延读数", [])
        return Verdict(CLEAN, CLEAN + "｜GPU 计算进程 " + str(len(rows)) + " 枚，全部属本仓/本栈（"
                       + "；".join(row.label() for row in ours) + "），零枚匿名影子。不证任何时延读数", [])

    legs = []
    unasked = []
    impostors = []
    named = []
    for row in shadows:
        proc = (state.host_processes or {}).get(row.pid)
        if proc is None or not proc.resolved:
            unasked.append(row.pid)
            continue
        lowered = str(proc.name).lower()
        if lowered.startswith(SHADOW_HOST_OWNERS):
            named.append("pid=" + row.pid + " name=" + proc.name + "＝名册内宿主代理")
            continue
        if is_repo_path(proc.exe_path):
            named.append("pid=" + row.pid + " exe=" + proc.exe_path
                         + "（nvidia-smi 读不出名，宿主进程表读到它在自家树里）")
            continue
        if proc.exe_path:
            impostors.append("pid=" + row.pid + " 反解出仓库外可执行文件 " + proc.exe_path)
            continue
        impostors.append("pid=" + row.pid + " 名字不在宿主代理名册（读到 " + (proc.name or "<空>") + "）")
    if impostors:
        legs.append(Leg("L1", False, "L1 影子｜" + "；".join(impostors)))
        return Verdict(FOREIGN, FOREIGN + "｜匿名影子反解出了别人：" + "；".join(impostors)
                       + " —— 这不是自家 vGPU 影子，A(1) 读数不可采信", legs)
    if unasked:
        legs.append(Leg("L1", False, "L1 影子｜宿主进程表读不到 pid=" + ",".join(unasked) + "（问不到）"))
        return Verdict(UNMEASURED, UNMEASURED + "｜L1 问不到：影子 pid=" + ",".join(unasked)
                       + " 在宿主进程表里点不到名 —— 不能拿「大概还是那枚影子」放行", legs)
    legs.append(Leg("L1", True, "L1 影子＝" + "；".join(named) + "（宿主进程表现取）"))

    container = state.container
    if container is None:
        legs.append(Leg("L2", False, "L2 容器｜没取证"))
        return Verdict(UNMEASURED, UNMEASURED + "｜L2 没取证：影子在位却没查过容器侧 —— 问不到不等于没有", legs)
    if not container.docker_ok:
        legs.append(Leg("L2", False, "L2 容器｜docker ps 问不到（" + "；".join(container.notes) + "）"))
        return Verdict(UNMEASURED, UNMEASURED + "｜L2 问不到：docker ps 跑不成（"
                       + "；".join(container.notes) + "）", legs)
    if not container.running:
        legs.append(Leg("L2", False, "L2 容器｜没有在跑的 " + OLLAMA_HINT + " 容器（" + "；".join(container.notes) + "）"))
        return Verdict(FOREIGN, FOREIGN + "｜匿名影子无人认领：docker 问得到，但在册容器里没有 "
                       + OLLAMA_CONTAINER_DEFAULT + " 一类的容器（" + "；".join(container.notes)
                       + "）—— 占卡的不是自家容器，不开窗", legs)
    if not container.query_ok:
        legs.append(Leg("L2", False, "L2 容器｜容器内 nvidia-smi 问不到（" + "；".join(container.notes) + "）"))
        return Verdict(UNMEASURED, UNMEASURED + "｜L2 问不到：" + OLLAMA_HINT
                       + " 容器在跑但容器内 nvidia-smi 非零（" + "；".join(container.notes) + "）", legs)
    legs.append(Leg("L2", True, "L2 容器＝" + container.name + " 在跑，容器内 nvidia-smi rc=0"))

    container_rows = as_rows(container.rows, "container")
    shadow_slots = [row.gpu_uuid for row in shadows]
    if any(not slot for slot in shadow_slots):
        legs.append(Leg("L3", False, "L3 同槽｜影子行缺 gpu_uuid（"
                        + "；".join(row.label() for row in shadows) + "）"))
        return Verdict(UNMEASURED, UNMEASURED + "｜L3 问不到：影子行没有 gpu_uuid 字段 —— "
                       "拿「同一台机」当「同一张卡」是猜，不是归因", legs)
    if not container_rows:
        legs.append(Leg("L3", False, "L3 同槽｜容器侧点名 0 枚计算进程"))
        return Verdict(FOREIGN, FOREIGN + "｜匿名影子无人认领：" + container.name
                       + " 容器内 nvidia-smi 点名 0 枚计算进程，而宿主有 " + str(len(shadows))
                       + " 枚匿名行（" + "；".join(row.label() for row in shadows)
                       + "）—— 归因不成立，不开窗", legs)
    container_slots = set(row.gpu_uuid for row in container_rows)
    unclaimed = [row.label() for row in shadows if row.gpu_uuid not in container_slots]
    if unclaimed:
        legs.append(Leg("L3", False, "L3 同槽｜容器侧不认领槽 " + "；".join(unclaimed)))
        return Verdict(FOREIGN, FOREIGN + "｜非容器所有的计算 pid：宿主匿名行的槽 " + "；".join(unclaimed)
                       + " 不在 " + container.name + " 的槽集合 " + ",".join(sorted(container_slots))
                       + " 里 —— 有人在自家容器外占卡，不开窗", legs)
    legs.append(Leg("L3", True, "L3 同槽＝影子槽 " + ",".join(sorted(set(shadow_slots)))
                    + " 容器侧在册（容器侧计算进程 " + str(len(container_rows)) + " 枚）"))

    slot_set = set(shadow_slots)
    on_slot = [row for row in container_rows if row.gpu_uuid in slot_set]
    nameable = [row for row in on_slot
                if (not row.anonymous) or str(row.pid) in (container.exe_names or {})]
    if not nameable:
        legs.append(Leg("L4", False, "L4 同名｜容器侧同槽 " + str(len(on_slot)) + " 枚一律叫不出名字"))
        return Verdict(UNMEASURED, UNMEASURED + "｜L4 问不到：" + container.name + " 同槽点名了 "
                       + str(len(on_slot)) + " 枚计算进程，但 nvidia-smi 与 /proc/<pid>/exe 都叫不出名字"
                       " —— 无名占卡不能算自家影子", legs)
    proof = "；".join("pid=" + row.pid + " -> " + str((container.exe_names or {}).get(row.pid, row.exe))
                      for row in nameable)
    legs.append(Leg("L4", True, "L4 同名＝" + proof))
    return Verdict(ATTRIBUTED, ATTRIBUTED + "｜匿名影子 " + str(len(shadows)) + " 枚已按四腿归给 "
                   + container.name + "（Docker Desktop vGPU 的宿主代理影子）："
                   + " ／ ".join(leg.text for leg in legs)
                   + " ／ 🔴 本格只证「占卡的是自家容器」，不证时延干净，A(1)／A(4) 不许因此翻绿", legs)


def attribute(state):
    """给调用方的两元组出口：(状态, 读数)。P-20 与后续所有调用点都走这一枚，别再自己判。"""
    verdict = classify(state)
    return verdict.status, verdict.detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="逐枚输出四腿")
    parser.add_argument("--container", default=None,
                        help="ollama 容器名（缺省 " + OLLAMA_CONTAINER_DEFAULT + "）")
    opts = parser.parse_args(argv)
    verdict = classify(collect(container=opts.container))
    if opts.json:
        print(json.dumps({"status": verdict.status, "blocking": verdict.blocking,
                          "detail": verdict.detail,
                          "legs": [{"leg": leg.ident, "ok": leg.ok, "text": leg.text}
                                   for leg in verdict.legs]}, ensure_ascii=False, indent=2))
    else:
        print("[R581] " + verdict.detail)
    if verdict.status in (CLEAN, ATTRIBUTED):
        return 0
    return 2 if verdict.status == UNMEASURED else 1


if __name__ == "__main__":
    sys.exit(main())
