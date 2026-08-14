from __future__ import annotations

import math
from pathlib import Path

import pytest

from relative_pose_policy_node.config import RelativePosePolicyConfig
from relative_pose_policy_node.kinematics import ForgeKinematicsAdapter


def test_forge_kinematics_adapter_computes_fk(tmp_path: Path) -> None:
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(
        """\
<?xml version="1.0"?>
<robot name="one_joint">
  <link name="base"/>
  <link name="arm"/>
  <joint name="j1" type="revolute">
    <parent link="base"/>
    <child link="arm"/>
    <axis xyz="0 0 1"/>
    <limit lower="-3.14" upper="3.14" effort="1" velocity="1"/>
  </joint>
  <link name="tcp"/>
  <joint name="tip" type="fixed">
    <parent link="arm"/>
    <child link="tcp"/>
    <origin xyz="1 0 0"/>
  </joint>
</robot>
""",
        encoding="utf-8",
    )
    config = RelativePosePolicyConfig(
        group_name="arm",
        joint_names=("j1",),
        urdf_path=urdf,
        base_frame="base",
        tip_frame="tcp",
    )

    pose = ForgeKinematicsAdapter(config).forward((math.pi / 2,))

    assert pose.x == pytest.approx(0.0, abs=1e-9)
    assert pose.y == pytest.approx(1.0, abs=1e-9)
    assert abs(pose.qz) == pytest.approx(math.sqrt(0.5))
    assert abs(pose.qw) == pytest.approx(math.sqrt(0.5))
