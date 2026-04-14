class TTSPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferQueue = [];
    this.isPlaying = false;
    this.samplesRemaining = 0;

    this.port.onmessage = (event) => {
      if (event.data.type === 'clear') {
        this.bufferQueue = [];
        this.samplesRemaining = 0;
        this.isPlaying = false;
      } else {
        this.bufferQueue.push(new Int16Array(event.data));
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    const channel = output[0];

    if (this.bufferQueue.length === 0 && this.samplesRemaining === 0) {
      if (this.isPlaying) {
        this.isPlaying = false;
        this.port.postMessage({ type: 'ttsPlaybackStopped' });
      }
      return true;
    }

    if (!this.isPlaying && this.bufferQueue.length > 0) {
      this.isPlaying = true;
      this.port.postMessage({ type: 'ttsPlaybackStarted' });
    }

    let written = 0;
    while (written < channel.length && (this.bufferQueue.length > 0 || this.samplesRemaining > 0)) {
      if (this.samplesRemaining === 0 && this.bufferQueue.length > 0) {
        this.currentBuffer = this.bufferQueue.shift();
        this.bufferIndex = 0;
        this.samplesRemaining = this.currentBuffer.length;
      }

      if (this.samplesRemaining > 0) {
        const toCopy = Math.min(
          channel.length - written,
          this.samplesRemaining
        );

        for (let i = 0; i < toCopy; i++) {
          channel[written + i] = this.currentBuffer[this.bufferIndex + i] / 32768;
        }

        written += toCopy;
        this.bufferIndex += toCopy;
        this.samplesRemaining -= toCopy;
      }
    }

    for (let i = written; i < channel.length; i++) {
      channel[i] = 0;
    }

    return true;
  }
}

registerProcessor('tts-playback-processor', TTSPlaybackProcessor);
