# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
vulnerability reporting for this repository. Include affected versions,
reproduction steps, impact, and any suggested mitigation.

## Deployment boundary

The Relative Pose Policy Node is a command-line Dora Query node. It performs no
authentication and computes poses from local `JointState` feedback.

- Run policy nodes only on trusted hosts within an isolated robot network.
- Treat policy YAML configuration as safety-relevant input; validate robot
  frames and kinematics parameters before deployment to hardware.
- This node is a Query provider: it resolves poses without moving the robot.
  Action execution remains the responsibility of downstream motion nodes and
  controllers, whose safety controls must be validated independently.
- Do not expose policy processes or their configuration to untrusted networks.

Security fixes are supported on the latest released version.
