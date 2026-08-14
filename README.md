# Relative Pose Policy Node

Standalone Dora policy node for the Forge Query endpoint `motion.relative_pose/resolve`. It consumes
`forge_msgs.JointState` locally, computes FK through `forge-kinematics`, and returns source and
absolute target poses over the Forge Tool Wire. It has no dependency on `forge-motion-server`.

The process uses the same Endpoint/domain-service layering as the Motion Action provider:

```text
Forge Query Tool Wire
        -> RelativePoseQueryEndpoint
        -> RelativePoseResolver
             -> JointStateCache
             -> ForwardKinematics
             -> frame transform
```

`RelativePoseQueryEndpoint` owns only Forge deadlines, strict wire argument parsing, `ToolResult`
serialization, and Tool/domain error translation. `RelativePoseResolver` is independent of
`forge_tool`; it owns state snapshots, FK, frame validation, and relative-to-absolute pose math.
Both objects are deliberately composed in one Dora policy-node process because resolution is a
short, one-shot query. A separate `RelativeQueryServer` process would add no execution or failure
boundary.

## Install and run

The project resolves Forge packages from the sibling `/home/mrgh/code/forge` checkout:

```bash
uv sync
uv run forge-relative-motion-policy --config relative_pose_policy.yaml
```

Configuration is intentionally limited to one kinematic group and exactly five fields:

```yaml
group_name: arm
joint_names: [joint1, joint2, joint3, joint4, joint5, joint6]
urdf_path: ../robots/piper.urdf
base_frame: base_link
tip_frame: link6
```

Relative `urdf_path` values resolve against the configuration file's directory. Unknown or missing
configuration fields are rejected.

## Dora ports

Inputs:

- `joint_state`: `forge_msgs.JointState`, cached only in-process using policy receive time.
- `tool_in`: Forge `ToolMessage` envelopes, including registry responses and Query requests.
- any regular input (for example `tick`) can drive lease renewal.

Output:

- `tool_out`: registration/unregistration, Query responses, and Tool errors.

The runner composes `RelativePoseQueryEndpoint`, `RelativePoseResolver`, Forge's public
`ToolEndpointHandler`, and `DoraToolEndpointBinding`; it does not duplicate Tool Wire dispatch. One
endpoint-level `EndpointLease` registers and renews the descriptor. See
[TOOL_CONTRACTS.md](TOOL_CONTRACTS.md) for the strict request and result contract.

The cross-repository fake, MuJoCo, and Agilex Piper integration graphs live in the
[move-arm-by-end-effector example](../../forge_runtime/examples/move_arm_by_ee_skill/README.md).
