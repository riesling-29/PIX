"""Standard-library-only checks for PIX's core wheel dependency contract.

This is deliberately a narrow allowlist for the metadata emitted by the current
pyproject.toml, not a general PEP 508 evaluator. New core requirements or compound
extra markers need an explicit contract review. Do not install packaging into
the wheel-only smoke environment just to inspect its dependencies.
"""

from __future__ import annotations

import re

_WINDOWS_TZDATA = re.compile(
    r"tzdata\s*>=\s*2024\.1\s*;\s*sys_platform\s*==\s*(['\"])win32\1",
    re.IGNORECASE,
)
_OPTIONAL_ONLY = re.compile(
    r"[^;]+;\s*extra\s*==\s*(['\"])(dev|browser|excel|parquet|imports)\1"
)


def check_core_dependencies(
    requirements: list[str], distributions: list[tuple[str, str]], platform: str
) -> dict:
    """Reject metadata drift and anything beyond PIX plus active Windows tzdata.

    ``platform`` is the interpreter's sys.platform in real smoke runs. Tests
    pass explicit platforms to exercise the marker contract without claiming
    that another operating system was executed.
    """
    runtime = []
    optional = []
    for raw in requirements:
        requirement = raw.strip()
        if _WINDOWS_TZDATA.fullmatch(requirement):
            runtime.append(raw)
        elif _OPTIONAL_ONLY.fullmatch(requirement):
            optional.append(raw)
        else:
            raise RuntimeError(f"Unexpected wheel dependency declaration: {raw}")
    if len(runtime) != 1:
        raise RuntimeError(
            "Expected exactly one Windows-only tzdata>=2024.1 declaration"
        )

    installed = sorted(
        (re.sub(r"[-_.]+", "-", name).lower(), version)
        for name, version in distributions
    )
    expected = ["pix", "tzdata"] if platform == "win32" else ["pix"]
    if [name for name, _ in installed] != expected:
        raise RuntimeError(
            f"Core smoke on {platform} requires only {expected}; found {installed}"
        )
    if platform == "win32":
        version = dict(installed)["tzdata"]
        match = re.fullmatch(r"([0-9]{4})\.([0-9]+)", version)
        if match is None or tuple(map(int, match.groups())) < (2024, 1):
            raise RuntimeError(
                f"Expected stable tzdata>=2024.1 in YYYY.N form; found {version}"
            )

    return {
        "platform": platform,
        "declared_core_requirements": runtime,
        "inactive_optional_requirements": optional,
        "active_core_dependencies": ["tzdata"] if platform == "win32" else [],
        "expected_distributions": expected,
        "installed_distributions": installed,
    }
