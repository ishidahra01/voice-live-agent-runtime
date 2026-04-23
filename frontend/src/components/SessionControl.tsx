import React from "react";
import type { ConnectionState } from "../ws/client";

interface Props {
  connectionState: ConnectionState;
  recording: boolean;
  tokens: number;
  sessionModel?: string | null;
  sessionVoice?: string | null;
  onStart: () => void;
  onStop: () => void;
}

const STATE_COLORS: Record<ConnectionState, string> = {
  connected: "#22c55e",
  connecting: "#f59e0b",
  disconnected: "#ef4444",
};

const SessionControl: React.FC<Props> = ({
  connectionState,
  recording,
  tokens,
  sessionModel,
  sessionVoice,
  onStart,
  onStop,
}) => {
  const isConnected = connectionState === "connected";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "8px 16px",
      }}
    >
      <button
        onClick={recording ? onStop : onStart}
        disabled={recording && !isConnected}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "6px 16px",
          borderRadius: 8,
          border: "none",
          background: recording ? "#ef4444" : "#3b82f6",
          color: "#fff",
          fontWeight: 700,
          fontSize: 14,
          cursor: "pointer",
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: recording ? "#fff" : "#fca5a5",
            animation: recording ? "pulse 1s infinite" : "none",
          }}
        />
        {recording ? "Stop" : "Start"}
      </button>

      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: STATE_COLORS[connectionState],
            display: "inline-block",
          }}
        />
        <span style={{ textTransform: "capitalize" }}>{connectionState}</span>
      </div>

      <div style={{ fontSize: 13, color: "#6b7280" }}>
        Tokens: <strong>{tokens.toLocaleString()}</strong>
      </div>

      {(sessionModel || sessionVoice) && (
        <div style={{ fontSize: 13, color: "#6b7280" }}>
          Runtime: <strong>{sessionModel ?? "-"}</strong>
          {" / "}
          <strong>{sessionVoice ?? "-"}</strong>
        </div>
      )}
    </div>
  );
};

export default SessionControl;
