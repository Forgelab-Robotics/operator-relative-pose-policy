# Tool Contracts

## `motion.relative_pose/resolve`

The endpoint descriptor contains one Query operation, `resolve`, with concurrency 1.

The wire contract is implemented by `RelativePoseQueryEndpoint`. After strict parsing, it passes a
typed `RelativePoseCommand` to the protocol-independent `RelativePoseResolver`. The resolver never
receives `ToolRequest`/`ToolContext` and never creates `ToolResult`; this keeps Forge protocol
behavior separate from FK and coordinate-transform behavior without creating another process.

Requests contain exactly:

- `group_name`: the configured group.
- `target_frame`: the configured tip frame.
- `reference`: literal `current`.
- `translation_frame`: `tcp` or `base`.
- `translation_m`: finite metre values with exactly `x`, `y`, and `z`.
- `orientation_mode`: `preserve` or `apply_delta`.
- `axis_angle_rad`: `null` for `preserve`; for `apply_delta`, a rotation vector object with
  exactly `x`, `y`, and `z`, whose direction is the axis and magnitude is radians.
- `max_state_age_ms`: positive integer policy receive-time freshness bound.

For compatibility, `orientation_mode` also accepts:

- `keep` with `rotation: null`.
- `quaternion` with a four-number `rotation` array in `qx,qy,qz,qw` order.
- `rpy` with a three-number `rotation` array. It is a local/TCP intrinsic delta
  `Rz(yaw) @ Ry(pitch) @ Rx(roll)`.

TCP translations are rotated by the current TCP orientation. Base translations are applied in the
configured base frame. Orientation deltas are post-multiplied in the current TCP/local frame.

Successful results contain `source_pose`, absolute `target_pose`, `frames`, `state_age_ms`, and
`source_snapshot`. `source_snapshot` contains a process-local version,
`received_monotonic_ns`, `age_ms`, and `time_basis: policy_receive_monotonic`. Joint positions are
never placed on the Tool Wire.

## Timing and errors

An expired Tool context fails with `FORGE_DEADLINE_EXCEEDED`. Missing, stale, or incomplete cached
state fails before FK. Stale/missing state uses retryable `MOTION_NO_FRESH_ROBOT_STATE`; incomplete
configured joints use retryable `MOTION_INCOMPLETE_STATE`. Contract, group, and frame failures use
`MOTION_INVALID_ARGUMENT`, `MOTION_INVALID_GROUP`, and `MOTION_INVALID_FRAME`.

`JointState` has no sensor observation timestamp in this contract. Freshness is therefore measured
from the monotonic time at which this policy receives/processes the state. Query resolution is not
atomic with a later Action: orchestration must provide any required stationary window and snapshot
version guard.

See the PAOS-owned
[`move-arm-by-ee` Skill](../../PhyAgentOS/PhyAgentOS/skills/forge-skill/move-arm-by-ee/)
for the current MuJoCo dataflow and Tool configuration.
