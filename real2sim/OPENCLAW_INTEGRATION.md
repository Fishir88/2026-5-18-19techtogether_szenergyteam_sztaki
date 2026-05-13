# OpenClaw Real2Sim Integration Guide

This document describes how to integrate the Real2Sim system with OpenClaw for AI agent control of the G1 robot simulation.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Human Movement (Camera)                 │
└──────────────────────┬──────────────────────────────────┘
                       │ (video feed)
                       ↓
┌─────────────────────────────────────────────────────────┐
│         MediaPipe Pose Detection (pose_test.py)          │
│  Extracts: 33 landmarks per frame → joint angles        │
└──────────────────────┬──────────────────────────────────┘
                       │ (joint angles: elbow, shoulder, etc)
                       ↓
┌─────────────────────────────────────────────────────────┐
│        Real2Sim Bridge (real2sim.py)                     │
│  Maps MediaPipe angles → G1 robot commands             │
└──────────────────────┬──────────────────────────────────┘
                       │ (robot joint commands)
                       ↓
┌─────────────────────────────────────────────────────────┐
│      G1 MuJoCo Simulation (g1_controller.py)            │
│  Simulates: Unitree G1 humanoid with dual arms         │
└──────────────────────┬──────────────────────────────────┘
                       │ (simulation state: positions, velocities)
                       ↓
┌─────────────────────────────────────────────────────────┐
│          OpenClaw Agent Interface                        │
│  Observes: simulated robot state                        │
│  Learns: human arm movement patterns                    │
│  Controls: robot via Real2Sim commands                  │
└─────────────────────────────────────────────────────────┘
```

## Running the System

### 1. Start Real2Sim with MuJoCo simulation

```bash
cd "d:\Szabi\SZEnergy\TechTogether OpenClaw\real2sim"
.\venv\Scripts\activate
python real2sim.py
```

**Expected output:**
```
[real2sim] Python: .../venv/Scripts/python.exe
[real2sim] ====== Real2Sim System Starting ======
[real2sim] Initializing Real2Sim system...
[real2sim] Initializing G1 MuJoCo simulation...
[real2sim] G1 simulation ready
[real2sim] Initializing MediaPipe pose detection...
[real2sim] MediaPipe initialized
[real2sim] Starting webcam capture...
[real2sim] Camera opened. Press Q to exit.
```

Then:
- Move your arms in front of the camera
- Watch the G1 robot simulation follow your movements in real-time
- Joint angles displayed on screen (e.g., "left_elbow: 132.5°")
- Press Q to exit

### 2. OpenClaw Agent Integration

OpenClaw agents can interact with the Real2Sim system via:

#### A. **Direct Python Integration** (Local Agent)

```python
# In your OpenClaw agent code or skill
import json
import subprocess
from pathlib import Path

class Real2SimSkill:
    """OpenClaw skill to control Real2Sim robot simulation."""
    
    def __init__(self):
        self.real2sim_path = Path("path/to/real2sim/real2sim.py")
    
    def get_robot_state(self) -> dict:
        """Query current robot state from Real2Sim system."""
        # In a real implementation, this would communicate via:
        # - HTTP API (recommended)
        # - WebSocket (real-time)
        # - Unix socket (local IPC)
        # - Shared memory (high-performance)
        pass
    
    def send_command(self, left_elbow: float, right_elbow: float):
        """Send robot commands to Real2Sim system."""
        # Commands would update the G1 robot pose
        pass
```

#### B. **REST API Interface** (Recommended)

Add this to `real2sim.py` for OpenClaw to query:

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/real2sim/state", methods=["GET"])
def get_state():
    """Get current Real2Sim system state."""
    return jsonify({
        "frame_id": system.frame_count,
        "detected_angles": system.current_angles,
        "robot_active": system.use_mujoco,
        "timestamp": time.time(),
    })

@app.route("/real2sim/command", methods=["POST"])
def send_command():
    """Send robot command to Real2Sim system."""
    data = request.json
    if system.robot:
        system.robot.set_arm_pose(
            left_elbow=data.get("left_elbow"),
            right_elbow=data.get("right_elbow"),
        )
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
```

#### C. **OpenClaw Tool/Skill**

Create a skill file at `~/.openclaw/workspace/skills/real2sim/SKILL.md`:

```markdown
# Real2Sim Skill

## Description
Controls the Real2Sim system: real-time human pose → G1 robot simulation

## Tools
- `real2sim_get_state()` - Get current robot pose and detected angles
- `real2sim_set_command(left_elbow, right_elbow)` - Command robot movements
- `real2sim_start()` - Start webcam capture
- `real2sim_stop()` - Stop simulation

## Usage Example
User: "Make the robot follow human arm movements"
Agent: 
1. Calls `real2sim_start()`
2. Polls `real2sim_get_state()` every 50ms
3. Observes detected_angles (human pose)
4. Applies learned policy to generate robot commands
5. Calls `real2sim_set_command()` with computed joint angles
```

## Key Integration Points

### 1. **State Observation**
OpenClaw observes:
- `frame_id`: Current frame number
- `detected_angles`: Detected joint angles (left_elbow, right_elbow, etc.)
- `robot_state`: G1 simulation state (position, velocity)
- `confidence`: Pose detection confidence (0-1)

### 2. **Command Interface**
OpenClaw sends:
- `set_arm_pose(left_elbow, right_elbow, left_shoulder, right_shoulder)`
- Values in degrees (0-180 for elbow/wrist, ±90 for shoulder)

### 3. **Feedback Loop**
- Real2Sim → human arm angles: ~30 FPS
- OpenClaw processes → G1 simulation: ~10-20 Hz (typically)
- Agent learns: human movement patterns ↔ robot control commands

## Testing Without Webcam

Run G1 controller test directly:

```bash
python g1_controller.py
```

This oscillates the robot arms without requiring a camera or MediaPipe.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| MuJoCo viewer not opening | Check: `mujoco` installed, X11 forwarding if SSH |
| Camera not detected | Try indices 0-3: `cv2.VideoCapture(0)` to `cv2.VideoCapture(3)` |
| Poses detected but robot not moving | Check `use_mujoco=True` in `Real2SimSystem` |
| Memory issues | Reduce pose detection confidence thresholds |

## Next Steps for Agent Development

1. **Imitation Learning**: Train agent to mimic human arm movements
2. **Reinforcement Learning**: Reward matching human pose or reaching targets
3. **Transfer Learning**: Deploy learned policy to real Unitree G1 hardware
4. **Multi-task Learning**: Learn multiple movement types (reaching, waving, etc.)

## File Structure

```
real2sim/
├── pose_test.py           # MediaPipe pose detection (baseline)
├── g1_controller.py       # MuJoCo G1 robot controller
├── real2sim.py            # Real2Sim bridge (main)
├── models/
│   └── pose_landmarker_heavy.task  # MediaPipe model (auto-download)
├── requirements.txt       # Dependencies (mediapipe, mujoco, etc.)
└── README.md             # This file
```

## References

- **MediaPipe**: https://mediapipe.dev/
- **MuJoCo**: https://mujoco.org/
- **OpenClaw**: https://github.com/openclaw/openclaw
- **Unitree G1**: https://www.unitree.com/
