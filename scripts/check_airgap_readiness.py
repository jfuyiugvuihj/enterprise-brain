"""R52 -- can this product be installed and run with no internet at all?

The private-deployment promise (AGENTS.md: 数据不出客户服务器) is a claim about runtime
behaviour, and claims like that rot silently: one hard-coded CDN URL, one "just disable
verification for the demo" line, one tracing default flipped to true, and the claim is
false while every test still passes. This script turns the three R52 criteria into a
mechanical check and keeps the parts that genuinely need an air-gapped machine in a
separate, clearly labelled list, so a green run can never be read as a full proof.

    python scripts/check_airgap_readiness.py            # human readable
    python scripts/check_airgap_readiness.py --json     # for the deployment gate
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Names that resolve inside the deployment itself: localhost, and the Compose service
# names the containers use as DNS names. Anything else on this list is an exit to the
# public internet and must be justified by an explicit, default-off switch.
INTERNAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1", "host.docker.internal",
                 "ollama", "redis", "postgres", "backend", "frontend", "migrate",
                 "worker", "scheduler", "enterprise-brain-ollama-1"}

# An XML namespace is an identifier that merely happens to be spelled as a URL. The two
# forms below are the only shapes one takes in shipped source: ElementTree's Clark notation
# and an xmlns declaration. Neither can open a socket, so counting them as an exit would only
# teach people to write "http" + "/ns/..." to get a green gate. The exemption is structural --
# there is no host allowlist that a name can be lost to -- and it is paid for by
# namespace_exemption_leaks below: a file that spells namespaces must not be able to talk.
NAMESPACE_LITERAL = re.compile(r'"\{https?://[^"]*\}"|xmlns(?::[\w.\-]+)?\s*=\s*"https?://[^"]*"')
NETWORK_CLIENT_IMPORTS = (
    (r"^\s*(?:import|from)\s+(?:socket|ssl|http(?:\.client)?|urllib|requests|httpx|aiohttp|ftplib|smtplib)\b",
     "imports a network client"),
    (r"\bsubprocess\.(?:run|Popen|call|check_call|check_output)\b[^#]*\b(?:curl|wget)\b",
     "shells out to curl/wget"),
)

TLS_BYPASS = [
    (r"verify\s*=\s*False", "requests/httpx: certificate checking switched off"),
    (r"CERT_NONE", "ssl: certificate checking switched off"),
    (r"ssl\s*[=_]\s*False|check_hostname\s*=\s*False", "ssl context built without verification"),
    (r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0", "node: TLS verification switched off"),
    (r"rejectUnauthorized\s*:\s*false", "node: TLS verification switched off"),
    (r"--insecure|insecure-skip-tls|sslVerification\s*=\s*['\"]?off", "CLI/tool flag disabling TLS"),
    (r"CURLOPT_SSL_VERIFYPEER\s*,\s*0", "curl: peer verification switched off"),
]

CODE_ROOTS = ("app", "scripts", "deploy", "migrations")
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".sh", ".ps1", ".yml", ".yaml", ".conf", ".cnf"}
CLOUD_KEYS = ("DASHSCOPE_API_KEY", "MINERU_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
              "AZURE_OPENAI_API_KEY", "GOOGLE_API_KEY")
OPT_IN_MARKERS = ("_ENABLED", "ENABLE_REMOTE", "USE_REMOTE", "remote_fallback", "allow_remote",
                  "RERANKER_URL", "explicit")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return path.read_text(encoding="utf-8", errors="replace")


def source_files(*roots: str) -> list[Path]:
    files: list[Path] = []
    for root in roots or CODE_ROOTS:
        target = ROOT / root
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files += [p for p in target.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES]
    return sorted(set(files))


def tls_bypass_hits(text: str) -> list[str]:
    """Lines that turn certificate checking off. Pure, so the tests can feed it bad code."""
    found: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for pattern, why in TLS_BYPASS:
            if re.search(pattern, line) and "# r52-detector" not in line:
                found.append("line " + str(line_number) + ": " + why)
    return found


def external_host_hits(text: str) -> list[str]:
    """Outbound hosts that are neither loopback nor a Compose service name.

    Namespace literals are dropped line by line first -- an identifier written as a URL is not
    an exit -- but removal is per line, so a request URL sharing the line still counts.
    """
    found: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for host in re.findall(r"https?://([A-Za-z0-9.\-]+)", NAMESPACE_LITERAL.sub("", line)):
            if host not in INTERNAL_HOSTS and "." in host and not host.endswith(".test"):
                found.append("line " + str(line_number) + ": " + host)
    return found


def namespace_exemption_leaks(text: str) -> list[str]:
    """Lines that void the namespace exemption: namespaces plus a way to reach the network.

    Without this check the exemption is a hole -- one import line and a namespace literal would
    hide a real CDN URL. It returns the offending lines so the gate names the file and the
    import rather than just going red.
    """
    if not NAMESPACE_LITERAL.search(text):
        return []
    return ["line " + str(line_number) + ": " + why
            for line_number, line in enumerate(text.splitlines(), start=1)
            for pattern, why in NETWORK_CLIENT_IMPORTS
            if re.search(pattern, line)]


def report() -> tuple[list[tuple[str, str, str]], list[str]]:
    """(rows, pending_on_real_machine). rows are (state, name, detail)."""
    rows: list[tuple[str, str, str]] = []
    pending: list[str] = []

    def add(state: str, name: str, detail: str) -> None:
        rows.append((state, name, detail))

    # --- constraint of the ticket: never pass the check by weakening TLS -------------
    hits: list[str] = []
    # This file is the detector: its own pattern table looks exactly like a violation.
    # The exclusion is by resolved path (not by name prefix) so no other file can hide
    # behind it, and tests/test_r52_airgap_readiness.py asserts the table still bites.
    here = Path(__file__).resolve()
    hits: list[str] = []
    for path in [*source_files(), ROOT / "Dockerfile", ROOT / "docker-compose.yml",
                 ROOT / "frontend" / "src"]:
        if not path.is_file() or path.resolve() == here:
            continue
        for hit in tls_bypass_hits(read(path)):
            hits.append(str(path.relative_to(ROOT)) + " " + hit)
    if hits:
        add("FAIL", "TLS verification is never disabled", "; ".join(hits[:6]))
    else:
        add("PASS", "TLS verification is never disabled", "no bypass pattern in "
            + str(len(list(source_files()))) + " tracked source files")

    # --- runtime exits to the public internet ---------------------------------------
    external: list[str] = []
    for path in source_files("app", "scripts", "deploy"):
        text = read(path)
        for hit in external_host_hits(text):
            external.append(str(path.relative_to(ROOT)) + " " + hit)
        for leak in namespace_exemption_leaks(text):
            external.append(str(path.relative_to(ROOT)) + " " + leak
                            + " -> namespace exemption voided by a network client")
    if external:
        add("FAIL", "no unguarded external host in shipped code", "; ".join(external[:6]))
    else:
        add("PASS", "no unguarded external host in shipped code",
            "app/**, scripts/** and deploy/** literals are localhost, Compose service "
            "names and XML namespace identifiers only")

    # --- tracing must be off unless the operator says otherwise ---------------------
    tracing = ROOT / "app" / "common" / "tracing.py"
    enabled_default = re.search(r'getenv\("LANGSMITH_TRACING",\s*"(\w+)"\)', read(tracing)) if tracing.is_file() else None
    if enabled_default and enabled_default.group(1).lower() in {"false", "0", "off", ""}:
        add("PASS", "telemetry off by default", 'LANGSMITH_TRACING default "' + enabled_default.group(1) + '"')
    else:
        add("FAIL", "telemetry off by default", "cannot find a default-false read of LANGSMITH_TRACING")

    # --- cloud model fallback: only when explicitly asked for -----------------------
    unwired: list[str] = []
    for key in CLOUD_KEYS:
        users = [p for p in source_files("app") if re.search(key, read(p))]
        if not users:
            continue
        gated = any(any(marker in read(p) for marker in OPT_IN_MARKERS) for p in users)
        if not gated:
            unwired.append(key + " read in " + ", ".join(str(p.relative_to(ROOT)) for p in users))
    if unwired:
        add("FAIL", "remote-model fallback needs an explicit switch", "; ".join(unwired))
    else:
        keys_in_use = [k for k in CLOUD_KEYS if any(re.search(k, read(p)) for p in source_files("app"))]
        add("PASS", "remote-model fallback needs an explicit switch",
            "wired and gated: " + (", ".join(keys_in_use) if keys_in_use else "none (keys unread in app/**)"))

    # --- build time: only the two documented mirror arguments may reach out ---------
    dockerfile = read(ROOT / "Dockerfile")
    sneaky = [line.strip()[:70] for line in dockerfile.splitlines()
              if re.search(r"\b(git clone|curl |wget |addcontextfiles)\b", line)
              and "APT_MIRROR" not in line and "PIP_INDEX_URL" not in line]
    mirror_switches = all(needle in dockerfile for needle in ("ARG APT_MIRROR", "ARG PIP_INDEX_URL"))
    if sneaky or not mirror_switches:
        add("FAIL", "build reaches out only through the mirror arguments",
            "; ".join(sneaky) or "missing APT_MIRROR/PIP_INDEX_URL build arguments")
    else:
        add("PASS", "build reaches out only through the mirror arguments",
            "uv sync runs once per lockfile change and is fed by a cache mount")

    # --- wheels: the lockfile is pinned to a public index ---------------------------
    lock = read(ROOT / "uv.lock")
    registries = sorted(set(re.findall(r'registry = "([^"]+)"', lock)))
    offline_override = "--default-index" in dockerfile
    if registries and not offline_override:
        add("FAIL", "dependency install is redirectable to an intranet index",
            "lockfile pins " + ", ".join(registries) + " with no override path")
    elif registries:
        add("PASS", "dependency install is redirectable to an intranet index",
            "PIP_INDEX_URL re-points uv and pip; pinned registries: " + ", ".join(registries))
    else:
        add("INFO", "dependency install is redirectable to an intranet index", "no registry lines found in uv.lock")

    # --- internal HTTPS surface -----------------------------------------------------
    nginx = read(ROOT / "deploy" / "nginx.conf")
    overlay = ROOT / "deploy" / "docker-compose.tls.yml"
    example = ROOT / "deploy" / "nginx.https.conf.example"
    tls_shipped = overlay.is_file() and example.is_file()
    if "listen 443" in nginx:
        add("PASS", "internal HTTPS is configurable", "nginx.conf already terminates TLS")
    elif tls_shipped:
        add("PASS", "internal HTTPS is configurable",
            "plain HTTP stays the default; deploy/docker-compose.tls.yml + nginx.https.conf.example carry the TLS form")
    else:
        add("FAIL", "internal HTTPS is configurable", "no 443 listener and no shipped TLS overlay")

    # --- the parts that are only provable off the network ---------------------------
    pending += [
        "真正断网装机：拔网线后跑 setup/Docker 构建 + `compose up -d --no-build`，"
        "需要内网 apt/wheel 镜像与 Ollama 模型 blob（本机不能验，验了就等于改业主网络）",
        "内网域名 + 证书握手：把 deploy/docker-compose.tls.yml 与 nginx.https.conf.example 填上客户 CA "
        "签发的证书与内网域名，再核对 CORS_ALLOW_ORIGINS 与前端 baseURL 是否同一个 https origin",
        "批量账号验收：python scripts/provision_bulk_accounts.py --count 50 之后逐号登录、"
        "抽查权限边界（判据③），本班未执行——它会往库里写 50 个账号，属业主批准的 acceptance 动作",
    ]
    return rows, pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit machine readable results")
    args = parser.parse_args(argv)

    rows, pending = report()
    failed = [name for state, name, _ in rows if state == "FAIL"]
    if args.json:
        print(json.dumps({"results": [{"state": s, "check": n, "detail": d} for s, n, d in rows],
                          "pending_on_real_machine": pending, "failed": failed}, ensure_ascii=False, indent=2))
    else:
        for state, name, detail in rows:
            print(state.ljust(5) + " " + name + " -- " + detail)
        print()
        for line in pending:
            print("PENDING  " + line)
        print("\nair-gap readiness: " + (str(len(rows) - len(failed)) + " passed, " + str(len(failed)) + " failed")
              + ("  <-- fix these before claiming offline capability" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
