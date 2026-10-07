"""Platform simulations and contamination counterexamples for wheel checks."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

check_core_dependencies = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tools/check_wheel_environment.py")
)["check_core_dependencies"]

TZDATA = 'tzdata>=2024.1; sys_platform == "win32"'
PIX = ("pix", "0.5.0")


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_declared_windows_dependency_is_only_installed_where_active(platform):
    installed = [PIX] + ([("tzdata", "2026.4")] if platform == "win32" else [])
    result = check_core_dependencies(
        [TZDATA, 'pytest; extra == "dev"', 'pyarrow>=14; extra == "imports"'],
        installed,
        platform,
    )
    assert result["active_core_dependencies"] == (
        ["tzdata"] if platform == "win32" else []
    )


def test_marker_whitespace_and_quotes_do_not_change_contract():
    result = check_core_dependencies(
        ["tzdata >= 2024.1 ; sys_platform=='win32'"],
        [("TZDATA", "2024.1"), ("PIX", "0.5.0")],
        "win32",
    )
    assert result["expected_distributions"] == ["pix", "tzdata"]


@pytest.mark.parametrize(
    "unexpected",
    [
        "numpy>=1",
        'numpy; sys_platform == "win32"',
        'tzdata>=2024.1; sys_platform != "win32"',
        'tzdata>=2024.1; sys_platform == "linux"',
        'tzdata>=2023.1; sys_platform == "win32"',
        "tzdata>=2024.1",
        'numpy; extra == "dev" or sys_platform == "linux"',
        'numpy; extra == ""',
        'numpy; extra == "dev"; extra == "browser"',
    ],
)
def test_inactive_platform_and_extra_text_cannot_hide_unexpected_runtime(unexpected):
    with pytest.raises(RuntimeError, match="Unexpected wheel dependency declaration"):
        check_core_dependencies([TZDATA, unexpected], [PIX], "linux")


@pytest.mark.parametrize("requirements", [[], [TZDATA, TZDATA]])
def test_missing_or_duplicate_core_declaration_is_contract_drift(requirements):
    with pytest.raises(RuntimeError, match="exactly one"):
        check_core_dependencies(requirements, [PIX], "linux")


@pytest.mark.parametrize(
    ("platform", "installed"),
    [
        ("win32", [PIX]),
        ("linux", [PIX, ("tzdata", "2026.4")]),
        ("darwin", [PIX, ("numpy", "2.0")]),
        ("win32", [PIX, ("tzdata", "2026.4"), ("pytest", "9.1")]),
        ("linux", [PIX, ("pip", "25.0")]),
        ("linux", [PIX, PIX]),
        ("linux", []),
    ],
)
def test_missing_dependency_or_contaminated_core_environment_is_rejected(
    platform, installed
):
    with pytest.raises(RuntimeError, match="requires only"):
        check_core_dependencies([TZDATA], installed, platform)


@pytest.mark.parametrize("version", ["2023.4", "2024.0", "2026.4rc1", "unknown"])
def test_windows_requires_supported_stable_tzdata_at_or_above_floor(version):
    with pytest.raises(RuntimeError, match="stable tzdata"):
        check_core_dependencies([TZDATA], [PIX, ("tzdata", version)], "win32")
