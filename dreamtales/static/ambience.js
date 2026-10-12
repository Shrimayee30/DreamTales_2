'use strict';
// Original procedural soundscapes. No recordings, remote requests, or model output URLs.
class DreamAmbience {
  constructor() { this.context = null; this.layers = []; this.buffers = new Map(); this.key = ''; this.level = .2; this.duck = false; }
  async unlock() {
    if (!this.context) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      this.context = new AudioContext();
      this.master = this.context.createGain(); this.master.gain.value = 0; this.master.connect(this.context.destination);
    }
    if (this.context.state === 'suspended') await this.context.resume();
  }
  buffer(kind) {
    if (this.buffers.has(kind)) return this.buffers.get(kind);
    const rate = 24000, seconds = kind === 'thunder' ? 24 : 12;
    const buffer = this.context.createBuffer(1, rate * seconds, rate), out = buffer.getChannelData(0);
    let brown = 0, smooth = 0;
    for (let i = 0; i < out.length; i++) {
      const t = i / rate, white = Math.random() * 2 - 1;
      brown = (brown + .025 * white) / 1.025;
      smooth += .05 * (white - smooth);
      const edge = Math.min(1, t / .12, (seconds - t) / .12);
      if (kind === 'rain') out[i] = (white * .12 + smooth * .7) * edge;
      if (kind === 'wind') out[i] = brown * 2.8 * (.4 + .25 * Math.sin(2 * Math.PI * t / 12)) * edge;
      if (kind === 'ocean') out[i] = smooth * 1.1 * (.45 + .35 * Math.sin(2 * Math.PI * t / 6)) * edge;
      if (kind === 'night') {
        const phrase = t % 2, chirp = t % .16;
        const envelope = phrase < .65 && chirp < .075 ? Math.sin(Math.PI * chirp / .075) ** 2 : 0;
        out[i] = Math.sin(2 * Math.PI * 3800 * t) * envelope * .04 * edge;
      }
      if (kind === 'thunder') {
        // Distant rumble only, no sharp strike; one low event per 24 seconds.
        const rumble = t > 4 && t < 11 ? Math.sin(Math.PI * (t - 4) / 7) ** 2 : 0;
        out[i] = brown * 1.7 * rumble;
      }
    }
    this.buffers.set(kind, buffer); return buffer;
  }
  setLevel(level, duck = this.duck) {
    this.level = Math.max(0, Math.min(.6, level)); this.duck = duck;
    if (this.master) this.master.gain.setTargetAtTime(this.level * (duck ? .55 : 1), this.context.currentTime, .6);
  }
  update(sounds, {enabled, muted, thunder, volume, duck}) {
    this.setLevel(muted || !enabled ? 0 : volume, duck);
    const allowed = ['rain','wind','night','ocean','thunder'];
    const selected = [...new Set(sounds)].filter(s => allowed.includes(s) && (s !== 'thunder' || thunder)).slice(0,3);
    const key = enabled && !muted ? selected.join(',') : '';
    if (!this.context || this.context.state !== 'running' || key === this.key) return;
    this.stop(1.5); this.key = key;
    if (!key) return;
    for (const kind of selected) {
      const source = this.context.createBufferSource(); source.buffer = this.buffer(kind); source.loop = true;
      const filter = this.context.createBiquadFilter(); filter.type = 'lowpass';
      filter.frequency.value = kind === 'thunder' ? 160 : kind === 'wind' ? 750 : 6000;
      const gain = this.context.createGain(); gain.gain.value = 0;
      source.connect(filter); filter.connect(gain); gain.connect(this.master);
      gain.gain.setTargetAtTime(1 / Math.sqrt(selected.length), this.context.currentTime, .8);
      source.start(); this.layers.push({source,filter,gain});
    }
  }
  stop(fade = .5) {
    if (!this.context) return;
    const now = this.context.currentTime;
    for (const layer of this.layers) {
      layer.gain.gain.cancelScheduledValues(now);
      layer.gain.gain.setTargetAtTime(0, now, Math.max(.02,fade / 3));
      layer.source.onended = () => { layer.source.disconnect(); layer.filter.disconnect(); layer.gain.disconnect(); };
      try { layer.source.stop(now + fade); } catch { /* Already stopped. */ }
    }
    this.layers = []; this.key = '';
  }
}
