from __future__ import annotations

import asyncio

from forge_msgs import JointState, ToolMessage
from forge_tool import (
    EndpointRegistryResponse,
    ToolContext,
    ToolEndpointHandler,
    ToolExecutionKey,
    ToolRequest,
    invoke_response_from_payload,
    make_endpoint_registry_response_envelope,
    make_invoke_request_envelope,
    validate_registration_envelope,
)
from forge_tool.dora import (
    DoraToolEndpointBinding,
    tool_envelope_to_message,
    tool_message_to_envelope,
)

from relative_pose_policy_node.endpoint_lease import EndpointLease
from relative_pose_policy_node.query import RELATIVE_DESCRIPTOR, RelativePoseQueryEndpoint
from relative_pose_policy_node.resolver import RelativePoseResolver
from relative_pose_policy_node.runner import RelativePosePolicyRunner


def _context() -> ToolContext:
    return ToolContext(
        execution_key=ToolExecutionKey("invocation", "attempt"),
        tool_id="motion.relative",
        implementation_id="relative-policy",
        endpoint_id="motion.relative_pose",
        operation="resolve",
    )


def _request() -> ToolRequest:
    return ToolRequest(
        {
            "group_name": "arm",
            "target_frame": "tcp",
            "reference": "current",
            "translation_frame": "base",
            "translation_m": {"x": 0.1, "y": 0.0, "z": 0.0},
            "orientation_mode": "preserve",
            "axis_angle_rad": None,
            "max_state_age_ms": 100,
        }
    )


def _arrow(envelope):
    return tool_envelope_to_message(envelope).to_arrow()


def _envelope(batch):
    return tool_message_to_envelope(ToolMessage.from_arrow(batch))


def test_public_query_binding_dispatches_query(policy_config, fake_kinematics) -> None:
    resolver = RelativePoseResolver(
        policy_config, kinematics=fake_kinematics, clock_ns=lambda: 10
    )
    endpoint = RelativePoseQueryEndpoint(resolver)
    resolver.update_joint_state(
        JointState(
            name=["j1", "j2", "j3"],
            position=[0.1, 0.2, 0.3],
            velocity=[],
            effort=[],
        ),
        now_ns=0,
    )
    handler = ToolEndpointHandler(
        RELATIVE_DESCRIPTOR,
        endpoint_instance_id="instance-1",
        operations={"resolve": endpoint},
    )
    binding = DoraToolEndpointBinding(handler)
    invoke = make_invoke_request_envelope(
        _request(),
        _context(),
        request_id="invoke-1",
        endpoint_instance_id="instance-1",
    )

    response = _envelope(asyncio.run(binding.dispatch_input(_arrow(invoke)))[0])
    result = invoke_response_from_payload(response.payload)

    assert result.status == "succeeded"
    assert result.outputs["target_pose"]["x"] == 0.2


def test_endpoint_lease_registers_renews_and_unregisters() -> None:
    lease = EndpointLease(RELATIVE_DESCRIPTOR, "instance-1")
    registration = lease.poll(10.0)

    assert registration is not None
    assert validate_registration_envelope(registration) == RELATIVE_DESCRIPTOR
    response = make_endpoint_registry_response_envelope(
        EndpointRegistryResponse(
            operation="register",
            status="accepted",
            registry_revision=1,
            lease_ttl_ms=3000,
        ),
        registration,
    )
    assert lease.acknowledge(response, 10.1) is True
    assert lease.poll(11.09) is None
    assert lease.poll(11.1) is not None
    assert lease.stop().message_type == "endpoint.unregister"
    assert lease.stop() is None


class _Node:
    def __init__(self) -> None:
        self.envelopes = []

    def send_output(self, output_id, value, **kwargs) -> None:
        assert output_id == "tool_out"
        self.envelopes.append(_envelope(value))


def test_runner_registers_and_unregisters(policy_config, fake_kinematics) -> None:
    node = _Node()
    resolver = RelativePoseResolver(policy_config, kinematics=fake_kinematics)
    endpoint = RelativePoseQueryEndpoint(resolver)
    runner = RelativePosePolicyRunner(
        node,
        policy_config,
        resolver=resolver,
        endpoint=endpoint,
        endpoint_instance_id="instance-1",
        clock=lambda: 10.0,
    )

    runner._drive_lease()
    assert node.envelopes[-1].message_type == "endpoint.register"
    assert runner.process_event({"type": "STOP"}) == 0
    assert node.envelopes[-1].message_type == "endpoint.unregister"
