# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for LLM/agent discovery manifests, `llms.txt` sync, and `.venv` introspection."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import tomllib
from typing import Any

from mcp import Client
import pytest

import cxidk
from cxidk import CxContext
from cxidk.ai import mcp as ai_mcp
from cxidk.ai.mcp import __main__ as mcp_main
from cxidk.ai import skills

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_gen_llms_module() -> Any:
    """Loads `.github/scripts/gen_llms_txt.py` for in-process verification."""
    script_path = REPO_ROOT / ".github" / "scripts" / "gen_llms_txt.py"
    spec = importlib.util.spec_from_file_location("gen_llms_txt", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gen_llms_txt_check_and_sdk_coverage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verifies `llms.txt`, `llms-full.txt`, and synced skills have zero drift."""
    gen_mod = _load_gen_llms_module()
    assert gen_mod.main(["--check"]) == 0

    root_llms = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")
    pkg_llms = (REPO_ROOT / "src" / "cxidk" / "llms.txt").read_text(
        encoding="utf-8"
    )
    full_llms = (REPO_ROOT / "llms-full.txt").read_text(encoding="utf-8")

    assert root_llms == pkg_llms
    assert "cxidk.workflow.ops.ConfigOps" in root_llms
    assert "cxidk.workflow.format.Insights" in root_llms
    assert "cxidk.workflow.role_recognizer.RoleRecognizer" in root_llms
    assert "https://github.com/GoogleCloudPlatform/conversational-insights-devkit" in root_llms

    assert "## Detailed AI Tool Signatures (`cxidk.ai.tools`)" in full_llms
    assert "# CCAI Insights Filter Syntax Reference" in full_llms
    for skill_name in skills.list_skills():
        assert f"name: {skill_name}" in full_llms

    missing_target = tmp_path / "missing_llms.txt"
    monkeypatch.setattr(
        gen_mod,
        "expected_artifacts",
        lambda: {missing_target: "expected"},
    )
    assert gen_mod.main(["--check"]) == 1


def test_pyproject_mcp_and_gemini_extension_manifests() -> None:
    """Validates PyPI metadata, `server.json`, `README.md`, and `gemini-extension.json`."""
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject["project"]
    version = project["version"]
    assert version == cxidk.__version__

    keywords = set(project.get("keywords", []))
    for expected_kw in (
        "ccai-insights",
        "conversational-insights",
        "mcp-server",
        "google-adk",
        "aws-transcribe",
        "genesys-cloud",
    ):
        assert expected_kw in keywords

    urls = project.get("urls", {})
    assert (
        urls.get("Repository")
        == "https://github.com/GoogleCloudPlatform/conversational-insights-devkit"
    )
    assert "llms-full.txt" in urls.get("LLMContext", "")

    scripts = project.get("scripts", {})
    assert scripts.get("cxidk") == "cxidk.ai.mcp.__main__:main"
    assert scripts.get("cxidk-mcp") == "cxidk.ai.mcp.__main__:main"

    server_manifest = json.loads(
        (REPO_ROOT / "server.json").read_text(encoding="utf-8")
    )
    mcp_name = server_manifest["name"]
    assert mcp_name == "io.github.GoogleCloudPlatform/cxidk"
    assert server_manifest["version"] == version
    assert 1 <= len(server_manifest["description"]) <= 100

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"<!-- mcp-name: {mcp_name} -->" in readme

    pkg = server_manifest["packages"][0]
    assert pkg["identifier"] == "cxidk"
    assert pkg["version"] == version
    assert pkg["runtimeHint"] == "uvx"
    runtime_args = pkg.get("runtimeArguments", [])
    assert any(arg.get("value") == "cxidk[mcp]" for arg in runtime_args)

    gem_ext = json.loads(
        (REPO_ROOT / "gemini-extension.json").read_text(encoding="utf-8")
    )
    assert gem_ext["name"] == "conversational-insights-devkit"
    assert gem_ext["version"] == version
    context_file = REPO_ROOT / gem_ext["contextFileName"]
    assert context_file.is_file()
    assert "Untrusted Transcript Boundary" in context_file.read_text(
        encoding="utf-8"
    )

    server_env_names = {ev["name"] for ev in pkg["environmentVariables"]}
    ext_env_names = {setting["envVar"] for setting in gem_ext["settings"]}
    assert server_env_names <= ext_env_names

    for skill_name in skills.list_skills():
        mirrored = REPO_ROOT / "skills" / skill_name / "SKILL.md"
        assert mirrored.is_file()
        assert mirrored.read_text(encoding="utf-8") == skills.load_skill(
            skill_name
        )


def test_top_level_package_introspection_and_cli_discovery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verifies lazy top-level subpackages, `get_llms_txt()`, and CLI discovery flags."""
    assert cxidk.wrapper is not None
    assert cxidk.workflow is not None
    assert cxidk.ai is not None
    assert cxidk.core is not None
    with pytest.raises(AttributeError):
        _ = cxidk.nonexistent_submodule
    with pytest.raises(AttributeError):
        _ = ai_mcp.nonexistent_mcp_attr

    llms_text = cxidk.get_llms_txt()
    assert "# Conversational Insights DevKit (cxidk)" in llms_text

    rc = mcp_main.main(["--print-llms-txt"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == llms_text

    def _raise_missing_mcp(mod_name: str) -> Any:
        raise ModuleNotFoundError(f"No module named {mod_name!r}", name="mcp")

    monkeypatch.setattr(mcp_main.importlib, "import_module", _raise_missing_mcp)
    missing_rc = mcp_main.main(["--transport", "stdio"])
    missing_io = capsys.readouterr()
    assert missing_rc == 2
    assert 'pip install "cxidk[mcp]"' in missing_io.err


async def test_mcp_exposes_llms_txt_and_skill_resources(
    demo_cx: CxContext,
) -> None:
    """Verifies `cxidk-mcp` lists and serves `llms.txt` and all `SKILL.md` resources."""
    policy = ai_mcp.Policy(
        transport="stdio",
        default_project_id="demo-proj-01",
        default_location="us-central1",
        allowed_projects=("demo-proj-01",),
        toolsets=("core",),
        allow_writes=False,
    )
    server = ai_mcp.build_server(policy=policy, cx=demo_cx)

    async with Client(server, raise_exceptions=True) as client:
        listed = await client.list_resources()
        uris = {str(res.uri) for res in listed.resources}
        assert "cxidk://reference/llms-txt" in uris

        llms_res = await client.read_resource("cxidk://reference/llms-txt")
        assert "Conversational Insights DevKit" in str(llms_res.contents[0])

        for skill_name in skills.list_skills():
            skill_uri = f"cxidk://skills/{skill_name}"
            assert skill_uri in uris
            skill_res = await client.read_resource(skill_uri)
            assert f"name: {skill_name}" in str(skill_res.contents[0])


def test_mcp_adk_and_gen_llms_import_without_optional_extras() -> None:
    """Ensures `cxidk[mcp]`, `cxidk[adk]`, `format`, and `gen_llms_txt.py` omit extra deps."""
    probe = textwrap.dedent(
        f"""
        import importlib
        import importlib.abc
        import importlib.util
        from pathlib import Path
        import sys
        from unittest.mock import MagicMock

        sys.path.insert(0, {str(REPO_ROOT / "src")!r})

        BLOCKED = (
            "google.cloud.dlp",
            "google.cloud.dlp_v2",
            "google.cloud.speech",
            "google.cloud.speech_v1",
            "google.cloud.speech_v2",
            "google.cloud.texttospeech",
            "pydub",
            "google.cloud.dialogflow",
            "google.cloud.dialogflowcx",
            "gspread",
            "pandas",
            "google.cloud.iam",
            "google.cloud.resourcemanager_v3",
            "google.cloud.bigquery",
            "sklearn",
            "tabulate",
        )

        class _Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if any(fullname == p or fullname.startswith(p + ".") for p in BLOCKED):
                    raise ModuleNotFoundError(f"Blocked optional extra: {{fullname}}")
                return None

        sys.meta_path.insert(0, _Blocker())

        for mod_name in (
            "cxidk",
            "cxidk.workflow.format",
            "cxidk.workflow.ops",
            "cxidk.workflow.role_recognizer",
            "cxidk.ai.tools",
            "cxidk.ai.mcp.server",
            "cxidk.ai.mcp.resources",
            "cxidk.ai.adk.toolset",
        ):
            importlib.import_module(mod_name)

        script_path = Path({str(REPO_ROOT / ".github" / "scripts" / "gen_llms_txt.py")!r})
        spec = importlib.util.spec_from_file_location("gen_llms_txt", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.main(["--check"]) == 0

        from cxidk import CxContext
        from cxidk.ai.tools import conversations
        from cxidk.core import errors

        fake_auth = MagicMock()
        fake_auth.credentials = MagicMock()
        cx = CxContext(project_id="demo-proj-01", location="us-central1", auth=fake_auth)
        try:
            conversations._redact_texts_with_dlp(
                ["Alice email alice@example.com"],
                cx,
                deidentify_template="projects/demo-proj-01/deidentifyTemplates/t1",
                inspect_template=None,
            )
        except errors.InvalidArgumentError as exc:
            assert "optional `dlp` extra" in str(exc)
        else:
            raise AssertionError("Expected InvalidArgumentError when dlp extra is missing")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"STDERR:\\n{proc.stderr}\\nSTDOUT:\\n{proc.stdout}"
