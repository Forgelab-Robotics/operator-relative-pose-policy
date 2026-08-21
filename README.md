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

Forge packages resolve from public package indexes (`forge-msgs==1.0.1`, `forge-kinematics==1.0.1`); the Forge Tool protocol is vendored under `src/forge_tool`:

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

The PAOS-owned MuJoCo integration graph lives in the `move-arm-by-ee` Skill of the
PhyAgentOS skill collection.


## Development

Use Python 3.12 and `uv`:

```bash
uv sync --frozen --all-groups
uv run pytest -q
```

The vendored `forge-tool` protocol under `src/forge_tool` is resolved
automatically; see `THIRD_PARTY_NOTICES.md` for its provenance. The optional
standalone executable can be built with `scripts/build_pyinstaller.sh`.

## License

[Apache License 2.0](LICENSE). Runtime dependencies are not distributed with
this source repository and retain their respective licenses; see
[NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Review the complete bundled artifact before publishing standalone executables.
