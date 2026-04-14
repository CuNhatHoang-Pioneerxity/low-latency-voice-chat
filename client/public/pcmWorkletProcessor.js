class PCMWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(0);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channel = input[0];
    const int16Data = new Int16Array(channel.length);

    for (let i = 0; i < channel.length; i++) {
      int16Data[i] = Math.max(-32768, Math.min(32767, channel[i] * 32767));
    }

    this.port.postMessage(int16Data.buffer, [int16Data.buffer]);

    return true;
  }
}

registerProcessor('pcm-worklet-processor', PCMWorkletProcessor);
