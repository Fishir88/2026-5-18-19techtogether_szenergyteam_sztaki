import mujoco
try:
    model = mujoco.MjModel.from_xml_path("Unitree_g1_converted.xml")
    joints = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(model.njnt)]
    actuators = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(model.nu)]
    print(f"Joints: {joints}")
    print(f"Actuators: {actuators}")
    print(f"Left Hip Pitch: {'left_hip_pitch_joint' in joints or 'left_hip_pitch' in joints}")
    print(f"Right Hip Pitch: {'right_hip_pitch_joint' in joints or 'right_hip_pitch' in joints}")
    print(f"Left Wrist Roll Actuator: {'left_wrist_roll' in actuators or 'left_wrist_roll_joint' in actuators}")
    print(f"Right Wrist Roll Actuator: {'right_wrist_roll' in actuators or 'right_wrist_roll_joint' in actuators}")
except Exception as e:
    print(f"Error: {e}")
