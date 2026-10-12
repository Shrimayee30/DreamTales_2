"""Isolated Kokoro ONNX synthesis. No model downloads occur at runtime."""
import json
import contextlib
import argparse
import os
import re
import sys

# Bound CPU work on both the development machine and the Jetson.
os.environ.setdefault('OMP_NUM_THREADS', '2')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--voices', required=True)
    parser.add_argument('--output')
    parser.add_argument('--server', action='store_true')
    parser.add_argument('--voice', default='af_heart')
    parser.add_argument('--speed', type=float, default=.88)
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro
    import onnxruntime as ort
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(args.model, sess_options=options, providers=['CPUExecutionProvider'])
    kokoro = Kokoro.from_session(session, args.voices)
    def synthesize(text, output):
        if not 40 <= len(text) <= 2200 or not .75 <= args.speed <= 1.1:
            raise ValueError('Invalid narration input')
        # Keep sentences together for prosody; insert a small pause between paragraphs.
        chunks = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        pieces = []
        rate = 24000
        for chunk in chunks:
            samples, rate = kokoro.create(chunk, voice=args.voice, speed=args.speed, lang='en-us')
            pieces.extend([samples, np.zeros(int(rate * .4), dtype=np.float32)])
        samples = np.concatenate(pieces)
        peak = float(np.max(np.abs(samples)))
        if peak > .85:
            samples *= .85 / peak
        fade = min(int(rate * .04), len(samples) // 2)
        samples[:fade] *= np.linspace(0, 1, fade)
        samples[-fade:] *= np.linspace(1, 0, fade)
        sf.write(output, samples, rate, subtype='PCM_16')

    if args.server:
        print('{"ready":true}', flush=True)
        for line in sys.stdin:
            try:
                request = json.loads(line)
                with contextlib.redirect_stdout(sys.stderr):
                    synthesize(request['text'], request['output'])
                print('{"ok":true}', flush=True)
            except Exception:
                print('{"ok":false}', flush=True)
    else:
        synthesize(sys.stdin.read(10000).strip(), args.output)

if __name__ == '__main__':
    main()
