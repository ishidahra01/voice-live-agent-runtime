import React from "react";

export interface PhaseTransitionEntry {
  from: string;
  to: string;
  vars: Record<string, unknown>;
  timestamp: number;
}

const PHASE_COLORS: Record<string, string> = {
  triage: "#3b82f6",
  identity: "#f59e0b",
  business: "#22c55e",
  escalation: "#ef4444",
};

interface Props {
  transitions: PhaseTransitionEntry[];
}

const PhaseTransitionLog: React.FC<Props> = ({ transitions }) => {
  if (transitions.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#9ca3af",
          fontSize: 13,
        }}
      >
        No phase transitions yet
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "8px 12px",
        fontSize: 13,
      }}
    >
      {transitions.map((t, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "4px 0",
            borderBottom: "1px solid #f3f4f6",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: "50%",
              backgroundColor: PHASE_COLORS[t.to] ?? "#6b7280",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              color: PHASE_COLORS[t.from] ?? "#6b7280",
              fontWeight: 500,
            }}
          >
            {t.from}
          </span>
          <span style={{ color: "#9ca3af" }}>→</span>
          <span
            style={{
              color: PHASE_COLORS[t.to] ?? "#6b7280",
              fontWeight: 600,
            }}
          >
            {t.to}
          </span>
          <span style={{ color: "#9ca3af", fontSize: 11, marginLeft: "auto" }}>
            {new Date(t.timestamp).toLocaleTimeString()}
          </span>
        </div>
      ))}
    </div>
  );
};

export default PhaseTransitionLog;
