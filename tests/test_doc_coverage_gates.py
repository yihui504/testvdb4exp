"""文档覆盖率机械核对 + param 次级提取回归测试（pilot 2026-08-20 根因修复）.

覆盖:
- validate_doc_coverage: 根路径过滤 / 端点提取 / 覆盖率写回 raw_knowledge（LLM 自报覆写）
- gt_reach_injector._meta_param: top-level param 缺失时 test_parameters 次级提取
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_doc_coverage import (  # noqa: E402
    extract_openapi_endpoints,
    extract_raw_knowledge_endpoints,
)
from gt_reach_injector import _meta_param  # noqa: E402


# ═══════════════════════════════════════════════════════════════
# validate_doc_coverage — 端点提取
# ═══════════════════════════════════════════════════════════════

class TestOpenapiEndpointExtraction:
    def test_root_and_empty_paths_filtered(self):
        """qdrant spec 合并分片带入 GET /——归一化后成空 path，必须过滤。"""
        openapi = {"paths": {"/": {"get": {}}, "": {"get": {}},
                             "/collections/{name}": {"get": {}}}}
        eps = extract_openapi_endpoints(openapi, [])
        assert eps == {("GET", "/collections/{name}")}

    def test_exclude_prefixes(self):
        openapi = {"paths": {
            "/internal/foo": {"get": {}},
            "/telemetry": {"get": {}},
            "/cluster/recover": {"post": {}},  # 不在默认排除（GT 9421 所在）
        }}
        eps = extract_openapi_endpoints(
            openapi, ["/internal", "/admin", "/telemetry", "/metrics", "/healthz"])
        assert eps == {("POST", "/cluster/recover")}

    def test_non_http_methods_ignored(self):
        openapi = {"paths": {"/collections": {"get": {}, "parameters": [], "x-custom": {}}}}
        eps = extract_openapi_endpoints(openapi, [])
        assert eps == {("GET", "/collections")}


class TestRawKnowledgeEndpointExtraction:
    def test_method_path_list_form(self):
        """pilot raw_knowledge.md 实际形态：'- Method: PUT\n- Path: /...'。"""
        txt = "- Method: PUT\n- Path: /collections/{collection_name}\n\n" \
              "- Method: POST\n- Path: /collections/{collection_name}/points/search\n"
        eps = extract_raw_knowledge_endpoints_str(txt)
        assert eps == {("PUT", "/collections/{collection_name}"),
                       ("POST", "/collections/{collection_name}/points/search")}

    def test_table_form(self):
        txt = "| GET | /collections/{name} | ...\n| DELETE | /collections/{name} |"
        eps = extract_raw_knowledge_endpoints_str(txt)
        assert eps == {("GET", "/collections/{name}"),
                       ("DELETE", "/collections/{name}")}


def extract_raw_knowledge_endpoints_str(txt: str) -> set:
    """文件临时落盘后走原函数（复用真实 I/O 路径）。"""
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "raw_knowledge.md"
        p.write_text(txt, encoding="utf-8")
        return extract_raw_knowledge_endpoints(str(p))


# ═══════════════════════════════════════════════════════════════
# gt_reach_injector._meta_param — 次级提取
# ═══════════════════════════════════════════════════════════════

class TestMetaParamSecondaryExtraction:
    def _write_meta(self, tmp_path, sub, defect_id, meta):
        d = tmp_path / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{defect_id}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return str(tmp_path)

    def test_top_level_param_wins(self, tmp_path):
        sd = self._write_meta(tmp_path, "vein_scripts", "x",
                              {"param": "hnsw_ef", "test_parameters": {"other": 1}})
        assert _meta_param(sd, "x") == "hnsw_ef"

    def test_test_parameters_fallback(self, tmp_path):
        """pilot 修复前的真实形态：无 top-level param，test_parameters 有键。"""
        sd = self._write_meta(tmp_path, "vein_scripts", "x",
                              {"test_parameters": {
                                  "filter.key": "age",
                                  "filter.match.value": 10,
                                  "filter.match.value_type": "int"}})
        assert _meta_param(sd, "x") == "filter.key"  # _type 后缀键被过滤

    def test_behavioral_no_param_returns_empty(self, tmp_path):
        sd = self._write_meta(tmp_path, "vein_scripts", "y",
                              {"param": None, "test_parameters": {}})
        assert _meta_param(sd, "y") == ""

    def test_missing_meta_returns_empty(self, tmp_path):
        assert _meta_param(str(tmp_path), "nope") == ""

    def test_paren_annotation_stripped(self):
        """fullrun#1：agent meta "points[].vector (dimension)" 带说明括号——剥后可命中 GT 裸名。"""
        from gt_reach_injector import _norm_multi, _reached, _norm
        parts = _norm_multi("points[].vector (dimension)")
        assert parts == {"pointsvector"}
        assert _reached(_norm("vector"), parts)

    def test_points_prefix_alignment(self):
        """points[].vector 归一为 pointsvector——容器前缀 points 对齐 GT 裸名 vector。"""
        from gt_reach_injector import _reached, _norm
        assert _reached(_norm("vector"), {"pointsvector"})
        assert _reached(_norm("vector"), {"pointsvector", "wait"})

    def test_no_false_match_vectorsize(self):
        """防误匹配：vector 不得命中 vectors.size（vectorssize）。"""
        from gt_reach_injector import _reached, _norm
        assert not _reached(_norm("vector"), {"vectorssize"})


# ═══════════════════════════════════════════════════════════════
# chain_verdicts 双形态兼容（fullrun#5 R1 2026-08-21：旧直写根下+final_verdict）
# ═══════════════════════════════════════════════════════════════


class TestChainVerdictsDualForm:
    def _make_session(self, tmp_path, verdict_key, at_root):
        """构造 session：verdicts 用指定字段名，文件落 debate_logs/ 或根。"""
        sd = tmp_path
        (sd / "debate_logs").mkdir(exist_ok=True)
        (sd / "debate_logs" / "x_001.meta.json").write_text(
            json.dumps({"param": "tokenization"}), encoding="utf-8")
        cv = {"verdicts": [
            {"defect_id": "x_001", verdict_key: "DEFECT"},
            {"defect_id": "x_002", verdict_key: "NOT_DEFECT"},
        ]}
        target = sd if at_root else sd / "debate_logs"
        (target / "chain_verdicts.json").write_text(
            json.dumps(cv), encoding="utf-8")
        return str(sd)

    def test_root_final_verdict_form(self, tmp_path):
        """fullrun#5 R1 实况：auditor 旧直写落 session 根 + final_verdict 字段。"""
        from gt_reach_injector import _confirmed_params
        params = _confirmed_params(self._make_session(tmp_path, "final_verdict", at_root=True))
        assert params == {"tokenization"}

    def test_debate_logs_verdict_form(self, tmp_path):
        """fullrun#4 两段式转写形态：debate_logs/ + verdict 字段。"""
        from gt_reach_injector import _confirmed_params
        params = _confirmed_params(self._make_session(tmp_path, "verdict", at_root=False))
        assert params == {"tokenization"}

    def test_debate_logs_final_verdict_form(self, tmp_path):
        """交叉形态防漏：debate_logs/ 下也可能出现 final_verdict。"""
        from gt_reach_injector import _confirmed_params
        params = _confirmed_params(self._make_session(tmp_path, "final_verdict", at_root=False))
        assert params == {"tokenization"}
