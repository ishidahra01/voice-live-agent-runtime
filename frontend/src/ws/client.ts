import type { IncomingMessage, OutgoingMessage } from "../types/events";

export type ConnectionState = "disconnected" | "connecting" | "connected";

export class WsClient {
  private ws: WebSocket | null = null;
  private url: string;

  state: ConnectionState = "disconnected";
  onMessage: ((msg: IncomingMessage) => void) | null = null;
  onStateChange: ((state: ConnectionState) => void) | null = null;

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    if (this.ws) this.disconnect();
    this.setState("connecting");

    const ws = new WebSocket(this.url);
    ws.onopen = () => this.setState("connected");
    ws.onclose = () => this.setState("disconnected");
    ws.onerror = () => this.setState("disconnected");
    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string) as IncomingMessage;
        this.onMessage?.(msg);
      } catch {
        console.warn("Failed to parse WS message", ev.data);
      }
    };
    this.ws = ws;
  }

  disconnect(): void {
    this.ws?.close();
    this.ws = null;
    this.setState("disconnected");
  }

  send(msg: OutgoingMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private setState(s: ConnectionState): void {
    this.state = s;
    this.onStateChange?.(s);
  }
}
