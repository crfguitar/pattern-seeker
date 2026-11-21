"""Sinfonietta in D - a hand-written Classical-era piece in three movements for
chamber orchestra (flute, oboe, clarinet, bassoon, horns, timpani, strings).

    python examples/sinfonietta.py            # compose and print the plan
    python examples/sinfonietta.py build      # add the eleven channels to FL
    python examples/sinfonietta.py write      # write the patterns, lay out the song

What makes it a piece rather than a loop, and what a generator would need:

  I   Allegro, D major, sonata form: theme 1 (tutti), a transition that leaves
      the key, theme 2 in the dominant (strings, then winds), closing; a
      development that takes theme 1 through minor keys onto a dominant pedal;
      the recapitulation with theme 2 at home; coda.
  II  Andante, G major (the subdominant), A-B-A + coda: a singing theme, an oboe
      episode in E minor, the theme again with flute.
  III Rondo, D major, A-B-A-C-A + coda: a dance tune, a wind episode in the
      dominant, a storm in D minor.

The themes and the chords under them are written out by hand below; the
`textures` turn a melody and its chords into the parts of the orchestra.
FL has one tempo, so everything is written at 132 BPM: the Andante in doubled
note values (it sounds at 66), the Rondo as 2/4 bars two to an FL bar.
"""

import collections
import json
import os
import random
import re
import sys

TEMPO = 132
PCS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DYN = {"pp": 36, "p": 50, "mp": 62, "mf": 76, "f": 92, "ff": 106}
QUAL = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10),
        "dim": (0, 3, 6), "maj7": (0, 4, 7, 11)}

# channel: (sound, colour, volume, pan, lowest note, highest note) - middle C is 60
ORCHESTRA = {
    "Flute": ("FLEX/Essential Winds/Flutes Sustain", "#8FD3F4", 0.50, -0.10, 60, 93),
    "Oboe": ("FLEX/Essential Winds/Oboes Sustain", "#F4C98F", 0.46, 0.10, 58, 88),
    "Clarinet": ("FLEX/Essential Winds/Clarinets Sustain", "#B79FE8", 0.46, -0.18, 50, 86),
    "Bassoon": ("FLEX/Essential Winds/Bassoon Sustain", "#A9785A", 0.48, 0.18, 34, 67),
    "Horns": ("FLEX/Essential Winds/Horns Sustain", "#E0B040", 0.42, -0.28, 41, 72),
    "Timpani": ("FLEX/General Midi Library/Timpani", "#C05050", 0.55, 0.0, 36, 50),
    "Violins 1": ("FLEX/Essential Strings/Violins Sustain", "#5FA8E8", 0.62, -0.38, 55, 96),
    "Violins 2": ("FLEX/Essential Strings/Violins Sustain", "#4C8BD0", 0.55, -0.14, 55, 88),
    "Violas": ("FLEX/Essential Strings/Violas Sustain", "#5FB889", 0.55, 0.14, 48, 79),
    "Cellos": ("FLEX/Essential Strings/Cellos Sustain", "#3F9E6E", 0.60, 0.32, 36, 69),
    "Basses": ("FLEX/Essential Strings/Bass Sustain", "#2F7F58", 0.55, 0.42, 28, 55),
}
V1, V2, VA, VC, CB = "Violins 1", "Violins 2", "Violas", "Cellos", "Basses"
FL, OB, CL, BN, HN, TI = "Flute", "Oboe", "Clarinet", "Bassoon", "Horns", "Timpani"


def pc(name):
    return (PCS[name[0]] + name.count("#") - name.count("b")) % 12


def midi(name):
    """'F#5' -> 78 (C4 = 60, middle C)."""
    m = re.match(r"^([A-G][#b]*)(-?\d)$", name)
    return 12 * (int(m.group(2)) + 1) + PCS[m.group(1)[0]] + m.group(1).count("#") \
        - m.group(1).count("b")


class Chord:
    def __init__(self, text, tr=0):
        m = re.match(r"^([A-G][#b]?)(maj7|m7|dim|m|7)?(?:/([A-G][#b]?))?$", text)
        if not m:
            raise ValueError("chord %r" % text)
        self.root = (pc(m.group(1)) + tr) % 12
        self.pcs = [(self.root + i) % 12 for i in QUAL[m.group(2) or ""]]
        # which tones matter most: the third, then the seventh, the root, the fifth
        order = (1, 3, 0, 2) if len(self.pcs) == 4 else (1, 0, 2)
        self.order = [self.pcs[i] for i in order]
        self.fifth = self.pcs[2]
        self.bass = (pc(m.group(3)) + tr) % 12 if m.group(3) else self.root


