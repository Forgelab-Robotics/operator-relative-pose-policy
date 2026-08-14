from __future__ import annotations

from pathlib import Path

import pytest

from relative_pose_policy_node.config import config_from_mapping, load_config


def _mapping(**updates):
    values = {
        "group_name": "arm",
        "joint_names": ["j1", "j2"],
        "urdf_path": "robot.urdf",
        "base_frame": "base",
        "tip_frame": "tcp",
    }
    values.update(updates)
    return values


def test_minimal_config_resolves_urdf_relative_to_config(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(
        "\n".join(
            [
                "group_name: arm",
                "joint_names: [j1, j2]",
                "urdf_path: models/robot.urdf",
                "base_frame: base",
                "tip_frame: tcp",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.group_name == "arm"
    assert config.joint_names == ("j1", "j2")
    assert config.urdf_path == (tmp_path / "models/robot.urdf").resolve()


@pytest.mark.parametrize(
    "mapping",
    [
        _mapping(extra=True),
        {key: value for key, value in _mapping().items() if key != "tip_frame"},
        _mapping(joint_names=["j1", "j1"]),
        _mapping(group_name=""),
        _mapping(urdf_path=""),
    ],
)
def test_config_rejects_non_minimal_or_invalid_values(mapping) -> None:
    with pytest.raises(ValueError):
        config_from_mapping(mapping)
