from __future__ import annotations

from pathlib import Path

import pytest
from forge_msgs import Pose

from relative_pose_policy_node.config import RelativePosePolicyConfig


class FakeKinematics:
    def forward(self, positions: tuple[float, ...]) -> Pose:
        return Pose(x=positions[0], y=positions[1], z=positions[2])


@pytest.fixture
def policy_config() -> RelativePosePolicyConfig:
    return RelativePosePolicyConfig(
        group_name="arm",
        joint_names=("j1", "j2", "j3"),
        urdf_path=Path("unused.urdf"),
        base_frame="base",
        tip_frame="tcp",
    )


@pytest.fixture
def fake_kinematics() -> FakeKinematics:
    return FakeKinematics()
