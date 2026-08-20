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
