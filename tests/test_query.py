from __future__ import annotations

import asyncio
import math

import numpy as np
import pytest
from forge_msgs import JointState

from forge_tool import ToolContext, ToolEndpointError, ToolExecutionKey, ToolRequest
from relative_pose_policy_node.query import (
    RELATIVE_DESCRIPTOR,
    RelativePoseQuery,
    RelativePoseQueryEndpoint,
)
from relative_pose_policy_node.resolver import RelativePoseResolver, _rotation_matrix


def _context(*, deadline_ms: int | None = None) -> ToolContext:
    return ToolContext(
        execution_key=ToolExecutionKey("invoke-1", "attempt-1"),
        tool_id="motion.relative",
        implementation_id="relative-policy",
        endpoint_id="motion.relative_pose",
        operation="resolve",
        deadline_ms=deadline_ms,
    )


def _arguments(**updates):
    values = {
        "group_name": "arm",
        "target_frame": "tcp",
        "reference": "current",
        "translation_frame": "base",
        "translation_m": {"x": 0.1, "y": -0.2, "z": 0.3},
        "orientation_mode": "preserve",
        "axis_angle_rad": None,
        "max_state_age_ms": 100,
    }
    values.update(updates)
    return values


def _state(names=None) -> JointState:
    return JointState(
        name=names or ["j1", "j2", "j3"],
        position=[0.1, 0.2, 0.3],
        velocity=[],
        effort=[],
    )


def test_descriptor_is_query_endpoint() -> None:
    assert RELATIVE_DESCRIPTOR.endpoint_id == "motion.relative_pose"
    assert [(item.name, item.semantics) for item in RELATIVE_DESCRIPTOR.operations] == [
        ("resolve", "query")
    ]


def test_resolve_preserves_wire_contract_and_source_snapshot(
    policy_config, fake_kinematics
) -> None:
    resolver = RelativePoseResolver(
        policy_config, kinematics=fake_kinematics, clock_ns=lambda: 50_000_000
    )
    endpoint = RelativePoseQueryEndpoint(resolver)
    resolver.update_joint_state(
        JointState(
            name=["j3", "extra", "j1", "j2"],
            position=[0.3, 8.0, 0.1, 0.2],
            velocity=[],
            effort=[],
        ),
        now_ns=10_000_000,
    )

    result = asyncio.run(endpoint.query(ToolRequest(_arguments()), _context()))

    assert result.status == "succeeded"
    assert result.outputs["source_pose"] == {
        "x": 0.1,
        "y": 0.2,
        "z": 0.3,
        "qx": 0.0,
        "qy": 0.0,
        "qz": 0.0,
        "qw": 1.0,
    }
    assert result.outputs["target_pose"]["x"] == pytest.approx(0.2)
    assert result.outputs["target_pose"]["y"] == pytest.approx(0.0)
    assert result.outputs["target_pose"]["z"] == pytest.approx(0.6)
    assert result.outputs["frames"] == {
        "reference_frame": "base",
        "target_frame": "tcp",
        "translation_frame": "base",
        "rotation_frame": "tcp",
    }
    assert result.outputs["source_snapshot"] == {
        "version": 1,
        "received_monotonic_ns": 10_000_000,
        "age_ms": 40.0,
        "time_basis": "policy_receive_monotonic",
    }
    assert "joint_state" not in result.outputs
    assert "positions" not in result.outputs


