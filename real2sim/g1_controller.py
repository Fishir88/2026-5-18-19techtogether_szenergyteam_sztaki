"""
G1 Robot MuJoCo Controller
Maps MediaPipe pose joint angles to Unitree G1 robot joints in simulation.

Architecture:
  Human Pose (MediaPipe) → Joint Angles → G1 Controller → MuJoCo Simulation → Visual Feedback
"""

import mujoco
import mujoco.viewer
import numpy as np
import sys
import os
from pathlib import Path
from dataclasses import dataclass

print(f"[g1_controller] Python: {sys.executable}", flush=True)


@dataclass
class JointMapping:
    """Maps MediaPipe landmarks to G1 robot joint indices."""
    # Left arm
    left_shoulder_pitch: int = None  # LEFT_SHOULDER to elbow abduction
    left_shoulder_roll: int = None   # LEFT_SHOULDER to elbow forward
    left_elbow_pitch: int = None     # LEFT_ELBOW to wrist
    left_wrist_pitch: int = None     # LEFT_WRIST fine angle
    
    # Right arm (symmetric)
    right_shoulder_pitch: int = None
    right_shoulder_roll: int = None
    right_elbow_pitch: int = None
    right_wrist_pitch: int = None


class G1Humanoid:
    """MuJoCo controller for Unitree G1 humanoid robot."""

    LEFT_SHOULDER_YAW_NEUTRAL = -np.pi / 2
    RIGHT_SHOULDER_YAW_NEUTRAL = np.pi / 2
    # Calibration offsets: desired qpos for a T-pose (user-specified)
    LEFT_SHOULDER_PITCH_OFFSET = 0.0
    RIGHT_SHOULDER_PITCH_OFFSET = 0.0
    
    def __init__(self, model_path: str = None):
        """
        Initialize G1 robot simulation.
        
        Args:
            model_path: Path to G1 MJCF model. If None, use a simple humanoid placeholder.
        """
        print("[g1_controller] Initializing G1 Humanoid MuJoCo model...", flush=True)
        
        try:
            resolved_model_path = self._resolve_model_path(model_path)

            # Try to load a real G1 model if found
            if resolved_model_path:
                print(f"[g1_controller] Loading G1 model from: {resolved_model_path}", flush=True)
                self.model = mujoco.MjModel.from_xml_path(str(resolved_model_path))
            else:
                # Create a simple 2-arm humanoid placeholder
                print("[g1_controller] Creating simplified humanoid placeholder (waiting for G1 MJCF model)", flush=True)
                self.model = self._create_simple_humanoid()
        except Exception as e:
            print(f"[g1_controller] ERROR loading model: {e}", flush=True)
            print("[g1_controller] Creating simplified humanoid placeholder", flush=True)
            self.model = self._create_simple_humanoid()
        
        self.data = mujoco.MjData(self.model)
        self.viewer = None
        self.fixed_base = True
        self.base_qpos_adr = None
        self.base_qvel_adr = None
        self.base_qpos_ref = None
        self._initialize_base_lock()
        
        # Joint mapping: MediaPipe → G1 joints
        self.joint_map = self._initialize_joint_mapping()
        self.has_hip_joints = any(
            name in self.joint_map
            for name in ["left_hip_pitch_joint", "left_hip_pitch", "left_hip_joint", "right_hip_pitch_joint", "right_hip_pitch", "right_hip_joint"]
        )
        self._hip_warning_printed = False
        
        # Performance tracking
        self.step_count = 0
        self.fps_tracker = []
        
        print(f"[g1_controller] Model initialized: {self.model.nq} DOF", flush=True)
        print(f"[g1_controller] Available joints: {self._list_joints()}", flush=True)

    def _resolve_model_path(self, explicit_model_path: str = None) -> Path | None:
        """Resolve the best available real G1 model path."""
        candidate_paths: list[Path] = []

        if explicit_model_path:
            candidate_paths.append(Path(explicit_model_path))

        env_model_path = os.environ.get("G1_MODEL_PATH")
        if env_model_path:
            candidate_paths.append(Path(env_model_path))

        local_dir = Path(__file__).resolve().parent
        candidate_paths.extend(
            [
                local_dir / "models" / "Unitree_g1.xml",
                local_dir / "models" / "Unitree_g1_converted.xml",
                Path.cwd() / "Unitree_g1.xml",
                Path.cwd() / "Unitree_g1_converted.xml",
            ]
        )

        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            downloads_dir = Path(user_profile) / "Downloads" / "unitree_g1_upper_body"
            candidate_paths.extend(
                [
                    downloads_dir / "Unitree_g1.xml",
                    downloads_dir / "Unitree_g1_converted.xml",
                ]
            )

        for candidate in candidate_paths:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def _iter_joint_names(self) -> list[str]:
        names: list[str] = []
        for joint_id in range(self.model.njnt):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
            if name:
                names.append(name)
        return names

    def _initialize_base_lock(self):
        """Capture the floating base pose so torso position/orientation stays fixed."""
        try:
            for joint_id in range(self.model.njnt):
                if int(self.model.jnt_type[joint_id]) == int(mujoco.mjtJoint.mjJNT_FREE):
                    self.base_qpos_adr = int(self.model.jnt_qposadr[joint_id])
                    self.base_qvel_adr = int(self.model.jnt_dofadr[joint_id])
                    self.base_qpos_ref = self.data.qpos[self.base_qpos_adr:self.base_qpos_adr + 7].copy()
                    print(
                        f"[g1_controller] Fixed base enabled at qpos[{self.base_qpos_adr}] / qvel[{self.base_qvel_adr}]",
                        flush=True,
                    )
                    return
        except Exception as e:
            print(f"[g1_controller] Base lock init warning: {e}", flush=True)

    def _enforce_fixed_base(self):
        if not self.fixed_base:
            return
        if self.base_qpos_adr is None or self.base_qvel_adr is None or self.base_qpos_ref is None:
            return
        self.data.qpos[self.base_qpos_adr:self.base_qpos_adr + 7] = self.base_qpos_ref
        self.data.qvel[self.base_qvel_adr:self.base_qvel_adr + 6] = 0.0
        mujoco.mj_forward(self.model, self.data)
    
    def _create_simple_humanoid(self) -> mujoco.MjModel:
        """Create a simple 2-arm humanoid placeholder for testing."""
        xml = """
        <mujoco model="humanoid_g1_placeholder">
                    <compiler angle="radian" inertiafromgeom="true"/>
                    <option timestep="0.005"/>
                    <default>
                        <joint damping="1" armature="0.1" limited="true"/>
                        <geom type="capsule" rgba="0.8 0.6 0.4 1"/>
                    </default>
          
          <worldbody>
                        <geom name="ground" type="plane" size="10 10 0.1" rgba="0.2 0.3 0.4 1"/>

                        <body name="torso" pos="0 0 1.2">
                            <freejoint name="root"/>
                            <geom type="box" size="0.2 0.15 0.3" rgba="0.7 0.5 0.3 1"/>
              
                            <body name="left_upper_arm" pos="0.22 0.15 0.18">
                                <joint name="left_shoulder" type="hinge" axis="0 1 0" range="-1.57 1.57"/>
                                <geom fromto="0 0 0 0 0 -0.28" size="0.04"/>

                                <body name="left_lower_arm" pos="0 0 -0.28">
                                    <joint name="left_elbow" type="hinge" axis="1 0 0" range="0 2.0"/>
                                    <geom fromto="0 0 0 0 0 -0.24" size="0.035" rgba="0.9 0.7 0.5 1"/>

                                    <body name="left_hand" pos="0 0 -0.24">
                                        <joint name="left_wrist" type="hinge" axis="0 1 0" range="-1.0 1.0"/>
                                        <geom type="sphere" size="0.045" rgba="0.95 0.8 0.65 1"/>
                                    </body>
                                </body>
              </body>
              
                            <body name="right_upper_arm" pos="-0.22 0.15 0.18">
                                <joint name="right_shoulder" type="hinge" axis="0 1 0" range="-1.57 1.57"/>
                                <geom fromto="0 0 0 0 0 -0.28" size="0.04"/>

                                <body name="right_lower_arm" pos="0 0 -0.28">
                                    <joint name="right_elbow" type="hinge" axis="1 0 0" range="0 2.0"/>
                                    <geom fromto="0 0 0 0 0 -0.24" size="0.035" rgba="0.9 0.7 0.5 1"/>

                                    <body name="right_hand" pos="0 0 -0.24">
                                        <joint name="right_wrist" type="hinge" axis="0 1 0" range="-1.0 1.0"/>
                                        <geom type="sphere" size="0.045" rgba="0.95 0.8 0.65 1"/>
                                    </body>
                                </body>
              </body>
            </body>
          </worldbody>
        </mujoco>
        """
        print("[g1_controller] Using placeholder humanoid XML model", flush=True)
        return mujoco.MjModel.from_xml_string(xml)
    
    def _initialize_joint_mapping(self) -> dict:
        """Map joint names to indices for easy access."""
        mapping = {}
        try:
            for name in self._iter_joint_names():
                joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
                qpos_adr = int(self.model.jnt_qposadr[joint_id])
                mapping[name] = qpos_adr
                print(f"[g1_controller]   Joint {name}: qpos[{qpos_adr}]", flush=True)
        except Exception as e:
            print(f"[g1_controller] Warning: Could not map joints: {e}", flush=True)
        return mapping
    
    def _list_joints(self) -> str:
        """Get human-readable joint list."""
        try:
            joints = self._iter_joint_names()
            return f"{len(joints)} joints: {', '.join(joints[:5])}..." if len(joints) > 5 else f"{len(joints)} joints"
        except Exception:
            return f"{self.model.nq} DOF"

    def _set_joint_if_present(self, candidate_names: list[str], angle_rad: float):
        for name in candidate_names:
            index = self.joint_map.get(name)
            if index is not None:
                self.data.qpos[index] = angle_rad
                return
    
    def set_arm_pose(self, 
                     left_shoulder: np.ndarray = None,
                     left_shoulder_pitch: float = None,
                     left_shoulder_roll: float = None,
                     left_shoulder_yaw: float = None,
                     left_elbow: float = None,
                     right_shoulder: np.ndarray = None,
                     right_shoulder_pitch: float = None,
                     right_shoulder_roll: float = None,
                     right_shoulder_yaw: float = None,
                     right_elbow: float = None,
                     left_hip_pitch: float = None,
                     right_hip_pitch: float = None):
        """
        Set robot arm pose from MediaPipe landmarks.
        
        Args:
            left_shoulder: 3D position [x, y, z] or None to skip
            left_elbow: Elbow bend angle (0-180 degrees)
            right_shoulder: 3D position [x, y, z]
            right_elbow: Elbow bend angle
        """
        try:
            # Normalize angles to radians and valid ranges
            if left_shoulder_pitch is not None:
                # Keep pitch identity-mapped so measured 0 -> simulated 0 and measured 1 -> simulated 1
                val = float(np.clip(left_shoulder_pitch + self.LEFT_SHOULDER_PITCH_OFFSET, -2.2, 2.2))
                self._set_joint_if_present(["left_shoulder_pitch_joint", "left_shoulder_pitch"], val)

            if left_shoulder_roll is not None:
                self._set_joint_if_present(
                    ["left_shoulder_roll_joint", "left_shoulder_roll"],
                    float(np.clip(left_shoulder_roll, -2.0, 2.0)),
                )

            self._set_joint_if_present(
                ["left_shoulder_yaw_joint", "left_shoulder_yaw"],
                float(np.clip(0.0, -2.2, 2.2)),
            )

            if right_shoulder_pitch is not None:
                # Keep pitch identity-mapped so measured 0 -> simulated 0 and measured -1 -> simulated -1
                val = float(np.clip(right_shoulder_pitch + self.RIGHT_SHOULDER_PITCH_OFFSET, -2.2, 2.2))
                self._set_joint_if_present(["right_shoulder_pitch_joint", "right_shoulder_pitch"], val)

            if right_shoulder_roll is not None:
                self._set_joint_if_present(
                    ["right_shoulder_roll_joint", "right_shoulder_roll"],
                    float(np.clip(right_shoulder_roll, -2.0, 2.0)),
                )

            self._set_joint_if_present(
                ["right_shoulder_yaw_joint", "right_shoulder_yaw"],
                float(np.clip(0.0, -2.2, 2.2)),
            )

            if left_elbow is not None:
                # Convert MediaPipe angle (0-180) to joint command (-pi/2 to pi/2)
                angle_rad = np.clip((left_elbow - 90) * np.pi / 180, -np.pi/2, np.pi/2)
                self._set_joint_if_present(["left_elbow_joint", "left_elbow"], angle_rad)
            
            if right_elbow is not None:
                angle_rad = np.clip((right_elbow - 90) * np.pi / 180, -np.pi/2, np.pi/2)
                self._set_joint_if_present(["right_elbow_joint", "right_elbow"], angle_rad)

            # Lock wrists at zero rotation to avoid unwanted wrist motion
            self._set_joint_if_present(["left_wrist_roll_joint", "left_wrist"], 0.0)
            self._set_joint_if_present(["right_wrist_roll_joint", "right_wrist"], 0.0)

            # Optional hip control: applies only if loaded model has matching joints.
            if (left_hip_pitch is not None or right_hip_pitch is not None) and not self.has_hip_joints and not self._hip_warning_printed:
                print(
                    "[g1_controller] Hip commands received, but current Unitree_g1.xml has no hip joints. Hip motion cannot be actuated with this model.",
                    flush=True,
                )
                self._hip_warning_printed = True

            if left_hip_pitch is not None:
                self._set_joint_if_present(
                    ["left_hip_pitch_joint", "left_hip_pitch", "left_hip_joint"],
                    float(np.clip(left_hip_pitch, -1.2, 1.2)),
                )

            if right_hip_pitch is not None:
                self._set_joint_if_present(
                    ["right_hip_pitch_joint", "right_hip_pitch", "right_hip_joint"],
                    float(np.clip(right_hip_pitch, -1.2, 1.2)),
                )
            
            # Apply gravity compensation
            mujoco.mj_inverse(self.model, self.data)
            
        except Exception as e:
            print(f"[g1_controller] Error setting arm pose: {e}", flush=True)
    
    def step(self, dt: float = 0.005):
        """Advance simulation by dt seconds."""
        try:
            self._enforce_fixed_base()
            mujoco.mj_step(self.model, self.data)
            self._enforce_fixed_base()
            self.step_count += 1
            
            if self.step_count % 200 == 0:  # Log every 1 second (200 steps * 0.005s)
                print(f"[g1_controller] Simulation step {self.step_count}, time={self.data.time:.2f}s", flush=True)
        except Exception as e:
            print(f"[g1_controller] Error during simulation step: {e}", flush=True)
    
    def render(self, show_viewer: bool = True):
        """Render the simulation."""
        try:
            if show_viewer and self.viewer is None:
                print("[g1_controller] Opening MuJoCo viewer...", flush=True)
                self.viewer = mujoco.viewer.launch_passive(self.model, self.data)
            
            if self.viewer is not None:
                self.viewer.sync()
        except Exception as e:
            print(f"[g1_controller] Error rendering: {e}", flush=True)
    
    def close(self):
        """Clean up resources."""
        if self.viewer is not None:
            self.viewer.close()
        print("[g1_controller] Simulation closed.", flush=True)
    
    def get_state(self) -> dict:
        """Get current simulation state."""
        return {
            "time": float(self.data.time),
            "qpos": self.data.qpos.copy(),
            "qvel": self.data.qvel.copy(),
            "step": self.step_count,
        }


