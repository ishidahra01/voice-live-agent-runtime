import { useCallback, useEffect, useRef, useState } from "react";
import { WsClient } from "./ws/client";
import type { ConnectionState } from "./ws/client";
import type { IncomingMessage, ToolCallEvent } from "./types/events";
import { MicRecorder } from "./audio/recorder";
import { AudioPlayer } from "./audio/player";
import SessionControl from "./components/SessionControl";
import PhaseIndicator from "./components/PhaseIndicator";
import TranscriptLog from "./components/TranscriptLog";
import type { TranscriptEntry } from "./components/TranscriptLog";
import ToolCallLog from "./components/ToolCallLog";
import PhaseTransitionLog from "./components/PhaseTransitionLog";
import type { PhaseTransitionEntry } from "./components/PhaseTransitionLog";

function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/voice`;
}

function App() {
  const wsRef = useRef<WsClient | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);
  const playerRef = useRef<AudioPlayer | null>(null);

  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected");
  const [recording, setRecording] = useState(false);
  const [phase, setPhase] = useState("triage");
  const [tokens, setTokens] = useState(0);
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCallEvent[]>([]);
  const [phaseTransitions, setPhaseTransitions] = useState<
    PhaseTransitionEntry[]
  >([]);

  const handleMessage = useCallback((msg: IncomingMessage) => {
    switch (msg.type) {
      case "audio":
        playerRef.current?.play(msg.data);
        break;

      case "transcript":
        setTranscripts((prev) => {
          const idx = prev.findIndex((e) => e.id === msg.item_id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              text: msg.text,
              phase: msg.phase,
            };
            return updated;
          }
          return [
            ...prev,
            {
              id: msg.item_id,
              role: msg.role,
              text: msg.text,
              phase: msg.phase,
            },
          ];
        });
        break;

      case "transcript_delta":
        setTranscripts((prev) => {
          const idx = prev.findIndex((e) => e.id === msg.item_id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              text: updated[idx].text + msg.delta,
            };
            return updated;
          }
          return [...prev, { id: msg.item_id, role: msg.role, text: msg.delta }];
        });
        break;

      case "phase_changed":
        setPhase(msg.to);
        setPhaseTransitions((prev) => [
          ...prev,
          {
            from: msg.from,
            to: msg.to,
            vars: msg.vars,
            timestamp: Date.now(),
          },
        ]);
        break;

      case "tool_call":
        setToolCalls((prev) => [...prev, msg]);
        break;

      case "speech_started":
        playerRef.current?.flush();
        break;

      case "summary_executed":
        setTokens((prev) => prev + msg.tokens);
        break;

      case "session_end":
        console.log("Session ended:", msg.reason);
        break;

      case "error":
        console.error("Server error:", msg.message);
        break;

      default:
        break;
    }
  }, []);

  const handleStart = useCallback(async () => {
    const ws = new WsClient(wsUrl());
    ws.onMessage = handleMessage;
    ws.onStateChange = setConnectionState;
    ws.connect();
    wsRef.current = ws;

    const player = new AudioPlayer();
    playerRef.current = player;

    const recorder = new MicRecorder();
    recorder.onAudioChunk = (base64) => {
      ws.send({ type: "audio", data: base64 });
    };
    await recorder.start();
    recorderRef.current = recorder;

    ws.send({ type: "control", action: "start" });
    setRecording(true);
  }, [handleMessage]);

  const handleStop = useCallback(async () => {
    wsRef.current?.send({ type: "control", action: "stop" });
    await recorderRef.current?.stop();
    recorderRef.current = null;
    playerRef.current?.flush();
    playerRef.current = null;
    wsRef.current?.disconnect();
    wsRef.current = null;
    setRecording(false);
  }, []);

  useEffect(() => {
    return () => {
      recorderRef.current?.stop();
      wsRef.current?.disconnect();
    };
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {/* Header */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid #e5e7eb",
          background: "#fff",
          padding: "0 8px",
          flexShrink: 0,
        }}
      >
        <SessionControl
          connectionState={connectionState}
          recording={recording}
          tokens={tokens}
          onStart={handleStart}
          onStop={handleStop}
        />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            paddingRight: 16,
          }}
        >
          <span style={{ fontSize: 13, color: "#6b7280" }}>Phase:</span>
          <PhaseIndicator phase={phase} />
        </div>
      </header>

      {/* Body */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div
          style={{
            flex: 2,
            display: "flex",
            flexDirection: "column",
            borderRight: "1px solid #e5e7eb",
          }}
        >
          <h3
            style={{
              margin: 0,
              padding: "8px 12px",
              borderBottom: "1px solid #e5e7eb",
              fontSize: 14,
            }}
          >
            Transcript
          </h3>
          <TranscriptLog entries={transcripts} />
        </div>

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minWidth: 260,
            borderRight: "1px solid #e5e7eb",
          }}
        >
          <h3
            style={{
              margin: 0,
              padding: "8px 12px",
              borderBottom: "1px solid #e5e7eb",
              fontSize: 14,
            }}
          >
            Tool Calls
          </h3>
          <ToolCallLog calls={toolCalls} />
        </div>

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minWidth: 220,
          }}
        >
          <h3
            style={{
              margin: 0,
              padding: "8px 12px",
              borderBottom: "1px solid #e5e7eb",
              fontSize: 14,
            }}
          >
            Phase Transitions
          </h3>
          <PhaseTransitionLog transitions={phaseTransitions} />
        </div>
      </div>
    </div>
  );
}

export default App;
