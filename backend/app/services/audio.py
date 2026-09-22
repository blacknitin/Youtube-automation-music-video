"""Audio analysis + local demo-song synthesis (numpy only, no heavy deps).

Analysis extracts: duration (ffprobe), BPM + beat offset (spectral-flux
autocorrelation), an energy curve, waveform peaks for the UI, and coarse
sections. WhisperX (if enabled) refines per-line timings later.
"""
import array
import math
import struct
import subprocess
import wave

import numpy as np

from ..config import SETTINGS


def probe_duration(path) -> float:
    try:
        out = subprocess.run(
            [SETTINGS.ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def load_pcm(path: str, sr: int = 22050) -> np.ndarray:
    """Decode any audio file to mono float32 via ffmpeg pipe."""
    cmd = [SETTINGS.ffmpeg_bin, "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
           "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, timeout=180).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def analyze(path) -> dict:
    try:
        import librosa  # optional — real DSP beat tracking (github.com/librosa/librosa)
        return _analyze_librosa(path)
    except Exception:
        return _analyze_numpy(path)


def _analyze_librosa(path) -> dict:
    """librosa-powered analysis: tempo via beat tracking, onset-novelty sections."""
    import librosa
    sr = 22050
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    duration = len(y) / sr

    # --- tempo + beat grid (dynamic programming beat tracker) ---
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    bpm = float(np.atleast_1d(tempo)[0])
    while bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    hop = 512
    beat_offset = float(beat_frames[0] * hop / sr) if len(beat_frames) else 0.0
    beat_period = 60.0 / bpm
    if beat_offset > beat_period:
        beat_offset %= beat_period

    # --- energy curve (RMS, 0.5s windows) ---
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=int(sr * 0.5))[0]
    energy = rms / (rms.max() + 1e-9)

    # --- sections via onset novelty + energy ---
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    sections = _librosa_sections(onset, energy, sr, duration)

    # --- waveform peaks for UI (~800 points) ---
    n_p = 800
    k = max(1, len(y) // n_p)
    n = min(n_p, len(y) // k)
    peaks = np.array([float(np.abs(y[i * k:(i + 1) * k]).max()) for i in range(n)])
    peaks = peaks / (peaks.max() + 1e-9)

    return {
        "duration": round(float(duration), 2),
        "bpm": round(float(bpm), 1),
        "beat_offset": round(float(beat_offset), 2),
        "sections": sections,
        "energy": [round(float(e), 3) for e in energy],
        "peaks": [round(float(p), 3) for p in peaks],
    }


def _librosa_sections(onset, energy, sr, duration) -> list:
    """Cut sections at smoothed onset-novelty peaks (min 12s apart, max 8),
    then label by energy level (verse below / chorus above median)."""
    hop = 512
    fps = sr / hop
    nov = onset / (onset.max() + 1e-9)
    sm = np.convolve(nov, np.ones(9) / 9, mode="same")
    thr = float(sm.mean() + 0.5 * sm.std())
    min_gap = int(12 * fps)
    cuts: list = []
    for i in range(1, len(sm) - 1):
        if len(cuts) >= 7:
            break
        if sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1] and sm[i] > thr:
            if not cuts or i - cuts[-1] >= min_gap:
                cuts.append(i)
    if cuts and cuts[0] < int(8 * fps):
        cuts = cuts[1:]  # drop a cut inside the first 8s (song start transient)
    edges = [0.0] + [c / fps for c in cuts] + [float(duration)]
    segments = [[edges[i], edges[i + 1]] for i in range(len(edges) - 1)]
    # split over-long segments (>45s) at the quietest transition point
    for _ in range(6):
        if len(segments) >= 16 or all(e - s <= 45.0 for s, e in segments):
            break
        out = []
        for s, e in segments:
            if e - s > 45.0:
                i0, i1 = int(s * fps), int(e * fps)
                lo, hi = i0 + (i1 - i0) // 5, i1 - (i1 - i0) // 5
                cut = (lo + int(np.argmin(sm[lo:hi]))) / fps if hi > lo else (s + e) / 2
                out += [[s, cut], [cut, e]]
            else:
                out.append([s, e])
        segments = out
    sections = []
    for s, e in segments:
        if e - s < 6:
            continue
        seg = energy[int(s / 0.5):int(e / 0.5) + 1]
        level = float(seg.mean()) if len(seg) else 0.5
        sections.append({"start": round(s, 2), "end": round(e, 2), "_lvl": level})
    if not sections:
        return [{"name": "Full", "type": "verse", "start": 0.0, "end": round(float(duration), 2)}]
    med = float(np.median([x["_lvl"] for x in sections]))
    n = len(sections)
    vi = ci = 0
    for i, sec in enumerate(sections):
        lvl = sec.pop("_lvl")
        if i == 0 and (sec["end"] - sec["start"] <= 15 or lvl < med):
            sec["name"], sec["type"] = "Intro", "intro"
        elif i == n - 1 and i > 0 and (lvl < med or sec["end"] - sec["start"] <= 15):
            sec["name"], sec["type"] = "Outro", "outro"
        elif lvl >= med:
            ci += 1
            sec["name"], sec["type"] = f"Chorus {ci}", "chorus"
        else:
            vi += 1
            sec["name"], sec["type"] = f"Verse {vi}", "verse"
    return sections


def _analyze_numpy(path) -> dict:
    sr = 22050
    y = load_pcm(str(path), sr)
    duration = len(y) / sr
    if duration < 1:
        duration = probe_duration(path)

    # --- spectral flux onset envelope ---
    hop, nfft = 512, 1024
    n_frames = max(1, (len(y) - nfft) // hop)
    win = np.hanning(nfft).astype(np.float32)
    frames = np.lib.stride_tricks.as_strided(
        y, shape=(n_frames, nfft), strides=(y.strides[0] * hop, y.strides[0])).copy()
    mags = np.abs(np.fft.rfft(frames * win, axis=1))
    flux = np.maximum(0.0, np.diff(mags, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    flux -= flux.mean()
    std = flux.std() or 1.0
    flux /= std

    # --- BPM via autocorrelation of onset envelope ---
    fps = sr / hop
    lag_min, lag_max = int(fps * 60 / 190), int(fps * 60 / 60)
    if len(flux) > lag_max + 2:
        f0 = flux - flux.mean()
        ac = np.correlate(f0, f0, mode="full")[len(f0) - 1:]
        seg = ac[lag_min:lag_max]
        lag = int(np.argmax(seg)) + lag_min
        # parabolic refine
        if 0 < lag - lag_min < len(seg) - 1:
            y0, y1, y2 = seg[lag - lag_min - 1], seg[lag - lag_min], seg[lag - lag_min + 1]
            denom = (y0 - 2 * y1 + y2)
            shift = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
            lag = lag + shift
        bpm = 60.0 * fps / lag
        while bpm < 70:
            bpm *= 2
        while bpm > 180:
            bpm /= 2
        # beat phase: fold flux at beat period
        period = 60.0 / bpm * fps
        idxs = np.arange(len(flux))
        phases = (idxs % period) / period
        best_offset, best_score = 0.0, -1
        for k in range(12):
            off = k / 12.0
            score = flux[((phases - off) % 1.0) < 0.08].mean()
            if score > best_score:
                best_score, best_offset = score, off
        beat_offset = float(best_offset * period / fps)
    else:
        bpm, beat_offset = 100.0, 0.0

    # --- energy curve (RMS, 0.5s windows) ---
    win_s = 0.5
    w = int(sr * win_s)
    n_e = max(1, len(y) // w)
    energy = np.array([float(np.sqrt(np.mean(y[i * w:(i + 1) * w] ** 2))) for i in range(n_e)])
    if energy.max() > 0:
        energy = energy / energy.max()

    # --- coarse sections: intro / verses / choruses / outro via energy ---
    sections = _coarse_sections(energy, win_s, duration)

    # --- waveform peaks for UI (~800 points) ---
    n_p = 800
    if len(y) > 0:
        idx = np.linspace(0, len(y) - 1, n_p).astype(int)
        peaks = np.abs(y[idx])
        k = max(1, len(y) // n_p)
        peaks = np.array([float(np.abs(y[i * k:(i + 1) * k]).max()) for i in range(n_p)])
        if peaks.max() > 0:
            peaks = peaks / peaks.max()
    else:
        peaks = np.zeros(n_p)

    return {
        "duration": round(float(duration), 2),
        "bpm": round(float(bpm), 1),
        "beat_offset": round(float(beat_offset), 2),
        "sections": sections,
        "energy": [round(float(e), 3) for e in energy],
        "peaks": [round(float(p), 3) for p in peaks],
    }


def _coarse_sections(energy, win_s, duration) -> list:
    """Label coarse sections by energy: intro, alternating verse/chorus, outro."""
    if duration <= 0:
        return []
    n = len(energy)
    if n < 8:
        return [{"name": "Full", "type": "verse", "start": 0.0, "end": duration}]
    thr = float(np.percentile(energy, 35))
    active = energy > thr
    first = int(np.argmax(active))
    last = n - 1 - int(np.argmax(active[::-1]))
    intro_end = min(duration * 0.25, (first + 1) * win_s)
    outro_start = max(intro_end + 1, last * win_s)
    mid = outro_start - intro_end
    n_mid = max(2, min(6, int(mid // 25)))
    sections = []
    if intro_end > 2.5:
        sections.append({"name": "Intro", "type": "intro", "start": 0.0, "end": round(intro_end, 2)})
    for i in range(n_mid):
        s = intro_end + mid * i / n_mid
        e = intro_end + mid * (i + 1) / n_mid
        sections.append({"name": f"Verse {i + 1}" if i % 2 == 0 else f"Chorus {i // 2 + 1}",
                         "type": "verse" if i % 2 == 0 else "chorus",
                         "start": round(s, 2), "end": round(e, 2)})
    if duration - outro_start > 2.5:
        sections.append({"name": "Outro", "type": "outro", "start": round(outro_start, 2), "end": round(duration, 2)})
    if not sections:
        sections = [{"name": "Full", "type": "verse", "start": 0.0, "end": round(duration, 2)}]
    return sections


# ---------------------------------------------------------------------------
# Demo song synthesis — a 100 BPM loop (Am F C G) so users can try the whole
# pipeline before importing a real Suno track.
# ---------------------------------------------------------------------------
def synthesize_demo_song(out_path, bpm=100.0, bars=16, sr=44100):
    beat = 60.0 / bpm
    total = bars * 4 * beat
    t = np.arange(int(total * sr)) / sr
    mix = np.zeros_like(t)

    chords = [  # Am F C G (root midi notes + chord tones)
        [57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62],
    ]
    def note_hz(m): return 440.0 * 2 ** ((m - 69) / 12)

    for bar in range(bars):
        ch = chords[bar % 4]
        t0 = bar * 4 * beat
        i0 = int(t0 * sr)
        # pad (soft detuned saw-ish)
        for m in ch:
            f = note_hz(m - 12)
            seg_t = t[i0:i0 + int(4 * beat * sr)]
            w = 0.10 * (np.sin(2 * np.pi * f * seg_t) + 0.35 * np.sin(2 * np.pi * f * 1.005 * seg_t))
            env = np.minimum(1, np.arange(len(seg_t)) / (0.3 * sr)) * np.minimum(1, np.arange(len(seg_t))[::-1] / (0.5 * sr))
            mix[i0:i0 + len(w)] += w * env
        # arpeggio pluck (8ths)
        for k in range(8):
            m = ch[k % 3] + (12 if k % 4 == 3 else 0)
            ts = t0 + k * beat / 2
            j0 = int(ts * sr)
            n = int(0.28 * sr)
            seg_t = t[j0:j0 + n]
            if len(seg_t) == 0:
                continue
            w = 0.22 * np.sin(2 * np.pi * note_hz(m) * seg_t) * np.exp(-seg_t * 9)
            mix[j0:j0 + len(w)] += w[:len(mix) - j0] if j0 + n > len(mix) else w
        # bass
        f = note_hz(ch[0] - 24)
        for k in range(4):
            ts = t0 + k * beat
            j0 = int(ts * sr)
            n = int(beat * 0.9 * sr)
            seg_t = t[j0:j0 + n]
            if len(seg_t) == 0:
                continue
            w = 0.30 * np.sin(2 * np.pi * f * seg_t) * np.exp(-seg_t * 1.5)
            mix[j0:j0 + len(w)] += w[:len(mix) - j0] if j0 + n > len(mix) else w
        # kick on beats, hats on 8ths
        for k in range(4):
            j0 = int((t0 + k * beat) * sr)
            n = int(0.12 * sr)
            seg_t = t[j0:j0 + n]
            w = 0.55 * np.sin(2 * np.pi * (110 - 500 * seg_t) * seg_t) * np.exp(-seg_t * 30)
            mix[j0:j0 + min(len(w), len(mix) - j0)] += w[:min(len(w), len(mix) - j0)]
        for k in range(8):
            j0 = int((t0 + k * beat / 2 + beat / 2) * sr)
            n = int(0.03 * sr)
            rng = np.random.default_rng(j0)
            w = 0.12 * rng.standard_normal(n) * np.exp(-np.arange(n) / sr * 90)
            mix[j0:j0 + min(len(w), len(mix) - j0)] += w[:min(len(w), len(mix) - j0)]

    # fades
    fade = int(1.5 * sr)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix = 0.85 * mix / (np.abs(mix).max() + 1e-9)

    data = (mix * 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wfile:
        wfile.setnchannels(1)
        wfile.setsampwidth(2)
        wfile.setframerate(sr)
        wfile.writeframes(data.tobytes())
    return str(out_path)
