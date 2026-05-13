# OpenClaw Real2Sim Plugin

This package exposes OpenClaw tools for the local Real2Sim bridge.

## Tools

- `real2sim_state` - read the current pose and robot state
- `real2sim_command` - send a robot command to the local bridge

## Local config

The plugin reads the bridge URL from `plugins.entries.real2sim.config.apiBaseUrl`.
Default:

```json
"http://127.0.0.1:8765"
```

## Install in OpenClaw

Point OpenClaw at this plugin directory as a local plugin, then enable the `real2sim` plugin id.

Example shape:

```json
{
  "plugins": {
    "entries": {
      "real2sim": {
        "path": "d:/Szabi/SZEnergy/TechTogether OpenClaw/real2sim/openclaw-real2sim-plugin",
        "config": {
          "apiBaseUrl": "http://127.0.0.1:8765"
        }
      }
    }
  }
}
```

## Run order

1. Start `python real2sim.py --api-port 8765`
2. Start OpenClaw with this plugin enabled
3. Call `real2sim_state` or `real2sim_command`
