import { Type } from "@sinclair/typebox";
import { definePluginEntry, type OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

type Real2SimPluginConfig = {
  apiBaseUrl?: string;
};

function resolveApiBaseUrl(api: OpenClawPluginApi): string {
  const config = api.pluginConfig as Real2SimPluginConfig | undefined;
  const value = typeof config?.apiBaseUrl === "string" && config.apiBaseUrl.trim().length > 0
    ? config.apiBaseUrl.trim()
    : "http://127.0.0.1:8765";
  return value.replace(/\/$/, "");
}

async function requestJson<T>(input: string | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const text = await response.text();
  let body: unknown;
  try {
    body = text.length > 0 ? JSON.parse(text) : {};
  } catch {
    body = { raw: text };
  }
  if (!response.ok) {
    const message = typeof body === "object" && body && "error" in body
      ? String((body as { error?: unknown }).error)
      : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return body as T;
}

export default definePluginEntry({
  id: "real2sim",
  name: "Real2Sim Bridge",
  description: "OpenClaw tools for the local Real2Sim pose-to-robot bridge.",
  register(api) {
    api.registerTool(
      {
        name: "real2sim_state",
        description: "Read the current Real2Sim pose and robot state from the local bridge.",
        parameters: Type.Object({}),
        async execute(_toolCallId) {
          const baseUrl = resolveApiBaseUrl(api);
          const result = await requestJson<Record<string, unknown>>(`${baseUrl}/state`);
          return {
            content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
          };
        },
      },
      { optional: true },
    );

    api.registerTool(
      {
        name: "real2sim_command",
        description: "Send a command to the local Real2Sim bridge.",
        parameters: Type.Object(
          {
            left_elbow: Type.Optional(Type.Number()),
            right_elbow: Type.Optional(Type.Number()),
          },
          { additionalProperties: false },
        ),
        async execute(_toolCallId, params) {
          const baseUrl = resolveApiBaseUrl(api);
          const result = await requestJson<Record<string, unknown>>(`${baseUrl}/command`, {
            method: "POST",
            headers: {
              "content-type": "application/json",
            },
            body: JSON.stringify(params ?? {}),
          });
          return {
            content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
          };
        },
      },
      { optional: true },
    );
  },
});
