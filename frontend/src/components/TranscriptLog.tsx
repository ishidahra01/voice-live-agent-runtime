import React, { useEffect, useRef } from "react";
import PhaseIndicator from "./PhaseIndicator";

export interface TranscriptEntry {
  id: string;
  role: "user" | "assistant";
  text: string;
  phase?: string;
}

interface Props {
  entries: TranscriptEntry[];
}

const TranscriptLog: React.FC<Props> = ({ entries }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {entries.length === 0 && (
        <p style={{ color: "#9ca3af", textAlign: "center", marginTop: 40 }}>
          No messages yet. Start a session to begin.
        </p>
      )}
      {entries.map((e) => (
        <div
          key={e.id + e.text.length}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: e.role === "user" ? "flex-end" : "flex-start",
          }}
        >
          <div
            style={{
              maxWidth: "80%",
              padding: "8px 12px",
              borderRadius: 8,
              backgroundColor: e.role === "user" ? "#e0e7ff" : "#f3f4f6",
              fontSize: 14,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 4,
              }}
            >
              <span
                style={{
                  fontWeight: 700,
                  fontSize: 12,
                  textTransform: "uppercase",
                  color: e.role === "user" ? "#4338ca" : "#374151",
                }}
              >
                {e.role}
              </span>
              {e.phase && <PhaseIndicator phase={e.phase} />}
            </div>
            {e.text}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
};

export default TranscriptLog;
