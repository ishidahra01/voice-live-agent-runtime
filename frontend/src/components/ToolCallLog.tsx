import React, { useState } from "react";
import type { ToolCallEvent } from "../types/events";

interface Props {
  calls: ToolCallEvent[];
}

const TOOL_COLORS: Record<string, string> = {
  search: "#3b82f6",
  lookup: "#8b5cf6",
  transfer: "#ef4444",
  default: "#6b7280",
};

const ToolCallCard: React.FC<{ call: ToolCallEvent }> = ({ call }) => {
  const [expanded, setExpanded] = useState(false);
  const color = TOOL_COLORS[call.name] ?? TOOL_COLORS.default;

  return (
    <div
      style={{
        borderLeft: `4px solid ${color}`,
        backgroundColor: "#f9fafb",
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 13,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <span style={{ fontWeight: 700 }}>{call.name}</span>
        <span style={{ color: "#9ca3af", fontSize: 12 }}>
          {call.duration_ms}ms {expanded ? "▲" : "▼"}
        </span>
      </div>
      {expanded && (
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 4 }}>
            <strong style={{ fontSize: 11, color: "#6b7280" }}>ARGS</strong>
            <pre
              style={{
                margin: 0,
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                background: "#e5e7eb",
                padding: 6,
                borderRadius: 4,
              }}
            >
              {JSON.stringify(call.args, null, 2)}
            </pre>
          </div>
          <div>
            <strong style={{ fontSize: 11, color: "#6b7280" }}>RESULT</strong>
            <pre
              style={{
                margin: 0,
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                background: "#e5e7eb",
                padding: 6,
                borderRadius: 4,
              }}
            >
              {JSON.stringify(call.result, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};

const ToolCallLog: React.FC<Props> = ({ calls }) => (
  <div
    style={{
      overflowY: "auto",
      padding: 12,
      display: "flex",
      flexDirection: "column",
      gap: 8,
    }}
  >
    {calls.length === 0 && (
      <p style={{ color: "#9ca3af", textAlign: "center", marginTop: 20, fontSize: 13 }}>
        No tool calls yet.
      </p>
    )}
    {calls.map((c, i) => (
      <ToolCallCard key={`${c.name}-${i}`} call={c} />
    ))}
  </div>
);

export default ToolCallLog;