def main():
    """Test the G1 controller with dummy pose data."""
    print("[g1_controller] ====== G1 MuJoCo Controller Test ======", flush=True)
    
    try:
        import argparse
        parser = argparse.ArgumentParser(description="G1 controller test runner")
        parser.add_argument("--model", type=str, default=None, help="Path to Unitree G1 MJCF model")
        parser.add_argument("--keep-open", action="store_true", help="Keep MuJoCo viewer open until interrupted")
        parser.add_argument("--steps", type=int, default=300, help="Number of test simulation steps (ignored with --keep-open)")
        args = parser.parse_args()

        g1 = G1Humanoid(model_path=args.model)
        print("[g1_controller] Simulation initialized successfully", flush=True)

        if args.keep_open:
            # Set T-pose using configured offsets and lock wrists/yaw as configured
            g1.set_arm_pose(
                left_shoulder_pitch=g1.LEFT_SHOULDER_PITCH_OFFSET,
                left_shoulder_roll=0.0,
                right_shoulder_pitch=g1.RIGHT_SHOULDER_PITCH_OFFSET,
                right_shoulder_roll=0.0,
            )
            # Open viewer and run until interrupted
            g1.render(show_viewer=True)
            print("[g1_controller] Viewer open. Press Ctrl+C to exit.", flush=True)
            try:
                while True:
                    g1.step()
                    if g1.viewer is not None:
                        g1.viewer.sync()
            except KeyboardInterrupt:
                print("[g1_controller] Interrupted by user, closing.", flush=True)
                g1.close()
                return 0

        # Default short test run (finite steps)
        print(f"[g1_controller] Running {args.steps} simulation steps...", flush=True)
        for i in range(args.steps):
            # Oscillate left elbow: 90° ± 30° (visual test)
            elbow_angle = 90 + 30 * np.sin(2 * np.pi * i / 100)
            g1.set_arm_pose(left_elbow=elbow_angle, right_elbow=elbow_angle)
            g1.step()

            if i % 100 == 0:
                state = g1.get_state()
                print(f"[g1_controller] Step {i}: time={state['time']:.3f}s", flush=True)

            # Render every 5 steps
            if i % 5 == 0:
                g1.render()

        print("[g1_controller] Test completed successfully", flush=True)
        g1.close()
        return 0
    
    except Exception as e:
        print(f"[g1_controller] FATAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    print(f"[g1_controller] Exiting with code {exit_code}", flush=True)
    sys.exit(exit_code)
