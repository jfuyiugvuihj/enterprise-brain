"""R201 - the two flat document routes and the contract paragraph about them.

``GET /api/v1/documents`` and ``GET /api/v1/documents/catalog`` answer a listing request with a
``restricted`` tally (R194). Until today the paragraph that promises it was prose no test read: a
route could grow, drop or rename a key and the contract would not turn red. This file compares that
paragraph with the AST of the construction sites, in both directions - one key too many in the
contract is red, one key too few is red, a renamed key is red, and so is a route that quietly grows
a query parameter the paragraph says does not exist.

Method borrowed from ``test_r186_row_scope_contract.py`` and ``test_r191_hitl_contract_pins.py``:
locate a ``## `` section by heading, split its ``### `` subheads, read a markdown key table, rebuild
an f-string into a template, compute an endpoint from the route decorator plus the prefix mounted
in ``app/main.py``. None of their assertions are copied, and nothing here is transcribed by hand -
every key list, element type, guard name and sentence is read out of ``app/api/v1/chat.py`` or
``app/documents/catalog.py`` at run time. Fully static: no server, no database, no model.

Why the paragraph lives in its own ``## `` section rather than as a third ``### `` subhead under
``## Dataset Row-Level Visibility``: that section's subhead set is pinned by R186, and a third
subhead there would have to argue why it is not speaking for the other field. Writing the document
contract in a region R186 does not read needs no such argument: this file opens no existing pin and
adds no pin to somebody else's grid.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "api" / "contract-v1.md"
CHAT_PY = ROOT / "app" / "api" / "v1" / "chat.py"
CATALOG_PY = ROOT / "app" / "documents" / "catalog.py"
MAIN_PY = ROOT / "app" / "main.py"
POLICY_PY = ROOT / "app" / "documents" / "index_policy.py"
RUNBOOK = ROOT / "docs" / "handoff" / "2026-09-17-eval-real-run-runbook.md"

SECTION_HEADING = "## Document Catalog Visibility"
NEIGHBOUR_HEADING = "## Dataset Row-Level Visibility"
FLAT_SUBHEAD = "`GET /api/v1/documents` -> body"
CATALOG_SUBHEAD = "`GET /api/v1/documents/catalog` -> body"
RESTRICTED_SUBHEAD = "`restricted` -> the one shared projection"
ROWS_SUBHEAD = "`GET /api/v1/documents/catalog` -> `documents[]` rows"
SUBHEADS = {FLAT_SUBHEAD, CATALOG_SUBHEAD, RESTRICTED_SUBHEAD, ROWS_SUBHEAD}

FLAT_ROUTE = "list_documents"
CATALOG_ROUTE = "list_document_catalog"
PROJECTION = "_restricted_summary"
SERIALIZER = "public_document_row"
VERBS = {"get", "post", "put", "delete"}
CONTRACT_PHRASE = "discarded by the framework, not honoured"


def _text(path: Path) -> str:
    assert path.exists(), "%s is gone" % path.relative_to(ROOT)
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _tree(source: str) -> ast.Module:
    return ast.parse(source)


def _flat(text: str) -> str:
    """Fold markdown line wrapping: an anchor is a sentence, not one source line."""
    return re.sub(r"\s+", " ", text)


def _heading(body: str, heading: str) -> int:
    """A heading is a line that starts with it: a cross-reference elsewhere must not count."""
    match = re.search(r"(?m)^%s" % re.escape(heading), body)
    assert match, "the contract has no %r section: renaming it renames this pin" % heading
    return match.start()


def _section(contract: str | None = None) -> str:
    body = _text(CONTRACT) if contract is None else contract
    start = _heading(body, SECTION_HEADING)
    tail = body[start + len(SECTION_HEADING):]
    end = re.search(r"^## ", tail, re.MULTILINE)
    section = body[start:start + len(SECTION_HEADING) + (end.start() if end else len(tail))]
    assert len(section) > 3000, "this section is too short for the pins below to have anything to read"
    return section


def _split(section: str) -> dict[str, str]:
    chunks = re.split(r"^### ", section, flags=re.MULTILINE)
    out: dict[str, str] = {}
    for chunk in chunks[1:]:
        head, _, body = chunk.partition("\n")
        out[head.strip()] = body
    assert set(out) == SUBHEADS, "the subheads of this section changed: %s" % sorted(out)
    return out


def _subsections(contract: str | None = None) -> dict[str, str]:
    return _split(_section(contract))


def _table(body: str) -> list[tuple[str, str, str, str]]:
    rows = re.findall(
        r"^\|\s*`([a-z_]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$",
        body,
        re.MULTILINE,
    )
    assert rows, "no key table here: the key pins would be an empty echo"
    return rows


def _table_keys(body: str) -> list[str]:
    return [key for key, _type, _presence, _meaning in _table(body)]


def _presence(rows: list[tuple[str, str, str, str]]) -> tuple[list[str], list[str]]:
    required, optional = [], []
    for key, _type, cell, _meaning in rows:
        if cell == "always":
            required.append(key)
        elif cell.startswith("only when"):
            optional.append(key)
        else:
            raise AssertionError(
                "presence of %r says %r: it must say always, or only when something is true" % (key, cell)
            )
    return required, optional


def _cell(body: str, key: str) -> tuple[str, str, str]:
    for name, type_cell, presence, meaning in _table(body):
        if name == key:
            return type_cell, presence, meaning
    raise AssertionError("the table does not carry %r at all" % key)


def _fences(body: str) -> list[dict]:
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", body, re.DOTALL)]


def _json_blocks(body: str) -> list[dict]:
    blocks = _fences(body)
    assert blocks, "no JSON example here: the shape is not pinned down"
    return blocks


# ============================ the code side, read by AST ============================


def _function(source: str, name: str) -> ast.AST:
    found = [
        node for node in ast.walk(_tree(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, "%s should appear exactly once, found %d" % (name, len(found))
    return found[0]


def _route_of(fn: ast.AST) -> tuple[str, str, list[str]]:
    routes, keywords = [], []
    for decorator in fn.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if decorator.func.attr in VERBS and decorator.args:
                path = decorator.args[0]
                assert isinstance(path, ast.Constant), "the route path is no longer a literal"
                routes.append((decorator.func.attr, str(path.value)))
                keywords.extend(str(kw.arg) for kw in decorator.keywords or [])
    assert len(routes) == 1, "this pin reads one route at a time, found %d" % len(routes)
    return routes[0][0], routes[0][1], keywords


def _mounted_prefix(module: str, router: str) -> str:
    for node in ast.walk(_tree(module)):
        if (
            isinstance(node, ast.Call)
            and ast.unparse(node.func).endswith("include_router")
            and node.args
            and ast.unparse(node.args[0]) == router
        ):
            for keyword in node.keywords or []:
                if keyword.arg == "prefix":
                    assert isinstance(keyword.value, ast.Constant), "the mount prefix is no longer a literal"
                    return str(keyword.value.value)
    raise AssertionError("%s is no longer mounted with a literal prefix" % router)


def _endpoint(chat: str, name: str, module: str) -> str:
    method, path, _keywords = _route_of(_function(chat, name))
    return "%s %s%s" % (method.upper(), _mounted_prefix(module, "chat.router"), path)


def _writes(node: ast.AST, into: str) -> list[tuple[str, ast.expr]]:
    """Assignments of the form ``<into>["key"] = value`` inside a subtree."""
    found = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Assign) and isinstance(inner.targets[0], ast.Subscript):
            subscript = inner.targets[0]
            if isinstance(subscript.value, ast.Name) and subscript.value.id == into:
                if isinstance(subscript.slice, ast.Constant):
                    found.append((str(subscript.slice.value), inner.value))
    return found


def _envelope(chat: str, name: str) -> dict:
    """What one flat list route builds, under which guard, out of which call."""
    fn = _function(chat, name)
    params = [arg.arg for arg in fn.args.args] + [arg.arg for arg in fn.args.kwonlyargs]
    built: dict[str, ast.expr] = {}
    for node in ast.walk(fn):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
        if isinstance(node.value, ast.Dict) and isinstance(target, ast.Name):
                for key, value in zip(node.value.keys, node.value.values):
                    assert isinstance(key, ast.Constant), "a response key is no longer a literal string"
                    built[str(key.value)] = value
    guarded: dict[str, tuple[str, ast.expr]] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
            for key, value in _writes(node, "result"):
                guarded[key] = (node.test.id, value)
    every = dict(_writes(fn, "result"))
    assert set(every) == set(guarded), (
        "a key is attached to the answer outside any guard: %s" % sorted(set(every) - set(guarded))
    )
    assert not (set(built) & set(guarded)), "%s is built both always and conditionally" % sorted(
        set(built) & set(guarded)
    )
    returns = [node for node in fn.body if isinstance(node, ast.Return)]
    assert len(returns) == 1, "the route has more than one exit: this pin cannot read its shape"
    assert isinstance(returns[0].value, ast.Name), "the route no longer returns the dict it built"
    return {
        "params": params,
        "required": list(built),
        "values": built,
        "optional": list(guarded),
        "guards": guarded,
    }


def _projection(chat: str) -> dict:
    fn = _function(chat, PROJECTION)
    returns = [node for node in ast.walk(fn) if isinstance(node, ast.Return)]
    assert len(returns) == 1, "%s should return exactly one dict" % PROJECTION
    assert isinstance(returns[0].value, ast.Dict), "%s no longer returns a literal dict" % PROJECTION
    fields = {str(key.value): value for key, value in zip(returns[0].value.keys, returns[0].value.values)}
    message = fields["message"]
    assert isinstance(message, ast.JoinedStr), "restricted.message is no longer an interpolated sentence"
    template = ""
    for part in message.values:
        if isinstance(part, ast.Constant):
            template += str(part.value)
        elif isinstance(part, ast.FormattedValue):
            assert ast.unparse(part.value) == ast.unparse(fields["count"]), (
                "the number inside the sentence is not the number in the count field"
            )
            template += "{count}"
        else:
            raise AssertionError("unreadable node inside restricted.message")
    return {
        "keys": list(fields),
        "count": ast.unparse(fields["count"]),
        "reasons": ast.unparse(fields["reason_codes"]),
        "template": template,
    }


def _attach_points(chat: str) -> list[tuple[str, str, str]]:
    """Every place chat.py attaches a restricted key: (route, guard, expression)."""
    hits = []
    for fn in [node for node in ast.walk(_tree(chat)) if isinstance(node, ast.AsyncFunctionDef)]:
        guards = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
                for key, value in _writes(node, "result"):
                    if key == "restricted":
                        guards[id(value)] = ast.unparse(node.test)
        for key, value in _writes(fn, "result"):
            if key == "restricted":
                hits.append((fn.name, guards.get(id(value), ""), ast.unparse(value)))
    return hits

def _row_shape(catalog: str) -> dict:
    tree = _tree(catalog)
    select = [
        node for node in tree.body
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_SELECT_COLUMNS"
    ]
    assert len(select) == 1, "the stored-column list is not where this pin reads rows from"
    base = [column.strip() for column in select[0].value.value.split(",")]
    fn = _function(catalog, SERIALIZER)
    assigned: list[tuple[int, str]] = []
    popped: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript):
            subscript = node.targets[0]
            if isinstance(subscript.value, ast.Name) and isinstance(subscript.slice, ast.Constant):
                assigned.append((node.lineno, str(subscript.slice.value)))
        if (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "pop" and node.args and isinstance(node.args[0], ast.Constant)
        ):
            popped.append(str(node.args[0].value))
    assigned.sort()
    appended = [key for _lineno, key in assigned if key not in base]
    required = base + [key for key in appended if key not in popped]
    optional = [key for key in appended if key in popped]
    local = [node for node in ast.walk(_function(catalog, "_local_row")) if isinstance(node, ast.Return)]
    ownership = {
        node.targets[0].id: node.value.value for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("OWNERSHIP_")
    }
    return {
        "required": required,
        "optional": optional,
        "keys": required + optional,
        "offline_keys": {str(key.value) for key in local[-1].value.keys},
        "stored_keys": set(base) | set(optional),
        "owned": ownership["OWNERSHIP_OWNED"],
        "legacy": ownership["OWNERSHIP_LEGACY"],
    }


def _appended_to(chat: str, function_name: str, position: int) -> str:
    fn = _function(chat, function_name)
    returns = [node for node in ast.walk(fn) if isinstance(node, ast.Return)]
    name = returns[-1].value.elts[position].id
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "append"
            and ast.unparse(node.value.func.value) == name and node.value.args
        ):
            assert isinstance(node.value.args[0], ast.Call), "%s.append carries no projection call" % name
            return ast.unparse(node.value.args[0].func)
    raise AssertionError("nothing is appended to %s" % name)


def _element_kind(chat: str, name: str) -> tuple[str, str]:
    """What one entry of the documents array is: ("string", key) or ("object", builder)."""
    value = _envelope(chat, name)["values"]["documents"]
    if isinstance(value, ast.ListComp):
        assert len(value.generators) == 1, "the flat array is built by two comprehensions now"
        assert len(value.generators[0].ifs) == 1, "the flat array grew a second filter: re-read its paragraph"
        assert isinstance(value.elt, ast.Subscript) and isinstance(value.elt.slice, ast.Constant)
        return "string", str(value.elt.slice.value)
    assert isinstance(value, ast.Name), "the array of %s is no longer a name this pin can follow" % name
    for node in ast.walk(_function(chat, name)):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple):
            names = [element.id for element in node.targets[0].elts]
            if value.id in names and isinstance(node.value, ast.Call):
                return "object", _appended_to(chat, ast.unparse(node.value.func), names.index(value.id))
    raise AssertionError("%s builds its array out of something this pin cannot follow" % name)


# ================================= the envelopes =================================


def _check_envelope(
    body: str, name: str, kind: str, element: str,
    chat: str | None = None, label: str = "the paragraph",
) -> None:
    chat = _text(CHAT_PY) if chat is None else chat
    envelope = _envelope(chat, name)
    required, optional = _presence(_table(body))
    assert required == envelope["required"], (
        "%s is no longer the keys %s builds: contract %s vs route %s"
        % (label, name, required, envelope["required"])
    )
    assert optional == envelope["optional"], (
        "%s is no longer the keys %s attaches under a guard: contract %s vs route %s"
        % (label, name, optional, envelope["optional"])
    )
    assert required + optional == _table_keys(body), "%s lists its keys out of order" % label
    type_cell, _presence_cell, meaning = _cell(body, "documents")
    assert type_cell == "%s[]" % kind, (
        "%s says documents holds %r while %s builds %r entries out of %s"
        % (label, type_cell, name, kind, element)
    )
    assert "`%s`" % element in meaning, (
        "%s stopped naming where an array element comes from (%s)" % (label, element)
    )
    blocks = _json_blocks(body)
    for block in blocks:
        assert set(block) <= set(required) | set(optional), (
            "%s shows a key the route never returns: %s"
            % (label, sorted(set(block) - set(required) - set(optional)))
        )
        assert set(required) <= set(block), "%s lost an always-present key in an example" % label
    plain = [block for block in blocks if "restricted" not in block]
    assert plain, "%s never shows the answer for a caller nothing was refused from" % label
    for block in plain:
        assert set(block) == set(required), "%s: the no-refusal example is not the plain envelope" % label
    for key in optional:
        guard, value = envelope["guards"][key]
        assert guard == "withheld", "%s is attached under %r, not under the one shared verdict" % (key, guard)
        assert isinstance(value, ast.Call) and ast.unparse(value.func) == PROJECTION, (
            "%s is no longer built by %s: one fact, two shapes" % (key, PROJECTION)
        )
        assert [ast.unparse(argument) for argument in value.args] == [guard], (
            "%s is fed something other than the verdict it is guarded by" % key
        )


def test_the_flat_documents_envelope_is_the_envelope_the_route_builds() -> None:
    chat = _text(CHAT_PY)
    kind, element = _element_kind(chat, FLAT_ROUTE)
    _check_envelope(_subsections()[FLAT_SUBHEAD], FLAT_ROUTE, kind, element)


def test_the_catalog_envelope_is_the_envelope_the_route_builds() -> None:
    chat = _text(CHAT_PY)
    kind, element = _element_kind(chat, CATALOG_ROUTE)
    _check_envelope(_subsections()[CATALOG_SUBHEAD], CATALOG_ROUTE, kind, element)


def test_the_two_exposes_differ_only_in_what_their_array_holds() -> None:
    chat = _text(CHAT_PY)
    flat = _envelope(chat, FLAT_ROUTE)
    catalog = _envelope(chat, CATALOG_ROUTE)
    assert flat["required"] == catalog["required"] == ["documents"]
    assert flat["optional"] == catalog["optional"] == ["restricted"]
    assert _element_kind(chat, FLAT_ROUTE) == ("string", "filename")
    assert _element_kind(chat, CATALOG_ROUTE) == ("object", SERIALIZER)
    assert _cell(_subsections()[FLAT_SUBHEAD], "documents")[0] == "string[]"
    assert _cell(_subsections()[CATALOG_SUBHEAD], "documents")[0] == "object[]"


def test_the_weld_reads_a_registered_route_and_not_a_remembered_name() -> None:
    chat, module = _text(CHAT_PY), _text(MAIN_PY)
    flat = _endpoint(chat, FLAT_ROUTE, module)
    catalog = _endpoint(chat, CATALOG_ROUTE, module)
    assert flat == "GET /api/v1/documents", flat
    assert catalog == "GET /api/v1/documents/catalog", catalog
    for subhead, endpoint in ((FLAT_SUBHEAD, flat), (CATALOG_SUBHEAD, catalog)):
        assert endpoint in subhead, "%s no longer names %s on the same line as its body" % (subhead, endpoint)
    for name in (FLAT_ROUTE, CATALOG_ROUTE):
        _method, _path, keywords = _route_of(_function(chat, name))
        assert "response_model" not in keywords, (
            "%s grew a response model, and the section says the built dict is the wire shape" % name
        )


def test_the_document_paragraph_lives_where_no_elses_grid_is() -> None:
    body = _text(CONTRACT)
    assert _heading(body, NEIGHBOUR_HEADING) < _heading(body, SECTION_HEADING), (
        "the document section moved above the dataset section: R186 slices its region up to the next "
        "## and would start reading this one"
    )
    tail = body[_heading(body, NEIGHBOUR_HEADING) + len(NEIGHBOUR_HEADING):]
    cut = re.search(r"^## ", tail, re.MULTILINE)
    neighbour = tail[: cut.start() if cut else len(tail)]
    assert re.search(r"(?m)^%s" % re.escape(SECTION_HEADING), neighbour) is None, (
        "the document section sits inside the dataset region"
    )
    assert "row_scope" not in _section(), (
        "this section started speaking about the dataset row layer: one grid, one field"
    )


def test_the_shared_projection_is_attached_exactly_twice_in_chat() -> None:
    chat = _text(CHAT_PY)
    hits = _attach_points(chat)
    assert sorted(name for name, _guard, _call in hits) == sorted([FLAT_ROUTE, CATALOG_ROUTE]), hits
    assert all(guard == "withheld" for _name, guard, _call in hits), hits
    assert [call for _name, _guard, call in hits] == ["%s(withheld)" % PROJECTION] * 2, hits
    builders = [node for node in ast.walk(_tree(chat))
                if isinstance(node, ast.FunctionDef) and node.name == PROJECTION]
    assert len(builders) == 1, "%s is defined more than once" % PROJECTION


# =============================== the shared tally ===============================


def _tally_examples(contract: str | None = None) -> list[dict]:
    found = []
    for subhead in (FLAT_SUBHEAD, CATALOG_SUBHEAD):
        found.extend(block["restricted"] for block in _json_blocks(_subsections(contract)[subhead])
                     if "restricted" in block)
    found.extend(block for block in _fences(_subsections(contract)[RESTRICTED_SUBHEAD])
                 if "count" in block)
    assert found, "no example carries the withheld tally anywhere in the section"
    return found


def test_the_documented_tally_keys_are_the_projection_keys() -> None:
    body = _subsections()[RESTRICTED_SUBHEAD]
    shape = _projection(_text(CHAT_PY))
    required, optional = _presence(_table(body))
    assert optional == [], "restricted grew a key that only appears sometimes: say under what"
    assert required == shape["keys"], (
        "the tally table and the projection disagree: contract %s vs code %s" % (required, shape["keys"])
    )
    for item in _tally_examples():
        assert set(item) == set(shape["keys"]), (
            "an example of restricted is not the projection: %s vs %s" % (sorted(item), shape["keys"])
        )


def test_the_number_in_the_sentence_is_the_number_in_the_field() -> None:
    body = _subsections()[RESTRICTED_SUBHEAD]
    shape = _projection(_text(CHAT_PY))
    assert shape["count"] == "len(withheld)", "the tally is computed from something else now"
    assert "`%s`" % shape["count"] in _cell(body, "count")[2], (
        "the contract no longer quotes the expression the count is built from"
    )
    for item in _tally_examples():
        assert isinstance(item["count"], int), "the example count is not a count"


def test_the_message_template_is_the_sentence_the_projection_emits() -> None:
    body = _subsections()[RESTRICTED_SUBHEAD]
    shape = _projection(_text(CHAT_PY))
    documented = re.findall(r"`([^`\n]*\{count\}[^`\n]*)`", body)
    assert len(documented) == 1, "the section carries %d templates for one sentence" % len(documented)
    assert documented[0] == shape["template"], (
        "the wording promised to the customer is not the wording the route emits:\ncontract: %s\ncode: %s"
        % (documented[0], shape["template"])
    )
    for item in _tally_examples():
        assert item["message"] == shape["template"].replace("{count}", str(item["count"])), (
            "the example sentence was not rendered from the template with its own count"
        )


def test_the_reason_codes_are_that_verdicts_codes_deduplicated_in_order() -> None:
    body = _subsections()[RESTRICTED_SUBHEAD]
    shape = _projection(_text(CHAT_PY))
    assert "dict.fromkeys" in shape["reasons"], "reason codes are no longer collected in one ordered pass"
    assert "withheld" in shape["reasons"], "reason codes no longer come from the same verdict as the count"
    _type, _presence_cell, meaning = _cell(body, "reason_codes")
    assert "`dict.fromkeys`" in meaning, "the contract stopped naming how the codes are collected"
    assert "not** a contract enum" in meaning, (
        "the contract promised a closed set of reason codes; the codes belong to the policy layer"
    )
    for item in _tally_examples():
        assert len(item["reason_codes"]) == len(set(item["reason_codes"])), "an example repeats a code"


def test_the_tally_names_no_document_and_says_why() -> None:
    flat_prose = _flat(_subsections()[RESTRICTED_SUBHEAD])
    assert "never a filename" in flat_prose and "never an id" in flat_prose, (
        "the section stopped promising that a withheld document stays unnamed"
    )
    for item in _tally_examples():
        assert set(item) == {"count", "reason_codes", "message"}, (
            "the tally grew a key that could carry a name: %s" % sorted(item)
        )


# ================================= the row shape =================================


def _check_rows(body: str, catalog: str, label: str) -> None:
    shape = _row_shape(catalog)
    required, optional = _presence(_table(body))
    assert required + optional == _table_keys(body), "%s lists its row keys out of order" % label
    assert required == shape["required"], (
        "%s promises rows the serializer does not guarantee: contract %s vs code %s"
        % (label, required, shape["required"])
    )
    assert optional == shape["optional"], (
        "%s conditional row keys are not the pair the serializer withholds: %s vs %s"
        % (label, optional, shape["optional"])
    )
    assert shape["offline_keys"] == shape["stored_keys"], (
        "the stored row and the offline row are two different shapes: one of them is lying to this page"
    )
    examples = _fences(body) + [
        row for block in _json_blocks(_subsections()[CATALOG_SUBHEAD]) for row in block["documents"]
    ]
    assert examples, "%s has no example row: the shape is not pinned down" % label
    for row in examples:
        assert set(shape["required"]) <= set(row), (
            "%s: an example row lost a guaranteed key: %s" % (label, sorted(set(shape["required"]) - set(row)))
        )
        assert set(row) <= set(shape["keys"]), (
            "%s: an example row carries a key nobody builds: %s"
            % (label, sorted(set(row) - set(shape["keys"])))
        )
        assert row["ownership"] == (shape["legacy"] if row["owner_id"] is None else shape["owned"]), (
            "%s: the ownership marker no longer follows the owner_id it is derived from" % label
        )
        assert "`%s`" % row["ownership"] in body, "%s: an ownership value went unmentioned in the table" % label
    loud = [row for row in examples if "index_status" in row]
    assert loud and len(loud) != len(examples), (
        "%s must show both a row that recorded an index decision and one that stayed silent" % label
    )
    for row in loud:
        assert "index_reason" in row, "%s: an index decision was recorded without its reason key" % label


def test_the_documented_rows_are_the_rows_the_serializer_builds() -> None:
    _check_rows(_subsections()[ROWS_SUBHEAD], _text(CATALOG_PY), "the row paragraph")


def test_the_flat_array_is_an_intersection_and_says_so() -> None:
    chat = _text(CHAT_PY)
    assert _element_kind(chat, FLAT_ROUTE) == ("string", "filename")
    body = _flat(_subsections()[FLAT_SUBHEAD])
    assert "intersection" in body, "the flat paragraph stopped warning that its array is filtered twice"
    assert "neither `documents` nor `restricted`" in body, (
        "the section no longer says where a visible-but-unindexed document actually shows up"
    )
    assert "GET /api/v1/documents/catalog" in body, (
        "the section stopped pointing at the route where the unindexed row is readable"
    )


# ============================ the index-state domain ============================


def _index_states(policy: str) -> list[str]:
    tree = _tree(policy)
    values, declared = {}, None
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith("INDEX_STATUS_") and isinstance(node.value, ast.Constant):
                values[name] = str(node.value.value)
            if name == "INDEX_STATUSES":
                declared = node.value
    assert declared is not None and isinstance(declared, ast.Tuple), (
        "INDEX_STATUSES is no longer a literal tuple of the module's own constants"
    )
    states = []
    for element in declared.elts:
        assert isinstance(element, ast.Name) and element.id in values, (
            "INDEX_STATUSES carries something this pin cannot resolve"
        )
        states.append(values[element.id])
    assert len(states) == len(set(states)), "the declared domain repeats a state"
    return states


def test_the_documented_index_states_are_the_declared_domain() -> None:
    states = _index_states(_text(POLICY_PY))
    cell = _cell(_subsections()[ROWS_SUBHEAD], "index_status")[2]
    for state in states:
        assert "`%s`" % state in cell, "the row table no longer names %r as an index state" % state
    examples = _fences(_subsections()[ROWS_SUBHEAD]) + [
        row for block in _json_blocks(_subsections()[CATALOG_SUBHEAD]) for row in block["documents"]
    ]
    loud = [row for row in examples if "index_status" in row]
    assert loud, "no example row shows an index state at all"
    for row in loud:
        assert row["index_status"] in states, (
            "an example row shows %r, outside the domain the policy module declares" % row["index_status"]
        )
# ================ the false claim R194 collected and R196 handed to R201 ================


def test_neither_flat_route_declares_a_query_parameter() -> None:
    chat = _text(CHAT_PY)
    for name in (FLAT_ROUTE, CATALOG_ROUTE):
        params = _envelope(chat, name)["params"]
        assert params == ["request"], (
            "%s now takes %s: the contract and the runbook both say these routes are not paginated"
            % (name, params)
        )
        for node in ast.walk(_function(chat, name)):
            if isinstance(node, ast.Call):
                assert ast.unparse(node.func) != "Query", "%s grew a Query default" % name
    sentences = _flat(_section())
    assert "it declares no query parameters" in sentences, (
        "the sentence that turns the discarded page parameters into a promise is gone from the contract"
    )
    assert "?page=&page_size=` on it is " + CONTRACT_PHRASE in sentences, (
        "the contract no longer says what happens to a page parameter sent to these routes"
    )
    assert "**not** paginated" in sentences


def test_the_runbook_stops_counting_a_page_that_never_existed() -> None:
    rows = {
        match.group(1): match.group(0)
        for match in re.finditer(r"^\| \*{0,2}(P-\d+)\*{0,2}[^\n]*$", _text(RUNBOOK), re.MULTILINE)
    }
    assert {"P-9", "P-11"} <= set(rows), sorted(rows)
    for gate in ("P-9", "P-11"):
        row = _flat(rows[gate])
        assert "R201" in row, "%s does not record who corrected it" % gate
        assert "?page=1&page_size=500" in row, (
            "%s must keep telling the operator the command it always told them" % gate
        )
        assert "app/api/v1/chat.py::list_documents" in row, (
            "%s does not name the route whose parameters are discarded" % gate
        )
        assert CONTRACT_PHRASE in row, "%s does not quote the contract sentence it now agrees with" % gate
        assert SECTION_HEADING.replace("## ", "") in row, "%s does not point at the contract section" % gate
    assert "documents[]" in rows["P-9"] and "100" in rows["P-9"], "P-9 stopped counting documents"
    for anchor in ("only_in_container", "only_in_repo"):
        assert anchor in rows["P-11"], "P-11 lost its two-way name comparison (%s)" % anchor


# ==================================== falsifiers ====================================


def _with_extra_row(body: str) -> str:
    return body.replace(
        "\n| `documents` | string[] | always |",
        "\n| `total` | int | always | how many documents there are in total |\n"
        "| `documents` | string[] | always |",
        1,
    )


def _without_a_row(body: str) -> str:
    return re.sub(r"\n\| `documents` \|[^|]*\|[^|]*\|[^|]*\|", "\n", body, count=1)


def test_falsification_the_contract_inventing_a_key_turns_the_weld_red() -> None:
    original = _text(CONTRACT)
    mutated = _with_extra_row(original)
    assert mutated != original, "the falsifier stopped touching the contract"
    body = _subsections(mutated)[FLAT_SUBHEAD]
    assert _table_keys(body)[:2] == ["total", "documents"]
    with pytest.raises(AssertionError) as raised:
        _check_envelope(body, FLAT_ROUTE, "string", "filename", label="falsified paragraph")
    assert "no longer the keys" in str(raised.value)
    assert _table_keys(_subsections()[FLAT_SUBHEAD]) == ["documents", "restricted"], (
        "the contract on disk carries the invented key, and must not"
    )


def test_falsification_the_contract_losing_a_key_turns_the_weld_red() -> None:
    mutated = _without_a_row(_text(CONTRACT))
    assert mutated != _text(CONTRACT), "the falsifier stopped touching the contract"
    body = _subsections(mutated)[FLAT_SUBHEAD]
    assert _table_keys(body) == ["restricted"]
    with pytest.raises(AssertionError):
        _check_envelope(body, FLAT_ROUTE, "string", "filename", label="shortened paragraph")


def test_falsification_a_renamed_key_turns_the_weld_red() -> None:
    mutated = _text(CONTRACT).replace("| `restricted` | object | only when refused |",
                                      "| `withheld` | object | only when refused |", 1)
    assert mutated != _text(CONTRACT)
    body = _subsections(mutated)[FLAT_SUBHEAD]
    with pytest.raises(AssertionError) as raised:
        _check_envelope(body, FLAT_ROUTE, "string", "filename", label="renamed paragraph")
    assert "restricted" in str(raised.value)


def test_falsification_a_second_restricted_builder_in_chat_turns_the_weld_red() -> None:
    chat = _text(CHAT_PY)
    split = chat.replace(
        "    result[\"restricted\"] = _restricted_summary(withheld)\n    return result\n\n\n"
        "@router.get(\"/documents/catalog\")",
        "    result[\"restricted\"] = {\"count\": len(withheld)}\n    return result\n\n\n"
        "@router.get(\"/documents/catalog\")",
        1,
    )
    assert split != chat, "the falsifier stopped finding the shared projection"
    hits = _attach_points(split)
    assert [call for _name, _guard, call in hits] != [
        "%s(withheld)" % PROJECTION, "%s(withheld)" % PROJECTION
    ], "a route splitting off the shared projection did not register: the pin is blind"
    body = _subsections()[FLAT_SUBHEAD]
    with pytest.raises(AssertionError):
        _check_envelope(body, FLAT_ROUTE, "string", "filename", chat=split, label="split paragraph")


def test_falsification_a_new_row_column_breaks_the_row_paragraph() -> None:
    catalog = _text(CATALOG_PY).replace(
        '"filename, version, classification, department, storage_path, created_at, "',
        '"filename, doc_label, version, classification, department, storage_path, created_at, "',
        1,
    )
    assert catalog != _text(CATALOG_PY)
    with pytest.raises(AssertionError) as raised:
        _check_rows(_subsections()[ROWS_SUBHEAD], catalog, "falsified rows")
    assert "doc_label" in str(raised.value)


def test_falsification_a_query_parameter_on_a_flat_route_turns_the_signature_pin_red() -> None:
    chat = _text(CHAT_PY).replace(
        "async def list_documents(request: FastAPIRequest):",
        "async def list_documents(request: FastAPIRequest, page: int = 1):",
        1,
    )
    assert chat != _text(CHAT_PY)
    with pytest.raises(AssertionError):
        assert _envelope(chat, FLAT_ROUTE)["params"] == ["request"]
    assert _envelope(_text(CHAT_PY), FLAT_ROUTE)["params"] == ["request"]
    assert _endpoint(chat, FLAT_ROUTE, _text(MAIN_PY)) == "GET /api/v1/documents", (
        "a query parameter must not move the address this pin reads"
    )
    assert "page: int" in chat
