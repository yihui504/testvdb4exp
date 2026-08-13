#!/usr/bin/env python3
"""GT-informed reach injector (experimental build, phase3-plan #5).

Emits a GENERIC continuation hint when the current session has not yet reached
all Ground-Truth bugs for this (target, version). Feeds the attack agents'
dispatch prompts via the same --text-only injection pattern as
threat_model_injector.py (see commands/mine.md 8a/8b, {GT_HINT} variable).

Blindness contract — GT bug features (endpoint/param) live ONLY inside this
script's comparison; the emitted hint contains no feature, only a reached count
and a generic "improve quality / broaden coverage / dig deeper" nudge. The hint
is identical for all four attack agents (no per-direction wording), so it
cannot signal which direction the unreached bugs lie in.

No-op outside the experiment: if TESTVDB_GT_PATH is unset or the file is
missing/invalid, prints an empty string (--text-only) or {} and exits 0, so the
normal mining pipeline is completely unaffected.

Usage:
  GT_HINT=$(python scripts/gt_reach_injector.py \\
            --session-dir results/{target}/{version}/{timestamp} --text-only)

gt.json discovery (in order):
  1. TESTVDB_GT_PATH env var, if set and points to an existing file (override);
  2. results/{target}/{version}/gt.json — the conventional per-version location
     (= session_dir's parent). The experiment groups GT bugs by (target, version)
     and places one gt.json per version here, then runs /mine once per version.

gt.json format:
  {"target": "milvus", "version": "v2.6.17",
   "bugs": [{"id": "milvus_47729", "endpoint": "search", "param": "nprobe"}, ...]}
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from _pipeline_utils import setup_encoding, extract_confirmed  # noqa: E402

HINT_TEMPLATE = (
    "【GT-informed 续挖】当前会话尚未覆盖全部目标缺陷（已确认 {x}/{y}）。"
    "可能你的测试脚本质量不足，或尚未覆盖所有测试方向（端点/参数/边界/并发/状态）。"
    "请提升脚本质量、扩大测试方向的覆盖、深化挖掘。"
    "⛔ 本提示不含任何具体端点/参数/预期行为，请凭现有 contract 与 threat_model 自行判断方向。"
)


def _norm(s: str) -> str:
    """Coarse param-name normalization for matching (lowercase alnum only)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _confirmed_params(session_dir: str) -> set:
    """Normalized param names from the session's stage2 aggregation(s)."""
    params: set = set()
    for agg_path in glob.glob(
        os.path.join(session_dir, "**", "stage2_aggregation*.json"), recursive=True
    ):
        try:
            agg = json.load(open(agg_path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for d in extract_confirmed(agg):
            np = _norm(d.get("param", ""))
            if np:
                params.add(np)
    return params


def _noop(text_only: bool) -> int:
    print("" if text_only else "{}")
    return 0


def main() -> int:
    setup_encoding()

    session_dir = ""
    text_only = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--session-dir" and i + 1 < len(args):
            session_dir = args[i + 1]
            i += 2
        elif args[i] == "--text-only":
            text_only = True
            i += 1
        else:
            i += 1

    gt_path = os.environ.get("TESTVDB_GT_PATH")
    if not gt_path or not os.path.isfile(gt_path):
        # Conventional per-version location: results/{target}/{version}/gt.json
        # (session_dir = results/{target}/{version}/{timestamp}, so its parent is
        # the version root). Lets the experiment run /mine once per version with
        # that version's grouped GT bugs in place — no gt_path threading needed.
        gt_path = str(Path(session_dir).parent / "gt.json")
        if not os.path.isfile(gt_path):
            return _noop(text_only)

    try:
        gt = json.load(open(gt_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _noop(text_only)

    bugs = gt.get("bugs", []) if isinstance(gt, dict) else []
    if not bugs:
        return _noop(text_only)

    confirmed = _confirmed_params(session_dir)
    y = len(bugs)
    x = sum(1 for b in bugs if (np := _norm(b.get("param", ""))) and np in confirmed)

    if x >= y:
        # All reached — stop nudging; the round cap ends the run.
        if text_only:
            print("")
        else:
            print(json.dumps({"reached": x, "total": y, "all_reached": True}, ensure_ascii=False))
        return 0

    hint = HINT_TEMPLATE.format(x=x, y=y)
    if text_only:
        print(hint)
    else:
        print(json.dumps({"reached": x, "total": y, "all_reached": False, "hint": hint},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
