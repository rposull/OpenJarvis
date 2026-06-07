"""Tests for network/channel-triggered tool auto-approval gating.

By default, unattended network paths (inbound SMS/iMessage/SendBlue, managed
agent streams) must NOT auto-approve tools that require confirmation
(shell_exec, git_commit, agent_kill). The opt-in
``[security] network_tool_auto_approve`` flag restores the old behavior.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

from openjarvis.server.agent_manager_routes import (  # noqa: E402
    _network_tool_confirm_callback,
)


class _Security:
    def __init__(self, auto_approve: bool) -> None:
        self.network_tool_auto_approve = auto_approve


class _Config:
    def __init__(self, auto_approve: bool) -> None:
        self.security = _Security(auto_approve)


def test_default_returns_none_so_tools_are_denied():
    # None callback => ToolExecutor denies requires_confirmation tools.
    assert _network_tool_confirm_callback(_Config(False)) is None


def test_optin_returns_auto_approving_callback():
    cb = _network_tool_confirm_callback(_Config(True))
    assert cb is not None
    assert cb("Allow execution of tool 'shell_exec'?") is True


def test_default_config_is_secure():
    # With no app_config passed, the real default config is loaded; the
    # shipped default keeps auto-approval OFF.
    assert _network_tool_confirm_callback() is None


def test_executor_denies_confirmation_tool_without_callback():
    """End-to-end: a requires_confirmation tool is denied when callback=None."""
    from openjarvis.core.types import ToolCall, ToolResult
    from openjarvis.tools._stubs import (
        BaseTool,
        ToolExecutor,
        ToolSpec,
    )

    class _DangerTool(BaseTool):
        tool_id = "danger"
        is_local = True

        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(
                name="danger",
                description="needs confirmation",
                parameters={"type": "object", "properties": {}},
                requires_confirmation=True,
            )

        def execute(self, **params):  # pragma: no cover - must not run
            return ToolResult(tool_name="danger", content="ran", success=True)

    executor = ToolExecutor(
        tools=[_DangerTool()],
        interactive=True,
        confirm_callback=_network_tool_confirm_callback(_Config(False)),
    )
    result = executor.execute(
        ToolCall(id="1", name="danger", arguments="{}")
    )
    assert result.success is False
    assert "confirmation" in result.content.lower()