def test_applies_tcp_translation_and_axis_angle(policy_config, fake_kinematics) -> None:
    query = RelativePoseQuery(policy_config, kinematics=fake_kinematics, clock_ns=lambda: 10)
    query.update_joint_state(_state(), now_ns=0)

    result = asyncio.run(
        query.query(
            ToolRequest(
                _arguments(
                    translation_frame="tcp",
                    translation_m={"x": 0.0, "y": 0.0, "z": 0.1},
                    orientation_mode="apply_delta",
                    axis_angle_rad={"x": 0.0, "y": 0.0, "z": math.pi},
                )
            ),
            _context(),
        )
    )

    assert result.outputs["target_pose"]["z"] == pytest.approx(0.4)
    assert abs(result.outputs["target_pose"]["qz"]) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("mode", "rotation"),
    [
        ("keep", None),
        ("quaternion", [0.0, 0.0, 1.0, 0.0]),
        ("rpy", [0.2, -0.3, 0.4]),
    ],
)
def test_legacy_orientation_modes_remain_accepted(
    policy_config, fake_kinematics, mode, rotation
) -> None:
    query = RelativePoseQuery(policy_config, kinematics=fake_kinematics, clock_ns=lambda: 10)
    query.update_joint_state(_state(), now_ns=0)
    arguments = _arguments(orientation_mode=mode)
    arguments.pop("axis_angle_rad")
    arguments["rotation"] = rotation

    assert asyncio.run(query.query(ToolRequest(arguments), _context())).status == "succeeded"


def test_legacy_rpy_is_rz_ry_rx() -> None:
    roll, pitch, yaw = 0.2, -0.3, 0.4
    rx = np.array(
        [[1, 0, 0], [0, math.cos(roll), -math.sin(roll)], [0, math.sin(roll), math.cos(roll)]]
    )
    ry = np.array(
        [
            [math.cos(pitch), 0, math.sin(pitch)],
            [0, 1, 0],
            [-math.sin(pitch), 0, math.cos(pitch)],
        ]
    )
    rz = np.array(
        [[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]]
    )
    assert np.allclose(_rotation_matrix("rpy", [roll, pitch, yaw]), rz @ ry @ rx)


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"reference": "named"}, "MOTION_INVALID_ARGUMENT"),
        ({"translation_frame": "world"}, "MOTION_INVALID_ARGUMENT"),
        ({"target_frame": "camera"}, "MOTION_INVALID_FRAME"),
        ({"group_name": "other"}, "MOTION_INVALID_GROUP"),
        ({"extra": True}, "MOTION_INVALID_ARGUMENT"),
    ],
)
def test_strict_contract_errors(policy_config, fake_kinematics, updates, code) -> None:
    query = RelativePoseQuery(policy_config, kinematics=fake_kinematics)
    with pytest.raises(ToolEndpointError) as captured:
        asyncio.run(query.query(ToolRequest(_arguments(**updates)), _context()))
    assert captured.value.error.code == code


def test_freshness_incomplete_and_deadline_errors(policy_config, fake_kinematics) -> None:
    stale = RelativePoseQuery(
        policy_config, kinematics=fake_kinematics, clock_ns=lambda: 200_000_000
    )
    stale.update_joint_state(_state(), now_ns=0)
    with pytest.raises(ToolEndpointError) as captured:
        asyncio.run(stale.query(ToolRequest(_arguments()), _context()))
    assert captured.value.error.code == "MOTION_NO_FRESH_ROBOT_STATE"
    assert captured.value.error.retryable is True

    incomplete = RelativePoseQuery(
        policy_config, kinematics=fake_kinematics, clock_ns=lambda: 10
    )
    incomplete.update_joint_state(
        JointState(name=["j1"], position=[0.1], velocity=[], effort=[]), now_ns=0
    )
    with pytest.raises(ToolEndpointError) as captured:
        asyncio.run(incomplete.query(ToolRequest(_arguments()), _context()))
    assert captured.value.error.code == "MOTION_INCOMPLETE_STATE"
    assert captured.value.error.retryable is True

    expired = RelativePoseQuery(
        policy_config, kinematics=fake_kinematics, epoch_ms=lambda: 1_000
    )
    with pytest.raises(ToolEndpointError) as captured:
        asyncio.run(expired.query(ToolRequest(_arguments()), _context(deadline_ms=999)))
    assert captured.value.error.code == "FORGE_DEADLINE_EXCEEDED"
