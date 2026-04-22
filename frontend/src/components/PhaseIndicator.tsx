import React from "react";

const PHASE_COLORS: Record<string, string> = {
  triage: "#3b82f6",
  identity: "#f59e0b",
  business: "#22c55e",
  escalation: "#ef4444",
};

interface Props {
  phase: string;
}

const PhaseIndicator: React.FC<Props> = ({ phase }) => {
  const color = PHASE_COLORS[phase] ?? "#6b7280";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: 12,
        backgroundColor: color,
        color: "#fff",
        fontSize: 13,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {phase}
    </span>
  );
};

export default PhaseIndicator;