def melody(text, tr=0, bar=4.0):
    """'D5:2 F#5:1 r:1 | ...' -> ([(pitch, start, length)], total beats). Bars are checked."""
    notes, t = [], 0.0
    for n, chunk in enumerate(text.split("|"), 1):
        start = t
        for tok in chunk.split():
            name, _, d = tok.partition(":")
            if name != "r":
                notes.append((midi(name) + tr, t, float(d)))
            t += float(d)
        if abs(t - start - bar) > 1e-6:
            raise ValueError("bar %d (%s) is %g beats" % (n, chunk.strip(), t - start))
    return notes, t


def chords(text, tr=0, bar=4.0):
    """'D | Em:3 A7:1' -> [(start, length, Chord)]."""
    out, t = [], 0.0
    for n, chunk in enumerate(text.split("|"), 1):
        start = t
        for tok in chunk.split():
            name, _, d = tok.partition(":")
            out.append((t, float(d or bar), Chord(name, tr)))
            t += float(d or bar)
        if abs(t - start - bar) > 1e-6:
            raise ValueError("chord bar %d (%s) is %g beats" % (n, chunk.strip(), t - start))
    return out, t


def place(pitch_class, center, lo, hi):
    """The note of that pitch class nearest `center`, inside the instrument."""
    best = None
    for p in range(lo, hi + 1):
        if p % 12 == pitch_class and (best is None or abs(p - center) < abs(best - center)):
            best = p
    return best


def fold(p, inst):
    lo, hi = ORCHESTRA[inst][4:6]
    while p > hi:
        p -= 12
    while p < lo:
        p += 12
    return p


