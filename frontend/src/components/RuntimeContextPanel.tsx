import React from "react";
import type { ContextSnapshotEvent, SessionConfigEvent } from "../types/events";

interface Props {
  sessionConfig: SessionConfigEvent | null;
  contextSnapshot: ContextSnapshotEvent | null;
}

function formatValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }

  return JSON.stringify(value, null, 2);
}

const cardStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  padding: 12,
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const RuntimeContextPanel: React.FC<Props> = ({ sessionConfig, contextSnapshot }) => {
  const varsEntries = Object.entries(contextSnapshot?.vars ?? {});
  const summaryEntries = Object.entries(contextSnapshot?.summaries ?? {});

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        background: "#f8fafc",
      }}
    >
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 14 }}>Live Runtime</strong>
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {sessionConfig?.phase ?? "triage"}
          </span>
        </div>
        {sessionConfig ? (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <div>
                <div style={{ color: "#6b7280" }}>Mode</div>
                <div style={{ fontWeight: 600 }}>{sessionConfig.mode}</div>
              </div>
              <div>
                <div style={{ color: "#6b7280" }}>Model</div>
                <div style={{ fontWeight: 600 }}>{sessionConfig.model}</div>
              </div>
              <div>
                <div style={{ color: "#6b7280" }}>Voice</div>
                <div style={{ fontWeight: 600 }}>{sessionConfig.voice}</div>
              </div>
            </div>
            <div>
              <div style={{ color: "#6b7280", fontSize: 12, marginBottom: 6 }}>Tools</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {sessionConfig.tools.map((tool) => (
                  <span
                    key={tool}
                    style={{
                      padding: "4px 8px",
                      borderRadius: 999,
                      fontSize: 11,
                      background: "#e0f2fe",
                      color: "#0f172a",
                    }}
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div style={{ fontSize: 13, color: "#9ca3af" }}>No session profile yet.</div>
        )}
      </div>

      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 14 }}>Context Vars</strong>
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {contextSnapshot?.cumulative_tokens?.toLocaleString() ?? 0} tokens
          </span>
        </div>
        {varsEntries.length > 0 ? (
          varsEntries.map(([key, value]) => (
            <div key={key} style={{ borderTop: "1px solid #f1f5f9", paddingTop: 8 }}>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{key}</div>
              <div style={{ fontSize: 13, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {formatValue(value)}
              </div>
            </div>
          ))
        ) : (
          <div style={{ fontSize: 13, color: "#9ca3af" }}>No live vars yet.</div>
        )}
      </div>

      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: 14 }}>Summaries</strong>
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            Last summary at {contextSnapshot?.last_summary_token_count?.toLocaleString() ?? 0}
          </span>
        </div>
        {summaryEntries.length > 0 ? (
          summaryEntries.map(([key, value]) => (
            <div key={key} style={{ borderTop: "1px solid #f1f5f9", paddingTop: 8 }}>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{key}</div>
              <div style={{ fontSize: 13, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {formatValue(value)}
              </div>
            </div>
          ))
        ) : (
          <div style={{ fontSize: 13, color: "#9ca3af" }}>No summaries yet.</div>
        )}
      </div>
    </div>
  );
};

export default RuntimeContextPanel;