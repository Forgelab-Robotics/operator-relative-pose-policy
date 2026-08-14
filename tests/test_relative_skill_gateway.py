from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path


def _workspace_root() -> Path:
    configured = os.environ.get("FORGE_WORKSPACE_ROOT")
    candidates = [Path(configured).expanduser().resolve()] if configured else []
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (
            (candidate / "forge_gateway" / "src").is_dir()
            and (candidate / "motion" / "packages" / "motion_server" / "src").is_dir()
            and (
                candidate
                / "forge_runtime"
                / "examples"
                / "move_arm_by_ee_skill"
                / "gateway.yaml"
            ).is_file()
        ):
            return candidate
    raise RuntimeError(
        "cannot locate sibling workspaces; set FORGE_WORKSPACE_ROOT to their common parent"
    )


WORKSPACE_ROOT = _workspace_root()
GATEWAY_SRC = WORKSPACE_ROOT / "forge_gateway" / "src"
MOTION_SERVER_SRC = WORKSPACE_ROOT / "motion" / "packages" / "motion_server" / "src"
EXAMPLE_DIR = WORKSPACE_ROOT / "forge_runtime" / "examples" / "move_arm_by_ee_skill"
EXAMPLE_FILE = EXAMPLE_DIR / "skill_caller.py"
sys.path[:0] = [str(GATEWAY_SRC), str(MOTION_SERVER_SRC)]

from forge_gateway.config import GatewayConfig  # noqa: E402
from forge_gateway.services.runtime_service import GatewayRuntime  # noqa: E402
from forge_motion_server.action_endpoint import ACTION_DESCRIPTOR  # noqa: E402
from forge_msgs import ToolMessage  # noqa: E402
from forge_tool import (  # noqa: E402
    EndpointRegistryResponse,
    ToolAccepted,
    ToolControlResponse,
    ToolError,
    ToolEvent,
    ToolExecutionStatus,
    ToolResult,
    ToolResultResponse,
    invoke_request_from_envelope,
    make_control_response_envelope,
    make_endpoint_registry_response_envelope,
    make_error_response_envelope,
    make_event_envelope,
    make_invoke_response_envelope,
    make_registration_envelope,
    make_result_request_envelope,
    make_result_response_envelope,
    make_status_response_envelope,
)
from forge_tool.dora import tool_envelope_to_message, tool_message_to_envelope  # noqa: E402

from relative_pose_policy_node.query import RELATIVE_DESCRIPTOR  # noqa: E402


