from __future__ import annotations

import math
from typing import Protocol

import numpy as np
from forge_kinematics import RobotModel
from forge_msgs import Pose

from .config import RelativePosePolicyConfig


class ForwardKinematics(Protocol):
    def forward(self, positions: tuple[float, ...]) -> Pose: ...


class ForgeKinematicsAdapter:
    def __init__(self, config: RelativePosePolicyConfig) -> None:
        model = RobotModel.from_urdf(config.urdf_path)
        self._group = model.create_group(
            name=config.group_name,
            joint_names=config.joint_names,
            base_frame=config.base_frame,
            tip_frames=(config.tip_frame,),
        )

    def forward(self, positions: tuple[float, ...]) -> Pose:
        return matrix_to_pose(self._group.forward(positions))


def pose_to_matrix(pose: Pose) -> np.ndarray:
    values = (pose.x, pose.y, pose.z, pose.qx, pose.qy, pose.qz, pose.qw)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("pose values must be finite")
    norm = math.sqrt(pose.qx**2 + pose.qy**2 + pose.qz**2 + pose.qw**2)
    if norm <= 1e-12:
        raise ValueError("pose quaternion norm is too small")
    x, y, z, w = (pose.qx / norm, pose.qy / norm, pose.qz / norm, pose.qw / norm)
    rotation = np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = np.array([pose.x, pose.y, pose.z], dtype=np.float64)
    return matrix


def matrix_to_pose(matrix: object) -> Pose:
    transform = np.array(matrix, dtype=np.float64, copy=True)
    if transform.shape != (4, 4) or not np.all(np.isfinite(transform)):
        raise ValueError("FK transform must be a finite 4x4 matrix")
    rotation = transform[:3, :3]
    qx, qy, qz, qw = _quaternion_from_rotation(rotation)
    return Pose(
        x=float(transform[0, 3]),
        y=float(transform[1, 3]),
        z=float(transform[2, 3]),
        qx=qx,
        qy=qy,
        qz=qz,
        qw=qw,
    )


def _quaternion_from_rotation(rotation: np.ndarray) -> tuple[float, float, float, float]:
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * scale
        qx = (rotation[2, 1] - rotation[1, 2]) / scale
        qy = (rotation[0, 2] - rotation[2, 0]) / scale
        qz = (rotation[1, 0] - rotation[0, 1]) / scale
    else:
        index = int(np.argmax(np.diag(rotation)))
        if index == 0:
            scale = math.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0
            qw = (rotation[2, 1] - rotation[1, 2]) / scale
            qx = 0.25 * scale
            qy = (rotation[0, 1] + rotation[1, 0]) / scale
            qz = (rotation[0, 2] + rotation[2, 0]) / scale
        elif index == 1:
            scale = math.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0
            qw = (rotation[0, 2] - rotation[2, 0]) / scale
            qx = (rotation[0, 1] + rotation[1, 0]) / scale
            qy = 0.25 * scale
            qz = (rotation[1, 2] + rotation[2, 1]) / scale
        else:
            scale = math.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0
            qw = (rotation[1, 0] - rotation[0, 1]) / scale
            qx = (rotation[0, 2] + rotation[2, 0]) / scale
            qy = (rotation[1, 2] + rotation[2, 1]) / scale
            qz = 0.25 * scale
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    return qx / norm, qy / norm, qz / norm, qw / norm


__all__ = ["ForgeKinematicsAdapter", "ForwardKinematics", "matrix_to_pose", "pose_to_matrix"]
