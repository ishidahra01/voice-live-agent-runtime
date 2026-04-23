function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export class MicRecorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private workletNode: AudioWorkletNode | null = null;

  onAudioChunk: ((base64: string) => void) | null = null;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1 },
    });

    this.ctx = new AudioContext({ sampleRate: 48000 });
    await this.ctx.audioWorklet.addModule("/pcm-worklet.js");

    const source = this.ctx.createMediaStreamSource(this.stream);
    this.workletNode = new AudioWorkletNode(this.ctx, "pcm-worklet-processor");

    this.workletNode.port.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      this.onAudioChunk?.(arrayBufferToBase64(ev.data));
    };

    source.connect(this.workletNode);
    // AudioWorklet must be connected to keep the audio graph alive.
    // The worklet processor does not produce output, so no audible sound is emitted.
    this.workletNode.connect(this.ctx.destination);
  }

  async stop(): Promise<void> {
    this.workletNode?.disconnect();
    this.workletNode = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    await this.ctx?.close();
    this.ctx = null;
  }
}
