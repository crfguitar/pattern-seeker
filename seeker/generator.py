"""Turn the genre vocabulary into a concrete beat: two bars of drums and 808
over a four-bar cycle of chords and pad."""

import random
import zlib

from .library import CHORDS, GENRES, PACES, PROGRESSIONS, ROLES, TURNAROUNDS

BARS = 2
STEPS = 16 * BARS
CYCLE = 2 * STEPS        # the harmony takes four bars to come round
VEL = {"X": 122, "x": 100, "o": 56}
SCALES = {"minor": (0, 2, 3, 5, 7, 8, 10), "major": (0, 2, 4, 5, 7, 9, 11)}
KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class Beat:
    def __init__(self, genre, lanes, tempo):
        self.genre = genre
        self.genre_name = GENRES[genre]["name"]
        self.lanes = lanes          # role -> list[int] velocity per step, 0 = rest
        self.tempo = tempo          # suggested BPM for this groove
        self.degrees = ["."] * STEPS  # 808 lane: scale degree per step
        self.relative = ["."] * STEPS  # 808 lane written against the chords
        self.chords = None            # {'rhythm', 'voicing', 'progs': {scale: prog}}
        sig = "|".join("%s:%s" % (r, "".join("1" if v else "0" for v in lanes[r]))
                       for r in ROLES)
        self.signature = sig
        self.tag = "%04X" % (zlib.crc32(sig.encode()) & 0xFFFF)
        self.name = "Seek %s %s" % (self.genre_name, self.tag)


def genres_for_tempo(bpm):
    """Genres idiomatic at this tempo; the nearest one if nothing fits."""
    fits = [k for k, g in GENRES.items() if g["bpm"][0] <= bpm <= g["bpm"][1]]
    if fits:
        return fits

    def gap(k):
        lo, hi = GENRES[k]["bpm"]
        return min(abs(bpm - lo), abs(bpm - hi))

    return [min(GENRES, key=gap)]


def _vary_kick(bar, rng):
    """Bar-two kick: add a pickup or drop a syncopation, never the downbeat."""
    bar = list(bar)
    hits = [i for i, c in enumerate(bar) if c != "." and i != 0]
    empty = [i for i in (3, 6, 7, 10, 11, 13, 14, 15) if bar[i] == "."]
    if hits and (not empty or rng.random() < 0.35):
        bar[rng.choice(hits)] = "."
    elif empty:
        bar[rng.choice(empty)] = "x"
    return "".join(bar)


def _vary_snare(bar, rng):
    bar = list(bar)
    spots = [i for i in (13, 15, 14) if bar[i] == "."]
    if spots:
        bar[rng.choice(spots)] = rng.choice("ox")
    return "".join(bar)


def _vary_hat(bar, rng):
    return bar[:12] + rng.choice(["xxxx", "x.xx", "xxx.", "xx.x", "x..."])


def _expand(pattern, role, straight, rng):
    if not pattern:
        return "." * STEPS
    if len(pattern) >= STEPS:
        return pattern[:STEPS]
    second = pattern
    roll = rng.random()
    if role == "kick" and not straight and roll < 0.55:
        second = _vary_kick(pattern, rng)
    elif role == "snare" and roll < 0.35:
        second = _vary_snare(pattern, rng)
    elif role == "hat" and roll < 0.4:
        second = _vary_hat(pattern, rng)
    return pattern + second


def _velocities(chars, role, rng):
    out = []
    for i, c in enumerate(chars):
        if c not in VEL:
            out.append(0)
            continue
        v = VEL[c]
        if role in ("hat", "perc") and c == "x":
            # Downbeats lead, off-16ths tuck under: the difference between a
            # groove and a typewriter.
            v = (104, 70, 88, 70)[i % 4]
        v += rng.randint(-4, 4)
        out.append(max(1, min(127, v)))
    return out


