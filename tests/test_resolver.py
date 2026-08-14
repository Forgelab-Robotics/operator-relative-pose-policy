from __future__ import annotations

import pytest
from forge_msgs import JointState

from relative_pose_policy_node.resolver import (
    RelativePoseCommand,
    RelativePoseResolutionError,
    RelativePoseResolver,
)


def _command(**updates) -> RelativePoseCommand:
    values = {
        "group_name": "arm",
        "target_frame": "tcp",
        "reference": "current",
        "translation_frame": "base",
        "translation_m": (0.1, -0.2, 0.3),
        "orientation_mode": "preserve",
        "rotation": None,
        "max_state_age_ms": 100,
    }
    values.update(updates)
    return RelativePoseCommand(**values)


def _state() -> JointState:
    return JointState(
        name=["j1", "j2", "j3"],
        position=[0.1, 0.2, 0.3],
        velocity=[],
        effort=[],
    )


def test_resolver_owns_state_fk_and_relative_transform(policy_config, fake_kinematics) -> None:
    resolver = RelativePoseResolver(
        policy_config,
        kinematics=fake_kinematics,
        clock_ns=lambda: 50_000_000,
    )
    resolver.update_joint_state(_state(), now_ns=10_000_000)

    result = resolver.resolve(_command())

    assert result.source_pose.x == pytest.approx(0.1)
    assert result.target_pose.x == pytest.approx(0.2)
    assert result.target_pose.y == pytest.approx(0.0)
    assert result.target_pose.z == pytest.approx(0.6)
    assert result.snapshot_version == 1
    assert result.state_age_ms == 40.0


def test_resolver_reports_domain_error_without_tool_types(
    policy_config, fake_kinematics
) -> None:
    resolver = RelativePoseResolver(policy_config, kinematics=fake_kinematics)

    with pytest.raises(RelativePoseResolutionError) as captured:
        resolver.resolve(_command(group_name="other"))

    assert captured.value.code == "MOTION_INVALID_GROUP"
    assert captured.value.retryable is False


def test_resolver_requires_fresh_state(policy_config, fake_kinematics) -> None:
    resolver = RelativePoseResolver(
        policy_config,
        kinematics=fake_kinematics,
        clock_ns=lambda: 200_000_000,
    )
    resolver.update_joint_state(_state(), now_ns=0)

    with pytest.raises(RelativePoseResolutionError) as captured:
        resolver.resolve(_command())

    assert captured.value.code == "MOTION_NO_FRESH_ROBOT_STATE"
    assert captured.value.retryable is True


def test_resolver_rejects_invalid_typed_command(policy_config, fake_kinematics) -> None:
    resolver = RelativePoseResolver(policy_config, kinematics=fake_kinematics)

    with pytest.raises(RelativePoseResolutionError) as captured:
        resolver.resolve(_command(translation_frame="world"))

    assert captured.value.code == "MOTION_INVALID_ARGUMENT"