def _load_skill_class():
    spec = importlib.util.spec_from_file_location("move_arm_by_ee_skill_caller", EXAMPLE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RelativeMotionSkill


class _Node:
    def __init__(self) -> None:
        self.sent = []

    def send_output(self, output_id, value) -> None:
        assert output_id == "tool_request"
        self.sent.append(tool_message_to_envelope(ToolMessage.from_arrow(value)))


def _config() -> GatewayConfig:
    return GatewayConfig.from_yaml_path(EXAMPLE_DIR / "gateway.yaml")


def _register(runtime: GatewayRuntime, descriptor, input_id: str, instance: str) -> None:
    request = make_registration_envelope(
        descriptor,
        endpoint_instance_id=instance,
        request_id=f"register-{instance}",
    )
    runtime.tool_gateway.handle_input(input_id, request, received_at=time.monotonic())
    outbound = runtime.tool_gateway.take_outbound()
    assert outbound is not None
    response = make_endpoint_registry_response_envelope(
        EndpointRegistryResponse(
            operation="register",
            status="accepted",
            registry_revision=1,
            lease_ttl_ms=15_000,
        ),
        request,
    )
    assert outbound.envelope.message_type == response.message_type


def _send_caller(runtime: GatewayRuntime, request, expected_tool_id: str):
    assert request.endpoint_instance_id is None
    context = request.payload.get("context")
    if context is not None:
        assert context["tool_id"] == expected_tool_id
    else:
        assert expected_tool_id == {
            "move_pose": "motion.move_pose",
            "move_joints": "motion.move_joints",
        }[request.operation]
    runtime.tool_gateway.handle_input(
        "tool_request",
        request,
        received_at=time.monotonic(),
    )
    outbound = runtime.tool_gateway.take_outbound()
    assert outbound is not None
    assert outbound.envelope.endpoint_instance_id is not None
    return outbound


def _return_provider(runtime: GatewayRuntime, input_id: str, response):
    runtime.tool_gateway.handle_input(input_id, response, received_at=time.monotonic())
    outbound = runtime.tool_gateway.take_outbound()
    assert outbound is not None
    assert outbound.output_id == "tool_response"
    assert outbound.envelope.endpoint_instance_id is None
    return tool_envelope_to_message(outbound.envelope).to_arrow()


def test_real_gateway_public_caller_lifecycle_uses_production_tool_ids(tmp_path) -> None:
    runtime = GatewayRuntime(_config())
    node = _Node()
    skill = _load_skill_class()(node, tmp_path / "result.json")
    try:
        _register(runtime, RELATIVE_DESCRIPTOR, "relative_tool_in", "relative-instance")
        _register(runtime, ACTION_DESCRIPTOR, "action_tool_in", "action-instance")

        skill.start()
        query = _send_caller(runtime, node.sent.pop(0), "motion.resolve_relative_pose")
        query_result = ToolResult(
            status="succeeded",
            outputs={
                "target_pose": {
                    "x": 0.1,
                    "y": 0.2,
                    "z": 0.3,
                    "qx": 0.0,
                    "qy": 0.0,
                    "qz": 0.0,
                    "qw": 1.0,
                }
            },
        )
        skill.handle(
            _return_provider(
                runtime,
                "relative_tool_in",
                make_invoke_response_envelope(query_result, query.envelope),
            )
        )

        pose = _send_caller(runtime, node.sent.pop(0), "motion.move_pose")
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_invoke_response_envelope(ToolAccepted(), pose.envelope),
            )
        )
        assert len(node.sent) == 2
        status_request = _send_caller(runtime, node.sent.pop(0), "motion.move_pose")
        result_request = _send_caller(runtime, node.sent.pop(0), "motion.move_pose")
        _, provider_context = invoke_request_from_envelope(pose.envelope)
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_event_envelope(
                    ToolEvent(type="progress", data={"progress": 0.5}),
                    provider_context,
                    endpoint_instance_id="action-instance",
                    sequence=0,
                ),
            )
        )
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_status_response_envelope(
                    ToolExecutionStatus(phase="running"),
                    status_request.envelope,
                ),
            )
        )
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_result_response_envelope(
                    ToolResultResponse(
                        status="available",
                        result=ToolResult(status="succeeded"),
                    ),
                    result_request.envelope,
                ),
            )
        )

        joints = _send_caller(runtime, node.sent.pop(0), "motion.move_joints")
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_invoke_response_envelope(ToolAccepted(), joints.envelope),
            )
        )
        cancel = _send_caller(runtime, node.sent.pop(0), "motion.move_joints")
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_control_response_envelope(
                    ToolControlResponse(command="cancel", status="accepted"),
                    cancel.envelope,
                ),
            )
        )
        assert all(request.endpoint_instance_id is None for request in node.sent)
        cancel_status = _send_caller(runtime, node.sent.pop(0), "motion.move_joints")
        cancel_result = _send_caller(runtime, node.sent.pop(0), "motion.move_joints")
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_status_response_envelope(
                    ToolExecutionStatus(phase="stopping"),
                    cancel_status.envelope,
                ),
            )
        )
        skill.handle(
            _return_provider(
                runtime,
                "action_tool_in",
                make_result_response_envelope(
                    ToolResultResponse(
                        status="available",
                        result=ToolResult(status="cancelled"),
                    ),
                    cancel_result.envelope,
                ),
            )
        )
        assert skill.completed is True
        assert skill.events == ["progress"]
    finally:
        runtime.close()


def test_skill_retries_busy_lifecycle_lookup(tmp_path) -> None:
    node = _Node()
    skill = _load_skill_class()(node, tmp_path / "result.json")
    skill.phase = "cancel_active"
    context = skill.context(
        "motion.move_joints",
        "motion.server",
        "move_joints",
        "joints-cancel-1",
    )
    request = make_result_request_envelope(
        context,
        request_id="busy-result",
        endpoint_instance_id=None,
    )
    skill.send(request, "result")

    error = make_error_response_envelope(
        ToolError(
            code="FORGE_TOOL_GATEWAY_BUSY",
            message="an Action result lookup is already pending",
            retryable=True,
        ),
        request,
    )
    skill.handle(tool_envelope_to_message(error).to_arrow())

    assert skill.phase == "cancel_active"
    assert "busy-result" not in skill.responses
    assert skill.next_poll > time.monotonic()
