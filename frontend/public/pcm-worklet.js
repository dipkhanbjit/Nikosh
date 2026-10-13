/* global AudioWorkletProcessor, registerProcessor, sampleRate */
// AudioWorklet for interview audio capture: mono Float32 -> 16 kHz LINEAR16 (Int16) chunks of ~100 ms,
// posted to the main thread as ArrayBuffers. The AudioContext normally runs at 16 kHz (the browser
// resamples); if it could not, samples are averaged down (works for non-integer ratios like 44.1 kHz).

const TARGET_RATE = 16000;
const CHUNK_SAMPLES = TARGET_RATE / 10; // 100 ms

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET_RATE; // input samples per output sample (1 = no resampling)
    this.chunk = new Int16Array(CHUNK_SAMPLES);
    this.length = 0;
    this.sum = 0; // fallback averaging state
    this.count = 0;
    this.pos = 0;
  }

  push(value) {
    const s = Math.max(-1, Math.min(1, value));
    this.chunk[this.length++] = s < 0 ? s * 0x8000 : s * 0x7fff;
    if (this.length === CHUNK_SAMPLES) {
      this.port.postMessage(this.chunk.buffer, [this.chunk.buffer]);
      this.chunk = new Int16Array(CHUNK_SAMPLES);
      this.length = 0;
    }
  }

  process(inputs) {
    const samples = inputs[0]?.[0]; // first channel = mono (the mic track)
    if (!samples) return true;
    if (this.ratio === 1) {
      for (let i = 0; i < samples.length; i++) this.push(samples[i]);
      return true;
    }
    for (let i = 0; i < samples.length; i++) {
      this.sum += samples[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.push(this.sum / this.count);
        this.sum = 0;
        this.count = 0;
        this.pos -= this.ratio;
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