class Seg:
    """One stretch of music in one texture: a melody, its chords, a dynamic."""

    def __init__(self, texture, dyn, mel, chd, tr=0):
        self.texture, self.tr = texture, tr
        self.soft, _, self.loud = dyn.replace(">", "<").partition("<")
        self.mel, beats = melody(mel, tr)
        self.tl, cbeats = chords(chd, tr)
        if abs(beats - cbeats) > 1e-6:
            raise ValueError("melody is %g beats, chords %g: %s" % (beats, cbeats, mel[:40]))
        self.beats = beats

    # ---- the pieces a texture is made of -----------------------------------
    def render(self, rng, legato):
        self.out, self.rng, self.legato = collections.defaultdict(list), rng, legato
        TEXTURES[self.texture](self)
        return self.out

    def level(self, t):
        a, b = DYN[self.soft], DYN[self.loud or self.soft]
        return a + (b - a) * t / self.beats

    def chord(self, t):
        now = self.tl[0][2]
        for start, _, ch in self.tl:
            if start <= t + 1e-9:
                now = ch
        return now

    def add(self, inst, p, t, d, off=0):
        v = self.level(t) + off + (5 if abs(t % 4) < 1e-6 else 0) + self.rng.randint(-3, 3)
        self.out[inst].append((int(p), t, d, max(1, min(127, int(round(v))))))

    def times(self, step, start=0.0):
        t = start
        while t < self.beats - 1e-9:
            yield t
            t += step

    def line(self, inst, shift=0, off=10):
        """The melody on `inst`, `shift` semitones away, louder toward its high notes."""
        mean = sum(p for p, _, _ in self.mel) / len(self.mel)
        for p, t, d in self.mel:
            long = d >= 1 or self.legato
            self.add(inst, fold(p + shift, inst), t, d * (0.96 if long else 0.8),
                     off + max(-6, min(6, (p - mean) * 0.4)))

    def tones(self, inst, picks, center, t):
        ch = self.chord(t)
        lo, hi = ORCHESTRA[inst][4:6]
        return sorted({place(ch.order[i % len(ch.order)], center, lo, hi) for i in picks})

    def pulse(self, inst, picks, center, step=0.5, length=0.4, off=-8, start=0.0):
        """Repeated chord tones: the inner strings' engine."""
        for t in self.times(step, start):
            for p in self.tones(inst, picks, center, t):
                self.add(inst, p, t, length, off)

    def alberti(self, inst, center, step=0.5, off=-8):
        """Broken chords: low, high, middle, high."""
        for t in self.times(step):
            tones = self.tones(inst, (0, 1, 2), center, t)
            k = int(round(t / step)) % 4
            self.add(inst, tones[(0, -1, len(tones) // 2, -1)[k]], t, step * 0.9, off)

    def sustain(self, inst, pick, center, off=-10):
        """One held note per chord; a note shared with the next chord is tied."""
        lo, hi = ORCHESTRA[inst][4:6]
        held = []
        for start, d, ch in self.tl:
            want = {"bass": ch.bass, "root": ch.root, "fifth": ch.fifth}.get(pick)
            if want is None:
                want = ch.order[pick % len(ch.order)]
            p = place(want, center, lo, hi)
            if held and held[-1][0] == p:
                held[-1][2] += d
            else:
                held.append([p, start, d])
        for p, start, d in held:
            self.add(inst, p, start, d * 0.98, off)

    def bass(self, style, insts=(VC, CB), off=0):
        step, length, only = {"quarters": (1, 0.85, None), "eighths": (0.5, 0.4, None),
                              "half": (2, 1.9, None), "ones": (2, 0.9, None),
                              "one": (4, 0.9, None), "oom": (1, 0.45, None)}[style]
        for t in self.times(step):
            p = place(self.chord(t).bass, 43, 36, 57)
            for inst in insts:
                q = p - 12 if inst == CB and p - 12 >= 28 else p
                self.add(inst, fold(q, inst), t, length, off)

    def timp(self, step=2.0, length=0.5, off=-4):
        for t in self.times(step):
            b = self.chord(t).bass
            if b in (2, 9):         # tuned to the tonic and the dominant, as in 1780
                self.add(TI, 38 if b == 2 else 45, t, length, off)

    def winds(self, off=-10):
        self.sustain(OB, 0, 74, off)
        self.sustain(CL, 1, 65, off)
        self.sustain(HN, "root", 53, off - 2)
        self.sustain(HN, "fifth", 60, off - 2)

    def hammer(self):
        """Every melody note is a chord for the whole orchestra."""
        for p, t, d in self.mel:
            ch, d = self.chord(t), d * 0.9
            self.add(V1, p, t, d, 8)
            self.add(FL, fold(p + 12, FL), t, d, 4)
            for inst, picks, center in ((V2, (0, 1), 66), (VA, (2, 0), 57), (OB, (0,), 74),
                                        (CL, (1,), 65)):
                for q in self.tones(inst, picks, center, t):
                    self.add(inst, q, t, d, 2)
            low = place(ch.bass, 43, 36, 57)
            for inst, q in ((VC, low), (BN, low), (CB, low - 12 if low >= 40 else low),
                            (HN, place(ch.root, 53, 41, 72)), (HN, place(ch.fifth, 60, 41, 72))):
                self.add(inst, q, t, d, 2)
            if ch.bass in (2, 9):
                self.add(TI, 38 if ch.bass == 2 else 45, t, d, 4)


# ---- textures: who plays what --------------------------------------------------
def tutti(s):
    s.line(V1)
    s.line(FL, 12, 2)
    s.pulse(V2, (0, 1), 66)
    s.pulse(VA, (2, 0), 57)
    s.bass("quarters", (VC, CB, BN))
    s.winds()
    s.timp()


def strings(s):
    s.line(V1)
    s.alberti(V2, 64)
    s.sustain(VA, 2, 57)
    s.bass("ones", (VC,), -4)
    s.bass("one", (CB,), -6)


def winds(s):
    top = max(p for p, _, _ in s.mel)
    s.line(FL, 12 if top <= 81 else 0, 10)
    s.line(CL, 0 if top <= 81 else -12, 2)
    s.sustain(BN, "bass", 48, -8)
    s.pulse(V1, (0, 1), 67, off=-12)
    s.pulse(V2, (2, 0), 60, off=-12)
    s.sustain(VA, 1, 55, -10)
    s.bass("ones", (VC,), -6)


def pedal(s):
    s.line(V1)
    s.pulse(V2, (0, 1), 64)
    s.pulse(VA, (2, 0), 57)
    s.bass("quarters", (VC, CB), -2)
    s.sustain(HN, "bass", 57, -8)
    s.timp(1.0, 0.4, -10)


def andante_strings(s):
    s.line(V1)
    s.alberti(V2, 62)
    s.sustain(VA, 2, 57)
    s.bass("half", (VC,), -4)
    s.bass("one", (CB,), -8)


def andante_oboe(s):
    s.line(OB, 0, 12)
    s.pulse(V1, (0, 1), 67, off=-10)
    s.pulse(V2, (2, 0), 60, off=-10)
    s.sustain(VA, 1, 55)
    s.sustain(BN, "bass", 48)
    s.bass("quarters", (VC, CB), -6)


def andante_full(s):
    s.line(V1)
    s.line(FL, 12, 4)
    s.alberti(V2, 64, 0.25)
    s.sustain(VA, 2, 57)
    s.sustain(CL, 0, 64, -8)
    s.sustain(HN, "root", 55, -12)
    s.bass("half", (VC,), -4)
    s.bass("ones", (CB,), -8)


def andante_coda(s):
    s.line(V1)
    s.line(FL, 12, 0)
    for inst, pick, center in ((V2, 0, 64), (VA, 2, 57), (CL, 1, 62), (HN, "root", 55),
                               (BN, "bass", 48), (VC, "bass", 43), (CB, "bass", 31)):
        s.sustain(inst, pick, center, -8)


def rondo_p(s):
    s.line(V1)
    s.pulse(V2, (0, 1), 66, 1.0, 0.35, -8, 0.5)     # after-beats
    s.pulse(VA, (2, 0), 57, 1.0, 0.35, -8, 0.5)
    s.bass("oom", (VC,), -4)
    s.bass("ones", (CB,), -6)


def rondo_winds(s):
    s.line(FL, 0, 10)
    s.line(CL, -12, 2)
    s.sustain(BN, "bass", 48, -8)
    s.pulse(V1, (0, 1), 67, 1.0, 0.35, -12, 0.5)
    s.pulse(V2, (2, 0), 60, 1.0, 0.35, -12, 0.5)
    s.sustain(VA, 1, 55, -10)
    s.bass("oom", (VC,), -6)


def storm(s):
    s.line(V1)
    s.line(FL, 12, 2)
    s.pulse(V2, (0, 1), 66, 0.25, 0.2)
    s.pulse(VA, (2, 0), 57, 0.25, 0.2)
    s.bass("eighths", (VC, CB, BN))
    s.winds(-6)
    s.timp(0.5, 0.3, -6)


TEXTURES = {"tutti": tutti, "strings": strings, "winds": winds, "pedal": pedal,
            "hammer": Seg.hammer, "andante_strings": andante_strings,
            "andante_oboe": andante_oboe, "andante_full": andante_full,
            "andante_coda": andante_coda, "rondo_p": rondo_p, "rondo_f": tutti,
            "rondo_winds": rondo_winds, "storm": storm}

# ---- I. Allegro: the themes ------------------------------------------------------
T1 = ("D5:2 F#5:1 A5:1 | D6:1.5 C#6:0.5 B5:0.5 A5:0.5 G5:0.5 F#5:0.5 | E5:1 G5:1 B5:1.5 A5:0.5 |"
      "A5:1 G5:0.5 F#5:0.5 E5:1 r:1 | D5:2 F#5:1 A5:1 | D6:1.5 E6:0.5 F#6:0.5 E6:0.5 D6:0.5 B5:0.5 |"
      "G5:1 B5:0.5 A5:0.5 F#5:1 E5:1 | D5:1 F#5:0.5 A5:0.5 D6:1 r:1",
      "D | D | Em:3 A7:1 | A7 | D | D:2 Bm:2 | G:2 D/A:1 A7:1 | D")
FIG = "%s:0.5 %s:0.5 %s:0.5 %s:0.5 %s:0.5 %s:0.5 %s:0.5 %s:0.5"


def fig(a, b, c):
    return FIG % (a, b, c, b, a, b, c, b)


BRIDGE = (" | ".join([fig("D5", "F#5", "A5"), fig("G5", "B5", "D6"), fig("E5", "G#5", "B5"),
                      "A5:0.5 C#6:0.5 E6:0.5 C#6:0.5 A5:1 r:1",
                      "F#5:0.5 A5:0.5 D6:1 E5:0.5 G#5:0.5 B5:1",
                      "C#6:0.5 B5:0.5 A5:0.5 G#5:0.5 A5:1 C#6:1",
                      "B5:0.5 A5:0.5 G#5:0.5 F#5:0.5 E5:1 G#5:1"]),
          "D | G | E7 | A | D:2 E7:2 | A | B7:2 E:2")
BRIDGE_HOME = (" | ".join([fig("D5", "F#5", "A5"), fig("G5", "B5", "D6"), fig("E5", "G5", "B5"),
                           "A5:0.5 C#6:0.5 E6:0.5 C#6:0.5 A5:1 r:1",
                           "B5:0.5 D6:0.5 G6:1 A5:0.5 C#6:0.5 E6:1",
                           "F#6:0.5 E6:0.5 D6:0.5 C#6:0.5 D6:1 F#6:1",
                           "E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A5:1 C#6:1"]),
               "D | G | Em | A | G:2 A7:2 | D | E7:2 A:2")
T2_HEAD = ("C#5:1.5 D5:0.5 E5:1 A5:1 | G#5:1.5 F#5:0.5 E5:2 | D5:1.5 E5:0.5 F#5:1 B5:1 |"
           "A5:1 G#5:0.5 F#5:0.5 E5:2 | C#5:1.5 D5:0.5 E5:1 A5:1 | C#6:1.5 B5:0.5 A5:1 F#5:1 | ")
T2_C = "A | E7 | Bm | E7 | A | F#m:2 D:2 | A/E:2 E7:2 | A"
T2 = (T2_HEAD + "E5:1 D5:0.5 C#5:0.5 B4:1.5 A4:0.5 | A4:2 r:2", T2_C)
T2_WINDS = (T2_HEAD + "E5:1 C#5:0.5 A5:0.5 G#5:1 B5:1 | A5:2 r:2", T2_C)
CLOSING = ("A5:0.5 B5:0.5 C#6:0.5 D6:0.5 E6:1 C#6:1 | D6:0.5 C#6:0.5 B5:0.5 A5:0.5 G#5:1 E5:1 |"
           "A5:0.5 B5:0.5 C#6:0.5 D6:0.5 E6:1 A6:1 | F#6:0.5 E6:0.5 D6:0.5 C#6:0.5 B5:1 G#5:1 |"
           "A5:1 E5:1 C#5:1 E5:1", "A | D:2 E7:2 | A | D:2 E7:2 | A")

ALLEGRO = [
    ("I Allegro - Theme 1", "#4C8BF5", [
        Seg("tutti", "f", *T1),
        Seg("tutti", "f<ff", *BRIDGE),
        Seg("hammer", "ff", "E5:1 r:1 E5:1 r:1", "E")]),
    ("I Allegro - Theme 2", "#5FB889", [
        Seg("strings", "p", *T2),
        Seg("winds", "p<mf", *T2_WINDS)]),
    ("I Allegro - Closing", "#F5A623", [
        Seg("tutti", "f", *CLOSING),
        Seg("hammer", "ff", "A5:1 A5:1 A5:1 r:1", "A")]),
    ("I Allegro - Development", "#9B59B6", [
        Seg("strings", "p", "A4:2 C5:1 E5:1 | A5:1.5 G5:0.5 F5:0.5 E5:0.5 D5:0.5 C5:0.5 |"
                            "B4:1 D5:1 F5:1.5 E5:0.5 | E5:1 D5:0.5 C5:0.5 B4:1 r:1",
            "Am | Am | Bdim | E7"),
        Seg("tutti", "f", "E5:2 G5:1 B5:1 | E6:1.5 D6:0.5 C6:0.5 B5:0.5 A5:0.5 G5:0.5 |"
                          "F#5:2 B5:1 D6:1 | F#6:1.5 E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A#5:0.5",
            "Em | Em | Bm | Bm:2 F#7:2"),
        Seg("tutti", "ff", " | ".join([
            fig("B5", "D6", "F#6"),
            "G#5:0.5 B5:0.5 E6:0.5 B5:0.5 G#5:0.5 B5:0.5 D6:0.5 B5:0.5",
            "A5:0.5 C#6:0.5 E6:0.5 C#6:0.5 G5:0.5 C#6:0.5 E6:0.5 C#6:0.5",
            fig("F#5", "A5", "D6"),
            "G5:0.5 B5:0.5 D6:0.5 B5:0.5 E5:0.5 G5:0.5 B5:0.5 G5:0.5",
            "C#6:1 A5:1 E5:1 A5:1"]), "Bm | E7 | A7 | D | G:2 Em:2 | A"),
        Seg("pedal", "p", "G5:1.5 F#5:0.5 E5:1 C#5:1 | D5:1 F#5:1 E5:1 C#5:1 |"
                          "G5:1.5 F#5:0.5 E5:1 C#5:1", "A7 | D/A:2 A7:2 | A7"),
        Seg("pedal", "p<f", "A4:0.5 B4:0.5 C#5:0.5 D5:0.5 E5:0.5 F#5:0.5 G5:0.5 A5:0.5", "A7")]),
    ("I Allegro - Reprise", "#4C8BF5", [
        Seg("tutti", "f", *T1),
        Seg("tutti", "f<ff", *BRIDGE_HOME),
        Seg("hammer", "ff", "A5:1 r:1 A5:1 r:1", "A")]),
    ("I Allegro - Theme 2 at home", "#5FB889", [
        Seg("strings", "p", *T2, tr=5),
        Seg("winds", "p<mf", *T2_WINDS, tr=5)]),
    ("I Allegro - Closing at home", "#F5A623", [
        Seg("tutti", "f", *CLOSING, tr=-7),
        Seg("hammer", "ff", "D6:1 D6:1 D6:1 r:1", "D")]),
    ("I Allegro - Coda", "#E05555", [
        Seg("tutti", "ff", "D5:0.5 F#5:0.5 A5:0.5 D6:0.5 F#6:1 D6:1 |"
                           "E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A5:1 C#6:1 |"
                           "D5:0.5 F#5:0.5 A5:0.5 D6:0.5 F#6:1 D6:1 |"
                           "E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A5:1 C#6:1 |"
                           "D6:1 A5:1 F#5:1 A5:1 | B5:1 G5:1 E5:1 C#5:1",
            "D | Em:2 A7:2 | D | Em:2 A7:2 | D | G:2 A7:2"),
        Seg("hammer", "ff", "D6:1 r:1 D6:1 r:1 | D6:3 r:1", "D | D")]),
]

# ---- II. Andante --------------------------------------------------------------------
SONG = ("B4:1.5 C5:0.5 D5:1 G5:1 | A5:1.5 G5:0.5 F#5:1 D5:1 | E5:1.5 F#5:0.5 G5:1 C6:1 |"
        "B5:1 A5:0.5 G5:0.5 A5:2 | B4:1.5 C5:0.5 D5:1 G5:1 | B5:1.5 A5:0.5 G5:1 E5:1 |"
        "D5:1 E5:0.5 F#5:0.5 A5:1 F#5:1 | G5:3 r:1",
        "G | D7/F# | C | G/D:2 D:2 | G | Em:2 C:2 | G/D:2 D7:2 | G")
ANDANTE = [
    ("II Andante - Song", "#5FB889", [Seg("andante_strings", "p", *SONG)]),
    ("II Andante - Oboe episode", "#9B59B6", [
        Seg("andante_oboe", "mp", "E5:1 G5:1 B5:1.5 A5:0.5 | C6:1 B5:0.5 A5:0.5 G5:1 F#5:1 |"
                                  "E5:1 G5:1 B5:1 E6:1 | E6:1 C#6:0.5 A5:0.5 G5:1 E5:1",
            "Em | Am:2 B7:2 | Em | A7"),
        Seg("andante_oboe", "mp>p", "F#5:1.5 G5:0.5 A5:1 D6:1 | C#6:1 B5:0.5 A5:0.5 B5:1 F#5:1 |"
                                    "G5:1 E5:1 D5:1 C#5:1 | D5:2 C5:1 A4:1",
            "D | A7:2 Bm:2 | Em:2 A7:2 | D:2 D7:2")]),
    ("II Andante - Song with flute", "#5FB889", [Seg("andante_full", "mp", *SONG)]),
    ("II Andante - Coda", "#E05555", [
        Seg("andante_coda", "p>pp", "G5:1.5 A5:0.5 B5:1 D6:1 | E6:2 Eb6:1 C6:1 |"
                                    "B5:1 D6:1 A5:1.5 F#5:0.5 | G5:4",
            "G | C:2 Cm:2 | G/D:2 D7:2 | G")]),
]

# ---- III. Rondo ---------------------------------------------------------------------
HEAD = "F#5:0.5 A5:0.5 D6:0.5 A5:0.5 F#5:0.5 A5:0.5 D6:1"
REFRAIN = [
    Seg("rondo_p", "p", HEAD + " | E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A5:1 r:1 |"
        "G5:0.5 B5:0.5 E6:0.5 B5:0.5 G5:0.5 B5:0.5 E6:1 |"
        "D6:0.5 C#6:0.5 B5:0.5 A5:0.5 G5:0.5 F#5:0.5 E5:1", "D | A7 | Em | A7"),
    Seg("rondo_f", "f", HEAD + " | E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A5:1 F#5:1 |"
        "G5:0.5 B5:0.5 E6:0.5 D6:0.5 C#6:0.5 E6:0.5 A5:0.5 C#6:0.5 | D6:1 A5:1 D5:1 r:1",
        "D | A7:2 D:2 | Em:2 A7:2 | D")]
RONDO = [
    ("III Rondo - Refrain", "#4C8BF5", REFRAIN),
    ("III Rondo - Wind episode", "#5FB889", [
        Seg("rondo_winds", "mp", "E5:1 A5:1 C#6:0.5 B5:0.5 A5:1 | G#5:0.5 A5:0.5 B5:1 E5:1 r:1 |"
                                 "E5:1 B5:1 D6:0.5 C#6:0.5 B5:1 | A5:0.5 B5:0.5 C#6:1 A5:1 r:1 |"
                                 "F#5:1 B5:1 D6:0.5 C#6:0.5 B5:1 | E5:1 A5:1 C#6:0.5 B5:0.5 A5:1 |"
                                 "D6:0.5 C#6:0.5 B5:0.5 A5:0.5 G#5:0.5 B5:0.5 E5:0.5 G#5:0.5 |"
                                 "A5:1 G5:1 E5:1 C#5:1",
            "A | E7 | E7 | A | Bm | A | Bm:2 E7:2 | A:1 A7:3")]),
    ("III Rondo - Storm", "#9B59B6", [
        Seg("storm", "ff", "D5:1 F5:1 A5:1 D6:1 | C#6:0.5 D6:0.5 E6:0.5 D6:0.5 C#6:0.5 A5:0.5 E5:1 |"
                           "D5:1 F5:1 A5:1 D6:1 | E6:0.5 F6:0.5 G6:0.5 F6:0.5 E6:0.5 C6:0.5 G5:1 |"
                           "F5:1 A5:1 C6:1 F6:1 | D6:0.5 C6:0.5 Bb5:0.5 G5:0.5 A5:1 F5:1 |"
                           "G5:1 Bb5:1 E5:1 G5:1 | F5:1 E5:1 D5:1 r:1",
            "Dm | A7 | Dm | C7 | F | Bb:2 F:2 | Gm:2 A7:2 | Dm/A:1 A7:1 Dm:2"),
        Seg("pedal", "f>p", "A5:1 C#6:1 E6:1 C#6:1 | Bb5:1 G5:1 E5:1 C#5:1", "A | A7"),
        Seg("pedal", "p<mf", "A5:1 C#6:1 E6:1 C#6:1 |"
                             "E5:0.5 F#5:0.5 G5:0.5 A5:0.5 B5:0.5 C#6:0.5 D6:0.5 E6:0.5", "A | A7")]),
    ("III Rondo - Coda", "#E05555", [
        Seg("rondo_f", "ff", " | ".join([
            HEAD, "G6:0.5 F#6:0.5 E6:0.5 D6:0.5 C#6:0.5 B5:0.5 A5:1", HEAD,
            "B5:0.5 D6:0.5 G6:0.5 D6:0.5 E6:0.5 C#6:0.5 A5:0.5 C#6:0.5",
            "D6:0.5 A5:0.5 F#5:0.5 A5:0.5 D6:0.5 A5:0.5 F#5:0.5 A5:0.5",
            "D6:0.5 B5:0.5 G5:0.5 B5:0.5 C#6:0.5 A5:0.5 E5:0.5 A5:0.5"]),
            "D | G:2 A7:2 | D | G:2 A7:2 | D | G:2 A7:2"),
        Seg("hammer", "ff", "D6:1 r:1 D6:1 r:1 | D6:3 r:1", "D | D")]),
]

# movement: (sections, how long a written beat lasts in FL beats, legato, playing order)
MOVEMENTS = [("I. Allegro", ALLEGRO, 1, False, range(8)),
             ("II. Andante", ANDANTE, 2, True, range(4)),
             ("III. Rondo", RONDO, 1, False, (0, 1, 0, 2, 0, 3))]
GAP = 2     # empty bars between movements


def compose(seed=1791):
    """[{"movement", "order", "sections": [{"name", "color", "bars", "parts"}]}]."""
    rng, out = random.Random(seed), []
    for title, sections, scale, legato, order in MOVEMENTS:
        made = []
        for name, color, segs in sections:
            parts, at = collections.defaultdict(list), 0.0
            for seg in segs:
                for inst, notes in seg.render(rng, legato).items():
                    parts[inst] += [[p, round((at + t) * scale, 4), round(d * scale, 4), v]
                                    for p, t, d, v in notes]
                at += seg.beats
            bars = at * scale / 4
            end = max(s + d for notes in parts.values() for _, s, d, _ in notes)
            if bars != int(bars) or end <= (bars - 1) * 4:
                raise ValueError("%s: %g bars, but its notes end at beat %g" % (name, bars, end))
            for inst, notes in parts.items():
                lo, hi = ORCHESTRA[inst][4:6]
                if any(not lo <= n[0] <= hi for n in notes):
                    raise ValueError("%s: %s leaves its range" % (name, inst))
            made.append({"name": name, "color": color, "bars": int(bars),
                         "parts": {inst: sorted(n, key=lambda x: (x[1], x[0]))
                                   for inst, n in parts.items()}})
        out.append({"movement": title, "order": list(order), "sections": made})
    return out


def plan(piece):
    """[(movement, first bar, [(section index, bar, bars)])] and the last bar."""
    bar, rows = 1, []
    for mv in piece:
        first, laid = bar, []
        for i in mv["order"]:
            laid.append((i, bar, mv["sections"][i]["bars"]))
            bar += mv["sections"][i]["bars"]
        rows.append((mv["movement"], first, laid))
        bar += GAP
    return rows, bar - GAP - 1


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    piece = compose()
    rows, last = plan(piece)
    do = argv[1] if len(argv) > 1 else "plan"
    if do == "plan":
        for (title, first, laid), mv in zip(rows, piece):
            print("%s (from bar %d)" % (title, first))
            for i, bar, bars in laid:
                sec = mv["sections"][i]
                print("  bars %3d-%3d  %-32s %5d notes on %d parts" % (
                    bar, bar + bars - 1, sec["name"], sum(map(len, sec["parts"].values())),
                    len(sec["parts"])))
        print("%d bars, %.1f minutes at %d BPM" % (last, last * 4 / TEMPO, TEMPO))
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        if do == "build":
            have = {c["name"] for c in engine.status()["channels"]}
            for name, (sound, color, volume, pan, _, _) in ORCHESTRA.items():
                if name in have:
                    continue
                made = engine.add_channel(sound, name, color, volume, pan)
                print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                      made["warnings"], file=sys.stderr)
        elif do == "write":
            sections = [dict(sec) for mv in piece for sec in mv["sections"]]
            done = engine.write_song(sections, tempo=TEMPO, arrange=False)
            numbers = [s["pattern"] for s in done["sections"]]
            print(json.dumps({"patterns": numbers, "problems": done["problems"]}))
            at = 0
            for (title, first, laid), mv in zip(rows, piece):
                mine = numbers[at:at + len(mv["sections"])]
                at += len(mv["sections"])
                out = engine.arrange([{"pattern": mine[i]} for i, _, _ in laid], 1, first)
                print(title, "bars %d-%d" % (out["startBar"], out["endBar"]), out["warnings"])
    finally:
        link.close()


if __name__ == "__main__":
    main(sys.argv)
