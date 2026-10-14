"""Conservative cleanup of a model's near-silent trailing output."""
import io
import numpy as np
import soundfile as sf


def trim_trailing_silence(raw):
    """Trim only a >=1.5s quiet tail, preserving 350ms after last active frame.

    20ms RMS windows reject codec noise/clicks without altering pauses inside speech.
    The threshold is capped at -60 dBFS and lowered for quiet recordings.
    """
    audio, rate = sf.read(io.BytesIO(raw), dtype='float32', always_2d=True)
    original = len(audio) / rate
    window = max(1, round(rate * .02))
    # Use the loudest channel; stereo cancellation must never remove speech.
    energy = np.max(audio * audio, axis=1)
    starts = np.arange(0, len(audio), window)
    if not len(starts): return raw, 0.0
    counts = np.minimum(window, len(audio) - starts)
    rms = np.sqrt(np.add.reduceat(energy, starts) / counts)
    threshold = min(.001, float(rms.max()) * .01)
    if threshold <= 0: return raw, 0.0
    active = np.flatnonzero(rms > threshold)
    if not len(active): return raw, 0.0
    last = min(len(audio), int(starts[active[-1]]) + window)
    if (len(audio) - last) / rate < 1.5: return raw, 0.0
    end = min(len(audio), last + round(rate * .35))
    result = io.BytesIO()
    sf.write(result, audio[:end], rate, format='WAV', subtype='PCM_16')
    return result.getvalue(), round(original - end / rate, 3)