def _bass(spec, kick, rng):
    """The 808 lane as (degrees, relative): one char per step, '.' = rest.

    `degrees` is the line on its own (used when there are no chords);
    `relative` is the same rhythm written against whatever chord is sounding.
    """
    lines = list(spec.get("lines") or [])
    contours = list(spec.get("contours") or [])
    if contours and (not lines or rng.random() < 0.6):
        contour, keep = rng.choice(contours), spec.get("follow", 1.0)
        # The 808 doubles the kick; downbeats always land, syncopations mostly do.
        hits = [c != "." and (i % 16 == 0 or rng.random() < keep) for i, c in enumerate(kick)]
        return ([contour[i // 4] if h else "." for i, h in enumerate(hits)],
                ["1" if h else "." for h in hits])
    line = rng.choice(lines) if lines else ""
    out = list((line * (STEPS // len(line)))[:STEPS]) if line else ["."] * STEPS
    return out, list(out)


def bass_pitches(degrees, key=0, scale="minor", base=60, prog=None):
    """MIDI note per step for a degree lane. `key` is semitones above C (0-11).

    `base` is the note at which the 808 sample plays untransposed (FL: C5 = 60),
    so this assumes a sample tuned to C. Keys are folded to within a tritone of
    it and 5-7 go below the root, keeping the line in the 808's usable range.

    With `prog` (chord root degree per beat) the degrees are read relative to
    the chord sounding at that step, moved along the scale so they stay in key.
    """
    steps = SCALES[scale]
    root = base + ((key + 6) % 12) - 6
    out = []
    for i, d in enumerate(degrees):
        if d == ".":
            out.append(base)
            continue
        p = int(prog[(i // 4) % len(prog)]) if prog else 1
        chord = steps[p - 1] - (12 if p >= 5 else 0)       # chord root vs key root
        if d == "8":
            move = 12
        else:
            n = int(d)
            idx = p - 1 + n - 1
            move = steps[idx % 7] + 12 * (idx // 7) - steps[p - 1]
            if n >= 5:
                move -= 12
        total = chord + move
        if total < -7:
            total += 12
        elif total > 12:
            total -= 12
        out.append(root + total)
    return out


VOICINGS = {"triad": (0, 2, 4), "seventh": (0, 2, 4, 6), "ninth": (0, 2, 6, 8)}


def chord_notes(rhythm, prog, key=0, scale="minor", voicing="triad", base=60):
    """Piano-roll notes for a chord lane: [(midi note, start step, length, velocity)].

    Every chord tone is folded into the same one-octave window around `base`,
    which gives close voicings that move smoothly from chord to chord.
    """
    steps, low = SCALES[scale], base - 5
    notes, start, current, vel = [], None, 0, 96

    def voiced(degree):
        tones = set()
        for t in VOICINGS[voicing]:
            pc = (key + steps[(degree - 1 + t) % 7]) % 12
            tones.add(low + (pc - low) % 12)
        return sorted(tones)

    def close(end):
        if start is not None and end > start:
            notes.extend((n, start, end - start, vel) for n in voiced(current))

    for i, c in enumerate(rhythm):
        degree = int(prog[(i // 4) % len(prog)])
        if c == "x" or (c == "-" and start is not None and i % 4 == 0 and degree != current):
            close(i)
            start, current, vel = i, degree, (96 if i % 4 == 0 else 84)
        elif c == ".":
            close(i)
            start = None
    close(len(rhythm))
    return notes


def progression(scale, pace, rng):
    """Sixteen characters: the root degree of the chord on each beat of four bars."""
    a, b, c, d = rng.choice(PROGRESSIONS[scale])
    if pace == "drone":
        a = "1"
    elif pace in ("slow", "slow3") and "1" not in (a, b, c)[:len(set(PACES[pace]))]:
        a, b, c = "1", a, b          # few chords: make sure home is one of them
    turn = rng.choice([t for t in TURNAROUNDS[scale] if t not in (a, d)][:3])
    chord = {"a": a, "b": b, "c": c, "d": d, "t": turn}
    return "".join(chord[x] for x in PACES[pace])


def pad_notes(prog, key=0, scale="minor", base=72, velocity=62):
    """Piano-roll notes for the synth pad: [(midi note, start step, length, velocity)].

    Ambience, not a lead: the three notes of whichever chord is sounding, held
    for as long as that chord lasts, an octave above the keys and played softly.
    A note two neighbouring chords share is tied straight through the change,
    so the pad moves as little as the harmony allows.
    """
    steps, low = SCALES[scale], base - 5
    held, notes = {}, []                 # held: note -> step it started at

    def chord(degree):
        return {low + (key + steps[(degree - 1 + t) % 7] - low) % 12 for t in (0, 2, 4)}

    for beat, degree in enumerate(prog):
        tones = chord(int(degree))
        for n in [n for n in held if n not in tones]:
            start = held.pop(n)
            notes.append((n, start, beat * 4 - start, velocity))
        for n in tones:
            held.setdefault(n, beat * 4)
    notes.extend((n, start, len(prog) * 4 - start, velocity) for n, start in held.items())
    return sorted(notes, key=lambda n: (n[1], n[0]))


def generate(genre, rng=None):
    rng = rng or random.Random()
    g = GENRES[genre]
    straight = bool(g.get("straight"))
    lanes, kick = {}, "." * STEPS
    for role in ROLES:
        chars = _expand(rng.choice(g.get(role) or [""]), role, straight, rng)
        if role == "kick":
            kick = chars
        lanes[role] = _velocities(chars, role, rng)
    degrees, relative = _bass(g.get("bass") or {}, kick, rng)
    lanes["bass"] = [0 if d == "." else (112 if i % 16 == 0 else 102) + rng.randint(-3, 3)
                     for i, d in enumerate(degrees)]
    lo, hi = g["bpm"]
    beat = Beat(genre, lanes, float(rng.randint(lo + (hi - lo) // 4, hi - (hi - lo) // 4)))
    beat.degrees, beat.relative = degrees, relative
    c = CHORDS[genre]
    rhythm, pace = rng.choice(c["rhythm"]), rng.choice(c["pace"])
    beat.chords = {"rhythm": (rhythm * (CYCLE // len(rhythm)))[:CYCLE], "voicing": c["voicing"],
                   "progs": {s: progression(s, pace, rng) for s in SCALES}}
    return beat


class Seeker:
    """Hands out beats without repeating the last few it gave."""

    def __init__(self, seed=None, memory=64):
        self.rng = random.Random(seed)
        self.recent = []
        self.recent_progs = []
        self.memory = memory

    def next(self, genre=None, tempo=None):
        """genre=None means pick one: fitting `tempo` if given, else any."""
        for _ in range(40):
            if genre:
                key = genre
            elif tempo:
                key = self.rng.choice(genres_for_tempo(tempo))
            else:
                key = self.rng.choice(list(GENRES))
            beat = generate(key, self.rng)
            progs = tuple(sorted(beat.chords["progs"].items()))
            # Fresh drums AND fresh harmony: never the chords of the last few beats.
            if beat.signature not in self.recent and progs not in self.recent_progs:
                break
        self.recent.append(beat.signature)
        self.recent_progs.append(progs)
        del self.recent[:-self.memory]
        del self.recent_progs[:-8]
        return beat
