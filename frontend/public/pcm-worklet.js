/**
 * AudioWorkletProcessor – captures mic audio, resamples to 24 kHz mono PCM16,
 * and posts Int16 ArrayBuffer chunks (~40 ms / 960 samples) to the main thread.
 */
class PcmWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    this._targetRate = 24000;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0]; // mono
    const ratio = sampleRate / this._targetRate;
    const resampledLength = Math.floor(channelData.length / ratio);

    // Simple linear-interpolation resample
    const resampled = new Float32Array(resampledLength);
    for (let i = 0; i < resampledLength; i++) {
      const srcIndex = i * ratio;
      const low = Math.floor(srcIndex);
      const high = Math.min(low + 1, channelData.length - 1);
      const frac = srcIndex - low;
      resampled[i] = channelData[low] * (1 - frac) + channelData[high] * frac;
    }

    // Accumulate
    const merged = new Float32Array(this._buffer.length + resampled.length);
    merged.set(this._buffer);
    merged.set(resampled, this._buffer.length);
    this._buffer = merged;

    // Flush in 960-sample chunks (~40 ms at 24 kHz)
    const chunkSize = 960;
    while (this._buffer.length >= chunkSize) {
      const chunk = this._buffer.slice(0, chunkSize);
      this._buffer = this._buffer.slice(chunkSize);

      // Float32 → Int16
      const pcm16 = new Int16Array(chunkSize);
      for (let i = 0; i < chunkSize; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }

    return true;
  }
}

registerProcessor("pcm-worklet-processor", PcmWorkletProcessor);
