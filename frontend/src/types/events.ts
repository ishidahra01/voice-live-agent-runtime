// Frontend → Backend
export type AudioMessage = { type: "audio"; data: string };
export type ControlMessage = { type: "control"; action: "start" | "stop" };
export type OutgoingMessage = AudioMessage | ControlMessage;

// Backend → Frontend
export type AudioEvent = { type: "audio"; data: string };
export type TranscriptEvent = {
  type: "transcript";
  role: "user" | "assistant";
  text: string;
  phase: string;
  item_id: string;
};
export type TranscriptDeltaEvent = {
  type: "transcript_delta";
  role: "assistant";
  delta: string;
  item_id: string;
};
export type PhaseChangedEvent = {
  type: "phase_changed";
  from: string;
  to: string;
  vars: Record<string, unknown>;
};
export type ToolCallEvent = {
  type: "tool_call";
  name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  duration_ms: number;
};
export type SpeechStartedEvent = { type: "speech_started" };
export type SpeechStoppedEvent = { type: "speech_stopped" };
export type SessionReadyEvent = { type: "session_ready" };
export type SessionEndEvent = { type: "session_end"; reason: string };
export type SummaryExecutedEvent = { type: "summary_executed"; tokens: number };
export type ErrorEvent = { type: "error"; message: string };

export type IncomingMessage =
  | AudioEvent
  | TranscriptEvent
  | TranscriptDeltaEvent
  | PhaseChangedEvent
  | ToolCallEvent
  | SpeechStartedEvent
  | SpeechStoppedEvent
  | SessionReadyEvent
  | SessionEndEvent
  | SummaryExecutedEvent
  | ErrorEvent;
