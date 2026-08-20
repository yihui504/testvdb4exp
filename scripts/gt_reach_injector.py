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

import json
import os
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from _pipeline_utils import setup_encoding  # noqa: E402

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
    """Normalized param names from the session's chain verdicts.

    ADR-0008 base: the judge quartet + stage2_aggregation is gone; the confirmed
    set now comes from debate_logs/chain_verdicts.json (chain-auditor's final
    verdicts). The auditor re-audits the accumulated evidence_chain/ each round
    (builders append chains; auditor writes the file fresh), so a single read of
    the latest file already carries cross-round accumulation — no history file
    needed. DEFECT only; NOT_DEFECT / NEEDS_MORE_EVIDENCE never counted.
    """
    cv_path = os.path.join(session_dir, "debate_logs", "chain_verdicts.json")
    params: set = set()
    try:
        cv = json.load(open(cv_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return params
    for v in cv.get("verdicts", []):
        if not isinstance(v, dict) or v.get("verdict") != "DEFECT":
            continue
        np = _norm(v.get("param", ""))
        if np:
            params.add(np)
            continue
        # Fallback (pilot 2026-08-20): chain-auditor verdicts carry no param
        # field; recover it from the attack agent's .meta.json next to the
        # script (debate_logs/<defect_id>.meta.json / vein_scripts/).
        np = _norm(_meta_param(session_dir, v.get("defect_id", "")))
        if np:
            params.add(np)
    return params


def _meta_param(session_dir: str, defect_id: str) -> str:
    """param field from the attack agent's .meta.json for defect_id (or "")."""
    if not defect_id:
        return ""
    for sub in ("debate_logs", "vein_scripts"):
        meta_path = os.path.join(session_dir, sub, defect_id + ".meta.json")
        try:
            meta = json.load(open(meta_path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        p = meta.get("param", "")
        if p:
            return str(p)
        # Secondary extraction (pilot 2026-08-20): vein metas carry the tested
        # params in test_parameters dict (keys are dotted param paths) even when
        # the top-level param field is missing/null.
        tp = meta.get("test_parameters")
        if isinstance(tp, dict) and tp:
            keys = [k for k in tp if not k.endswith("_type")]
            if keys:
                return str(keys[0])
    return ""


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
