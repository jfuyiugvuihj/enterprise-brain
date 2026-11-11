"""The off-peak index rebuild window: where its three knobs live, and what they may say (R425).

计划书 R50 asks for "低峰全量重建". The tool has had that shape for a while -- its usage line
is one `--apply --incremental --time-budget-seconds N` command long (scripts/rebuild_index.py:31)
-- but nothing ever put it on a calendar, so docs/handoff/2026-09-25-plan-ticket-closure.md §3.1
第 3 条 judged the gap as "代码欠，不欠机器".

This module is the single owner of the three knobs the window needs:

  * ``INDEX_REBUILD_SCHEDULE_ENABLED``    -- the switch, and it ships OFF,
  * ``INDEX_REBUILD_TIME_BUDGET_SECONDS`` -- the wall-clock budget, default 30 minutes,
  * ``INDEX_REBUILD_AT``                  -- the moment, default "03:30".

app/scheduler/jobs.py reads them here and nowhere else, so any one of them has exactly one place
to be wrong, and ``.env.example`` carries all three as commented-out factory defaults that
tests/test_r425_offpeak_index_rebuild.py recomputes from the constants below rather than trusting
the prose.

WHAT IS PINNED ABOVE THIS MODULE, AND WHY THERE IS NO COMMAND IN IT

    R22 判据 3 is a hard pin, not a preference: no startup hook, no upload hook and no scheduler
    job may import, call or spawn the rebuild command. tests/test_r22_rebuild_cli.py keeps
    checking for it, and since R242 its second pass reads parsed syntax rather than a text list,
    so an argv assembled as a list trips it too -- that shape is recorded in the file's own
    comments as the reason the pass exists. The consequence for this ticket is concrete: the
    scheduled half of 低峰重建 can be wired (a switch, a budget, a moment, a calendar entry), but
    the leg that would name the command cannot live under app/ at all. So this module owns the
    window and stays out of the write path, and the job built on it says plainly that it does not
    rebuild. Amending that pin is an owner decision, not a detail this module can pre-empt by
    hiding the command name in fragments -- the pin's own docstring calls that out as a known
    limit it refuses to paper over.

WHY OFF IS THE DEFAULT

    A private deployment is one machine inside one company. An install that wakes up in the small
    hours to rewrite a knowledge base nobody asked it to rewrite is not a feature, so "unset"
    means the job is never added to the scheduler at all. That is a different promise from "added,
    and the callback returns early": the calendar of a box that was never told stays exactly as
    narrow as the operator left it, and a reviewer can read that calendar without running it.

WHY THE BUDGET HAS NO "UNBOUNDED" SPELLING

    A whole library re-embedded in one sitting is the accident this knob exists to prevent, and
    the tool below it honours a budget only between documents -- which is also what makes an
    interrupted window resumable (scripts/rebuild_index.py:25-29). A missing, zero, negative or
    unparseable budget therefore resolves back to the shipped default with a warning, and
    ``schedulable`` re-checks that it is a positive number before anything reaches a scheduler.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

#: The three knobs, spelled exactly once in the repository.
SCHEDULE_ENV = "INDEX_REBUILD_SCHEDULE_ENABLED"
TIME_BUDGET_ENV = "INDEX_REBUILD_TIME_BUDGET_SECONDS"
AT_ENV = "INDEX_REBUILD_AT"

#: Factory defaults. ``.env.example`` writes all three as commented lines carrying these
#: numbers, and the R425 test derives the comment text from here instead of copying it.
DEFAULT_SCHEDULE_ENABLED = False
DEFAULT_TIME_BUDGET_SECONDS = 1800
DEFAULT_AT = "03:30"

#: The job's identity on the scheduler, so evidence can ask for it by name, not by position.
REBUILD_JOB_ID = "index_rebuild_window"

_AT_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")
#: The same four spellings app/main.py accepts for SCHEDULER_ENABLED, so one operator's "on"
#: means "on" in both places. Anything else is not a switch: it warns and stays off.
_TRUE_SPELLINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_SPELLINGS = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class IndexRebuildWindow:
    """What the three knobs said, resolved once, plus the answer to "may this be scheduled".

    ``notes`` is not decoration: an unparseable budget or moment falls back to the shipped
    default, and the operator has to learn that from one log line rather than from a window that
    quietly moved to a time nobody typed.
    """

    enabled: bool
    budget_seconds: int
    hour: int
    minute: int
    notes: tuple[str, ...] = ()

    @property
    def clock(self) -> tuple[int, int]:
        """The cron pair, so jobs.py never re-derives it from a string."""
        return (self.hour, self.minute)

    @property
    def schedulable(self) -> bool:
        return bool(self.enabled) and self.budget_seconds > 0

    def unschedulable_reason(self) -> str:
        """Why nothing was added to the calendar, in one sentence an operator can act on."""
        if not self.enabled:
            return (
                f"{SCHEDULE_ENV} is off (shipped default {DEFAULT_SCHEDULE_ENABLED}), so this "
                "box schedules no rebuild window at all"
            )
        if self.budget_seconds <= 0:
            return (
                f"{TIME_BUDGET_ENV}={self.budget_seconds} could never re-embed a single document, "
                "so nothing is scheduled"
            )
        return ""


def _read_switch(source: dict[str, str], notes: list[str]) -> bool:
    raw = str(source.get(SCHEDULE_ENV, "") or "").strip().lower()
    if not raw:
        return DEFAULT_SCHEDULE_ENABLED
    if raw in _TRUE_SPELLINGS:
        return True
    if raw in _FALSE_SPELLINGS:
        return False
    notes.append(
        f"{SCHEDULE_ENV}={raw!r} is neither an on nor an off spelling this code reads; "
        f"staying {DEFAULT_SCHEDULE_ENABLED}"
    )
    return DEFAULT_SCHEDULE_ENABLED


def _read_budget(source: dict[str, str], notes: list[str]) -> int:
    raw = str(source.get(TIME_BUDGET_ENV, "") or "").strip()
    if not raw:
        return DEFAULT_TIME_BUDGET_SECONDS
    try:
        value = int(float(raw))
    except (ValueError, OverflowError):
        notes.append(
            f"{TIME_BUDGET_ENV}={raw!r} is not a number of seconds; using "
            f"{DEFAULT_TIME_BUDGET_SECONDS}"
        )
        return DEFAULT_TIME_BUDGET_SECONDS
    if value <= 0:
        notes.append(
            f"{TIME_BUDGET_ENV}={value} would stop before any document is embedded; using "
            f"{DEFAULT_TIME_BUDGET_SECONDS}"
        )
        return DEFAULT_TIME_BUDGET_SECONDS
    return value


def _default_clock() -> tuple[int, int]:
    hour, minute = DEFAULT_AT.split(":")
    return (int(hour), int(minute))


def _read_moment(source: dict[str, str], notes: list[str]) -> tuple[int, int]:
    raw = str(source.get(AT_ENV, "") or "").strip()
    if not raw:
        return _default_clock()
    match = _AT_PATTERN.match(raw)
    if match and 0 <= int(match.group(1)) <= 23 and 0 <= int(match.group(2)) <= 59:
        return (int(match.group(1)), int(match.group(2)))
    notes.append(f"{AT_ENV}={raw!r} is not HH:MM; using {DEFAULT_AT}")
    return _default_clock()


def resolve_index_rebuild_window(env: dict[str, str] | None = None) -> IndexRebuildWindow:
    """Read the three knobs once. With no argument they come from the process environment."""
    source = dict(os.environ) if env is None else dict(env)
    notes: list[str] = []
    hour, minute = _read_moment(source, notes)
    return IndexRebuildWindow(
        enabled=_read_switch(source, notes),
        budget_seconds=_read_budget(source, notes),
        hour=hour,
        minute=minute,
        notes=tuple(notes),
    )
