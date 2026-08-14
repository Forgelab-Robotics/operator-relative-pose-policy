from __future__ import annotations

import os
import shlex
from pathlib import Path

import yaml


def _workspace_root() -> Path:
    configured = os.environ.get("FORGE_WORKSPACE_ROOT")
    candidates = [Path(configured).expanduser().resolve()] if configured else []
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (
            candidate.joinpath(
                "forge_runtime", "examples", "move_arm_by_ee_skill", "dataflow.yaml"
            ).is_file()
            and candidate.joinpath("policy_node", "relative_pose_policy_node").is_dir()
        ):
            return candidate
    raise RuntimeError(
        "cannot locate sibling workspaces; set FORGE_WORKSPACE_ROOT to their common parent"
    )


WORKSPACE_ROOT = _workspace_root()
EXAMPLE_DIR = WORKSPACE_ROOT / "forge_runtime" / "examples" / "move_arm_by_ee_skill"

EXPECTED_NODES = {
    "dataflow.yaml": {
        "gateway",
        "relative_motion_policy",
        "motion_action_policy",
    },
    "dataflow.fake.yaml": {
        "skill_caller",
        "gateway",
        "relative_motion_policy",
        "motion_action_policy",
        "motion_server",
        "joint_trajectory_controller",
        "fake_joint_plant",
    },
    "dataflow.mujoco.yaml": {
        "gateway",
        "relative_motion_policy",
        "motion_action_policy",
        "motion_server",
        "joint_trajectory_controller",
        "mujoco",
        "image_viewer",
    },
    "dataflow.robot.yaml": {
        "gateway",
        "relative_motion_policy",
        "motion_action_policy",
        "motion_server",
        "joint_trajectory_controller",
        "robot_driver",
    },
}


def _load(name: str) -> dict:
    return yaml.safe_load((EXAMPLE_DIR / name).read_text(encoding="utf-8"))


def _nodes(name: str) -> dict[str, dict]:
    return {node["id"]: node for node in _load(name)["nodes"]}


def test_dataflows_have_exact_environment_node_sets() -> None:
    for name, expected in EXPECTED_NODES.items():
        assert set(_nodes(name)) == expected


def test_fake_smoke_closes_the_motion_loop() -> None:
    nodes = _nodes("dataflow.fake.yaml")
    assert nodes["gateway"]["path"] == "${FORGE_RUNTIME_BIN}/gateway"
    assert nodes["gateway"]["inputs"]["tool_request"] == "skill_caller/tool_request"
    assert (
        nodes["joint_trajectory_controller"]["inputs"]["joint_state"]
        == "fake_joint_plant/joint_state"
    )
    assert (
        nodes["fake_joint_plant"]["inputs"]["joint_command"]
        == "joint_trajectory_controller/joint_command"
    )
    assert nodes["motion_server"]["inputs"]["trajectory_result"] == (
        "joint_trajectory_controller/trajectory_result"
    )


def test_mujoco_connects_state_and_action_ports() -> None:
    nodes = _nodes("dataflow.mujoco.yaml")
    assert nodes["mujoco"]["path"] == "${FORGE_RUNTIME_BIN}/mujoco_sim"
    assert (
        nodes["mujoco"]["inputs"]["action"]
        == "joint_trajectory_controller/joint_command"
    )
    for consumer in (
        "relative_motion_policy",
        "motion_server",
        "joint_trajectory_controller",
    ):
        assert nodes[consumer]["inputs"]["joint_state"] == "mujoco/proprio_state"
    viewer = nodes["image_viewer"]
    assert viewer["path"] == "${FORGE_RUNTIME_BIN}/image_viewer"
    assert viewer["inputs"]["image/hand"] == "mujoco/image/hand"
    assert set(nodes["mujoco"]["outputs"]) >= {
        "proprio_state",
        "image/hand",
        "image/top",
        "image/angle",
        "image/left_pillar",
    }


def test_robot_connects_state_and_action_ports_without_touching_can() -> None:
    nodes = _nodes("dataflow.robot.yaml")
    driver = nodes["robot_driver"]
    assert driver["inputs"]["action"] == "joint_trajectory_controller/joint_command"
    assert driver["path"] == "${FORGE_RUNTIME_BIN}/robots/robots_agilex_piper"
    assert driver["args"] == "run --config robot.yaml"
    for consumer in (
        "relative_motion_policy",
        "motion_server",
        "joint_trajectory_controller",
    ):
        assert nodes[consumer]["inputs"]["joint_state"] == "robot_driver/state"


def test_all_relative_project_script_and_config_paths_exist() -> None:
    for name in EXPECTED_NODES:
        for node in _nodes(name).values():
            path = node.get("path")
            if (
                isinstance(path, str)
                and (path.startswith(".") or "/" in path)
                and "${" not in path
            ):
                assert (EXAMPLE_DIR / path).resolve().exists(), (name, node["id"], path)

            args = shlex.split(node.get("args", ""))
            for option in ("--project", "--config"):
                if option in args:
                    value = args[args.index(option) + 1]
                    assert (EXAMPLE_DIR / value).resolve().exists(), (
                        name,
                        node["id"],
                        value,
                    )
            if "python" in args:
                script = args[args.index("python") + 1]
                assert (EXAMPLE_DIR / script).resolve().is_file(), (
                    name,
                    node["id"],
                    script,
                )

    simulator = yaml.safe_load(
        (EXAMPLE_DIR / "simulator.yaml").read_text(encoding="utf-8")
    )
    assert (EXAMPLE_DIR / simulator["model_path"]).resolve().is_file()

    relative_policy = yaml.safe_load(
        (EXAMPLE_DIR / "relative_pose_policy.yaml").read_text(encoding="utf-8")
    )
    assert (EXAMPLE_DIR / relative_policy["urdf_path"]).resolve().is_file()

    motion_server = yaml.safe_load(
        (EXAMPLE_DIR / "motion_server.yaml").read_text(encoding="utf-8")
    )
    for group in motion_server["groups"].values():
        assert (EXAMPLE_DIR / group["urdf_path"]).resolve().is_file()


def test_hardware_and_binary_prerequisites_are_documented_only() -> None:
    readme = (EXAMPLE_DIR / "README.md").read_text(encoding="utf-8")
    robot = (EXAMPLE_DIR / "robot.yaml").read_text(encoding="utf-8")
    assert "${FORGE_RUNTIME_BIN}/mujoco_sim" in readme
    assert "不启动" in readme and "仿真" in readme
    assert "不要把它当 smoke test 运行" in readme
    assert "DANGER" in robot
