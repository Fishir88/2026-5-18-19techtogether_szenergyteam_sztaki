---
name: real2sim
summary: Control and observe the Real2Sim pose-to-robot bridge from OpenClaw.
---

# Real2Sim Skill

Use this skill when you need OpenClaw to work with the local Real2Sim demo.

## Goal

Human webcam pose should drive the MuJoCo robot simulation, while OpenClaw can inspect state and issue local control commands through the JSON API.

## Start the system

Run the bridge from the project root:

```powershell
python real2sim.py --api-port 8765
```

Use pose-only mode when you only want webcam tracking:

```powershell
python pose_test.py
```

Use the MuJoCo controller alone when you want to check the robot simulation without the camera:

```powershell
python g1_controller.py
```

## OpenClaw interaction pattern

OpenClaw should use the local API on `http://127.0.0.1:8765`.

### Read state

```powershell
curl http://127.0.0.1:8765/state
```

Expected fields:
- `frame_id`
- `angles`
- `last_command`
- `robot_active`
- `timestamp`

### Send a command

```powershell
curl -Method POST http://127.0.0.1:8765/command -ContentType application/json -Body '{"left_elbow": 120, "right_elbow": 115}'
```

Supported command fields:
- `left_elbow`
- `right_elbow`
- `left_wrist`
- `right_wrist`

## Workflow for OpenClaw

1. Start `python real2sim.py --api-port 8765`.
2. Read `/state` to observe the current pose.
3. Use the pose angles to infer motion or generate a robot policy.
4. Optionally POST a command to `/command` for robot-side overrides.
5. Keep the simulation running while the agent reasons over the state stream.

## Notes

- The API is local-only on `127.0.0.1`.
- The camera loop still drives the robot directly from the detected human pose.
- The command endpoint is available for OpenClaw tooling, testing, and future policy control.
- If MuJoCo is not needed, start with `python real2sim.py --no-mujoco --api-port 8765`.
