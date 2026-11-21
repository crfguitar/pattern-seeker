"""Divertimento in B-flat - a hand-written Classical-era piece in three movements
for ten players: flute, oboe, clarinet, bassoon, horns and a string section.
Ten, so every part gets one of the user's CFilteR-01 inserts (mixer 1-10).

    python examples/divertimento.py           # compose and print the plan
    python examples/divertimento.py json      # dump the sections (for write_song)
    python examples/divertimento.py write     # write the patterns, lay out the song
    python examples/divertimento.py rewrite   # new notes into patterns 2-17, playlist kept

  I   Allegro con brio, B-flat, sonata form with the exposition repeated: a
      rising theme 1 (tutti), a transition to F, a singing theme 2 in F (strings,
      then winds), closing; a development through G minor and C minor onto an F7
      pedal; the recapitulation with theme 2 at home; coda.
  II  Adagio cantabile, E-flat (the subdominant), A B A + coda: the violins sing,
      the clarinet takes a C minor episode, the song returns with flute and horns.
  III Finale, Allegro molto in 6/8, a hunting rondo: A B A C A + coda, with a
      wind episode in F and a G minor storm over an F7 pedal.

FL has one tempo, so everything is written at 120 BPM: the Adagio in doubled
note values (it sounds at 60), the 6/8 finale with eighths a third of a beat
(dotted quarter = 120). Same method as examples/sinfonietta.py: themes and
chords by hand, `textures` hand the lines and chords to the players.
"""

import collections
import json
import os
import random
import re
import sys

TEMPO = 120
PCS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Dynamics as velocity. FLEX turns velocity straight into loudness, so the
# whole range is kept narrow (pp to ff = 34 velocity steps, was 70), the parts
# sit closer together (OFF_SCALE), and a change of dynamic arrives over RAMP
# bars instead of on one beat (see `shape`): no section starts with a jump.
DYN = {"pp": 54, "p": 60, "mp": 67, "mf": 74, "f": 82, "ff": 88}
OFF_SCALE = 0.5         # melody over accompaniment: +5 / -4 instead of +10 / -8
ACCENT = 3              # first beat of a bar
JITTER = 2              # +/- random, so repeated notes aren't machine-identical
RAMP = 2.0              # bars (in written time) a change of level takes
QUAL = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10),
        "dim": (0, 3, 6), "maj7": (0, 4, 7, 11)}

# channel: (sound, colour, volume, pan, lowest note, highest note) - middle C is 60.
# Rack order = insert order: Flute is channel 1 -> insert 1 ... Basses 10 -> insert 10.
ORCHESTRA = {
    "Flute": ("FLEX/Essential Winds/Flutes Sustain", "#8FD3F4", 0.50, -0.10, 60, 93),
    "Oboe": ("FLEX/Essential Winds/Oboes Sustain", "#F4C98F", 0.46, 0.10, 58, 88),
    "Clarinet": ("FLEX/Essential Winds/Clarinets Sustain", "#B79FE8", 0.46, -0.18, 50, 86),
    "Bassoon": ("FLEX/Essential Winds/Bassoon Sustain", "#A9785A", 0.48, 0.18, 34, 67),
    "Horns": ("FLEX/Essential Winds/Horns Sustain", "#E0B040", 0.42, -0.28, 41, 72),
    "Violins 1": ("FLEX/Essential Strings/Violins Sustain", "#5FA8E8", 0.62, -0.38, 55, 96),
    "Violins 2": ("FLEX/Essential Strings/Violins Sustain", "#4C8BD0", 0.55, -0.14, 55, 88),
    "Violas": ("FLEX/Essential Strings/Violas Sustain", "#5FB889", 0.55, 0.14, 48, 79),
    "Cellos": ("FLEX/Essential Strings/Cellos Sustain", "#3F9E6E", 0.60, 0.32, 36, 69),
    "Basses": ("FLEX/Essential Strings/Bass Sustain", "#2F7F58", 0.55, 0.42, 28, 55),
}
V1, V2, VA, VC, CB = "Violins 1", "Violins 2", "Violas", "Cellos", "Basses"
FL, OB, CL, BN, HN = "Flute", "Oboe", "Clarinet", "Bassoon", "Horns"


def pc(name):
    return (PCS[name[0]] + name.count("#") - name.count("b")) % 12


def midi(name):
    """'F#5' -> 78, 'Bb4' -> 70 (C4 = 60, middle C)."""
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
        order = (1, 3, 0, 2) if len(self.pcs) == 4 else (1, 0, 2)
        self.order = [self.pcs[i] for i in order]
        self.fifth = self.pcs[2]
        self.bass = (pc(m.group(3)) + tr) % 12 if m.group(3) else self.root


def melody(text, tr=0, bar=4.0):
    """'D5:2 F#5:1 r:1 | ...' -> ([(pitch, start, length)], total). Bars are checked."""
    notes, t = [], 0.0
    for n, chunk in enumerate(text.split("|"), 1):
        start = t
        for tok in chunk.split():
            name, _, d = tok.partition(":")
            if name != "r":
                notes.append((midi(name) + tr, t, float(d)))
            t += float(d)
        if abs(t - start - bar) > 1e-6:
            raise ValueError("bar %d (%s) is %g, not %g" % (n, chunk.strip(), t - start, bar))
    return notes, t


def chords(text, tr=0, bar=4.0):
    out, t = [], 0.0
    for n, chunk in enumerate(text.split("|"), 1):
        start = t
        for tok in chunk.split():
            name, _, d = tok.partition(":")
            out.append((t, float(d or bar), Chord(name, tr)))
            t += float(d or bar)
        if abs(t - start - bar) > 1e-6:
            raise ValueError("chord bar %d (%s) is %g" % (n, chunk.strip(), t - start))
    return out, t


def place(pitch_class, center, lo, hi):
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
    """One stretch of music in one texture. `bar` is the written bar length:
    4 quarter-beats, or 6 eighths in the 6/8 finale."""

    def __init__(self, texture, dyn, mel, chd, tr=0, bar=4.0):
        self.texture, self.tr, self.bar = texture, tr, bar
        self.soft, _, self.loud = dyn.replace(">", "<").partition("<")
        self.mel, beats = melody(mel, tr, bar)
        self.tl, cbeats = chords(chd, tr, bar)
        if abs(beats - cbeats) > 1e-6:
            raise ValueError("melody is %g, chords %g: %s" % (beats, cbeats, mel[:40]))
        self.beats = beats
        self.long_at = 1 if bar == 4 else 2     # shorter notes are played detached

    def render(self, rng, legato):
        self.out, self.rng, self.legato = collections.defaultdict(list), rng, legato
        self.leads = set()
        TEXTURES[self.texture](self)
        return self.out

    def chord(self, t):
        now = self.tl[0][2]
        for start, _, ch in self.tl:
            if start <= t + 1e-9:
                now = ch
        return now

    def add(self, inst, p, t, d, off=0):
        """A note; its last field is its offset from the dynamic level, which
        `shape` turns into a velocity once the whole section is known."""
        accent = ACCENT if abs(t % self.bar) < 1e-6 else 0
        self.out[inst].append((int(p), t, d, off * OFF_SCALE + accent
                               + self.rng.randint(-JITTER, JITTER)))

    def times(self, step, start=0.0):
        t = start
        while t < self.beats - 1e-9:
            yield t
            t += step

    def line(self, inst, shift=0, off=10):
        """The melody on `inst`, louder toward its high notes."""
        self.leads.add(inst)
        mean = sum(p for p, _, _ in self.mel) / len(self.mel)
        for p, t, d in self.mel:
            long = d >= self.long_at or self.legato
            self.add(inst, fold(p + shift, inst), t, d * (0.96 if long else 0.8),
                     off + max(-6, min(6, (p - mean) * 0.4)))

    def tones(self, inst, picks, center, t):
        ch = self.chord(t)
        lo, hi = ORCHESTRA[inst][4:6]
        return sorted({place(ch.order[i % len(ch.order)], center, lo, hi) for i in picks})

    def pulse(self, inst, picks, center, step=0.5, length=0.4, off=-8, start=0.0):
        for t in self.times(step, start):
            for p in self.tones(inst, picks, center, t):
                self.add(inst, p, t, length, off)

    def alberti(self, inst, center, step=0.5, off=-8):
        for t in self.times(step):
            tones = self.tones(inst, (0, 1, 2), center, t)
            k = int(round(t / step)) % 4
            self.add(inst, tones[(0, -1, len(tones) // 2, -1)[k]], t, step * 0.9, off)

    def sustain(self, inst, pick, center, off=-10):
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

    BASS = {"quarters": (1, 0.85), "eighths": (0.5, 0.4), "half": (2, 1.9), "ones": (2, 0.9),
            "one": (4, 0.9), "lilt": (3, 1.6), "bar68": (6, 1.6), "e8": (1, 0.6)}

    def bass(self, style, insts=(VC, CB), off=0):
        step, length = self.BASS[style]
        for t in self.times(step):
            p = place(self.chord(t).bass, 43, 36, 57)
            for inst in insts:
                q = p - 12 if inst == CB and p - 12 >= 28 else p
                self.add(inst, fold(q, inst), t, length, off)

    def winds(self, off=-10):
        self.sustain(OB, 0, 74, off)
        self.sustain(CL, 1, 65, off)
        self.sustain(HN, "root", 53, off - 2)
        self.sustain(HN, "fifth", 60, off - 2)

    def hammer(self):
        """Every melody note is a chord for the whole orchestra."""
        self.leads.add(V1)
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


# ---- textures ------------------------------------------------------------------
def tutti(s):
    s.line(V1)
    s.line(FL, 12, 2)
    s.pulse(V2, (0, 1), 66)
    s.pulse(VA, (2, 0), 57)
    s.bass("quarters", (VC, CB, BN))
    s.winds()


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
    s.sustain(BN, "bass", 41, -10)


def adagio_strings(s):
    s.line(V1)
    s.alberti(V2, 62)
    s.sustain(VA, 2, 57)
    s.bass("half", (VC,), -4)
    s.bass("one", (CB,), -8)


def adagio_clarinet(s):
    s.line(CL, 0, 12)
    s.pulse(V1, (0, 1), 67, off=-12)
    s.pulse(V2, (2, 0), 60, off=-12)
    s.sustain(VA, 1, 55)
    s.sustain(BN, "bass", 46)
    s.bass("quarters", (VC, CB), -6)


def adagio_full(s):
    s.line(V1)
    s.line(FL, 12, 4)
    s.alberti(V2, 64, 0.25)
    s.sustain(VA, 2, 57)
    s.sustain(CL, 0, 64, -8)
    s.sustain(HN, "root", 55, -12)
    s.bass("half", (VC,), -4)
    s.bass("ones", (CB,), -8)


def adagio_coda(s):
    s.line(V1)
    s.line(FL, 12, 0)
    for inst, pick, center in ((V2, 0, 64), (VA, 2, 57), (CL, 1, 62), (HN, "root", 55),
                               (BN, "bass", 46), (VC, "bass", 43), (CB, "bass", 31)):
        s.sustain(inst, pick, center, -8)


# 6/8: steps are in eighths; after-beats fall on eighths 2-3 and 5-6
def afterbeats(s, inst, picks, center, off=-8):
    s.pulse(inst, picks, center, 3, 0.7, off, 1)
    s.pulse(inst, picks, center, 3, 0.7, off, 2)


def hunt_p(s):
    s.line(V1)
    afterbeats(s, V2, (0, 1), 66)
    afterbeats(s, VA, (2, 0), 57)
    s.bass("lilt", (VC,), -4)
    s.bass("bar68", (CB,), -6)


def hunt_f(s):
    s.line(V1)
    s.line(FL, 12, 2)
    afterbeats(s, V2, (0, 1), 66, -6)
    afterbeats(s, VA, (2, 0), 57, -6)
    s.bass("lilt", (VC, CB, BN))
    s.winds(-6)


def hunt_winds(s):
    top = max(p for p, _, _ in s.mel)
    s.line(FL, 12 if top <= 81 else 0, 10)
    s.line(CL, 0 if top <= 81 else -12, 2)
    s.sustain(BN, "bass", 48, -8)
    afterbeats(s, V1, (0, 1), 67, -12)
    afterbeats(s, V2, (2, 0), 60, -12)
    s.sustain(VA, 1, 55, -10)
    s.bass("lilt", (VC,), -6)


def storm68(s):
    s.line(V1)
    s.line(FL, 12, 2)
    s.pulse(V2, (0, 1), 66, 1, 0.6)
    s.pulse(VA, (2, 0), 57, 1, 0.6)
    s.bass("e8", (VC, CB, BN))
    s.winds(-6)


def pedal68(s):
    s.line(V1)
    s.pulse(V2, (0, 1), 64, 1, 0.6)
    s.pulse(VA, (2, 0), 57, 1, 0.6)
    s.bass("lilt", (VC, CB), -2)
    s.sustain(HN, "bass", 57, -8)
    s.sustain(BN, "bass", 41, -10)


TEXTURES = {"tutti": tutti, "strings": strings, "winds": winds, "pedal": pedal,
            "hammer": Seg.hammer, "adagio_strings": adagio_strings,
            "adagio_clarinet": adagio_clarinet, "adagio_full": adagio_full,
            "adagio_coda": adagio_coda, "hunt_p": hunt_p, "hunt_f": hunt_f,
            "hunt_winds": hunt_winds, "storm68": storm68, "pedal68": pedal68}


def fig(a, b, c):
    return " ".join("%s:0.5" % n for n in (a, b, c, b, a, b, c, b))


# ---- I. Allegro con brio ---------------------------------------------------------
T1 = ("Bb4:1 D5:1 F5:1 Bb5:1 | D6:2 C6:0.5 Bb5:0.5 A5:0.5 G5:0.5 | F5:1.5 Eb5:0.5 D5:1 C5:1 |"
      "C5:1 F5:1 A4:1 r:1 | Bb4:1 D5:1 F5:1 Bb5:1 | Eb6:2 D6:0.5 C6:0.5 Bb5:0.5 A5:0.5 |"
      "F5:1 Bb5:0.5 D6:0.5 C6:1 A5:1 | Bb5:1 F5:1 Bb4:1 r:1",
      "Bb | Bb | F7 | F7 | Bb | Eb | Bb/F:2 F7:2 | Bb")
BRIDGE = (" | ".join([fig("Bb4", "D5", "F5"), fig("Eb5", "G5", "Bb5"), fig("C5", "E5", "G5"),
                      "F5:0.5 A5:0.5 C6:0.5 A5:0.5 F5:1 r:1",
                      "D5:0.5 F5:0.5 Bb5:1 C5:0.5 E5:0.5 G5:1",
                      "A5:0.5 G5:0.5 F5:0.5 E5:0.5 F5:1 A5:1",
                      "G5:0.5 F5:0.5 E5:0.5 D5:0.5 C5:1 E5:1"]),
          "Bb | Eb | C7 | F | Bb:2 C7:2 | F | G7:2 C:2")
BRIDGE_HOME = (" | ".join([fig("Bb4", "D5", "F5"), fig("Eb5", "G5", "Bb5"), fig("C5", "Eb5", "G5"),
                           "F5:0.5 A5:0.5 C6:0.5 A5:0.5 F5:1 r:1",
                           "G5:0.5 Bb5:0.5 Eb6:1 F5:0.5 A5:0.5 C6:1",
                           "D6:0.5 C6:0.5 Bb5:0.5 A5:0.5 Bb5:1 D6:1",
                           "C6:0.5 Bb5:0.5 A5:0.5 G5:0.5 F5:1 A5:1"]),
               "Bb | Eb | Cm | F | Eb:2 F7:2 | Bb | C7:2 F:2")
T2_HEAD = ("A4:1.5 Bb4:0.5 C5:1 F5:1 | E5:1.5 D5:0.5 C5:2 | Bb4:1.5 C5:0.5 D5:1 G5:1 |"
           "G5:1 E5:0.5 D5:0.5 C5:2 | A4:1.5 Bb4:0.5 C5:1 F5:1 | A5:1.5 G5:0.5 F5:1 D5:1 | ")
T2_C = "F | C7 | Gm | C7 | F | Dm:2 Bb:2 | F/C:2 C7:2 | F"
T2 = (T2_HEAD + "C5:1 Bb4:0.5 A4:0.5 G4:1.5 F4:0.5 | F4:2 r:2", T2_C)
T2_WINDS = (T2_HEAD + "C5:1 A4:0.5 F5:0.5 E5:1 G5:1 | F5:2 r:2", T2_C)
CLOSING = ("F5:0.5 G5:0.5 A5:0.5 Bb5:0.5 C6:1 A5:1 | Bb5:0.5 A5:0.5 G5:0.5 F5:0.5 E5:1 C5:1 |"
           "F5:0.5 G5:0.5 A5:0.5 Bb5:0.5 C6:1 F6:1 | D6:0.5 C6:0.5 Bb5:0.5 A5:0.5 G5:1 E5:1 |"
           "F5:1 C5:1 A4:1 C5:1", "F | Bb:2 C7:2 | F | Bb:2 C7:2 | F")

ALLEGRO = [
    ("I Allegro - Theme 1", "#4C8BF5", [
        Seg("tutti", "f", *T1),
        Seg("tutti", "f", *BRIDGE),
        Seg("hammer", "f", "C5:1 r:1 C5:1 r:1", "C")]),
    ("I Allegro - Theme 2", "#5FB889", [
        Seg("strings", "p", *T2),
        Seg("winds", "p<mf", *T2_WINDS)]),
    ("I Allegro - Closing", "#F5A623", [
        Seg("tutti", "f", *CLOSING),
        Seg("hammer", "f", "F5:1 F5:1 F5:1 r:1", "F")]),
    ("I Allegro - Development", "#9B59B6", [
        Seg("strings", "p<mf", "G4:1 Bb4:1 D5:1 G5:1 | Bb5:2 A5:0.5 G5:0.5 F#5:0.5 E5:0.5 |"
                            "D5:1.5 C5:0.5 Bb4:1 A4:1 | A4:1 D5:1 F#4:1 r:1",
            "Gm | Gm | D7 | D7"),
        Seg("tutti", "f", "C5:1 Eb5:1 G5:1 C6:1 | Eb6:2 D6:0.5 C6:0.5 Bb5:0.5 Ab5:0.5 |"
                          "G5:1 B5:1 D6:1 F6:1 | Eb6:1 D6:1 C6:1 B5:1",
            "Cm | Cm | G7 | Cm:3 G7:1"),
        Seg("tutti", "ff>f", " | ".join([
            fig("C5", "Eb5", "G5"), fig("A4", "C5", "F5"), fig("Bb4", "D5", "F5"),
            fig("G4", "Bb4", "Eb5"),
            "D5:0.5 F5:0.5 Bb5:0.5 F5:0.5 Eb5:0.5 G5:0.5 C6:0.5 G5:0.5",
            "F5:1 A5:1 C6:1 Eb6:1"]), "Cm | F7 | Bb | Eb | Bb:2 Cm:2 | F7"),
        Seg("pedal", "mf>mp", "Eb5:1.5 D5:0.5 C5:1 A4:1 | Bb4:1 D5:1 C5:1 A4:1 |"
                          "Eb5:1.5 D5:0.5 C5:1 A4:1", "F7 | Bb/F:2 F7:2 | F7"),
        Seg("pedal", "mp<f", "F4:0.5 G4:0.5 A4:0.5 Bb4:0.5 C5:0.5 D5:0.5 Eb5:0.5 C5:0.5", "F7")]),
    ("I Allegro - Reprise", "#4C8BF5", [
        Seg("tutti", "f", *T1),
        Seg("tutti", "f", *BRIDGE_HOME),
        Seg("hammer", "f", "F5:1 r:1 F5:1 r:1", "F")]),
    ("I Allegro - Theme 2 at home", "#5FB889", [
        Seg("strings", "p", *T2, tr=5),
        Seg("winds", "p<mf", *T2_WINDS, tr=5)]),
    ("I Allegro - Closing at home", "#F5A623", [
        Seg("tutti", "f", *CLOSING, tr=-7),
        Seg("hammer", "f", "Bb5:1 Bb5:1 Bb5:1 r:1", "Bb")]),
    ("I Allegro - Coda", "#E05555", [
        Seg("tutti", "ff", "Bb4:0.5 D5:0.5 F5:0.5 Bb5:0.5 D6:1 Bb5:1 |"
                           "C6:0.5 Bb5:0.5 A5:0.5 G5:0.5 F5:1 A5:1 |"
                           "Bb4:0.5 D5:0.5 F5:0.5 Bb5:0.5 D6:1 Bb5:1 |"
                           "C6:0.5 Bb5:0.5 A5:0.5 G5:0.5 F5:1 A5:1 |"
                           "Bb5:1 F5:1 D5:1 F5:1 | G5:1 Eb5:1 C5:1 A4:1",
            "Bb | Cm:2 F7:2 | Bb | Cm:2 F7:2 | Bb | Eb:2 F7:2"),
        Seg("hammer", "ff", "Bb5:1 r:1 Bb5:1 r:1 | Bb5:3 r:1", "Bb | Bb")]),
]

# ---- II. Adagio cantabile -----------------------------------------------------------
SONG = ("G4:1.5 Ab4:0.5 Bb4:1 Eb5:1 | F5:1.5 Eb5:0.5 D5:1 Bb4:1 | C5:1 Eb5:1 Ab5:1.5 G5:0.5 |"
        "G5:1 F5:0.5 Eb5:0.5 F5:2 | G4:1.5 Ab4:0.5 Bb4:1 Eb5:1 | C6:1.5 Bb5:0.5 Ab5:1 Eb5:1 |"
        "Bb4:1 C5:0.5 D5:0.5 F5:1 D5:1 | Eb5:3 r:1",
        "Eb | Bb7/D | Ab | Eb/Bb:2 Bb:2 | Eb | Cm:2 Ab:2 | Eb/Bb:2 Bb7:2 | Eb")
ADAGIO = [
    ("II Adagio - Song", "#5FB889", [Seg("adagio_strings", "p", *SONG)]),
    ("II Adagio - Clarinet episode", "#9B59B6", [
        Seg("adagio_clarinet", "mp", "G4:1 C5:1 Eb5:1.5 D5:0.5 | F5:1 Eb5:0.5 D5:0.5 C5:1 B4:1 |"
                                     "C5:1 Eb5:1 G5:1 C6:1 | C6:1 Ab5:0.5 Eb5:0.5 F5:1 D5:1",
            "Cm | Fm:2 G7:2 | Cm | Ab:2 G7:2"),
        Seg("adagio_clarinet", "mp>p", "Eb5:1.5 F5:0.5 G5:1 C6:1 | Bb5:1 A5:0.5 G5:0.5 F5:1 Eb5:1 |"
                                       "D5:1 F5:1 Bb5:1.5 Ab5:0.5 | G5:2 F5:1 D5:1",
            "Cm | F7 | Bb:3 Bb7:1 | Eb/Bb:2 Bb7:2")]),
    ("II Adagio - Song with flute", "#5FB889", [Seg("adagio_full", "mp", *SONG)]),
    ("II Adagio - Coda", "#E05555", [
        Seg("adagio_coda", "p>pp", "Eb5:1.5 F5:0.5 G5:1 Bb5:1 | C6:2 B5:1 Ab5:1 |"
                                   "G5:1 Bb5:1 F5:1.5 D5:0.5 | Eb5:4",
            "Eb | Ab:2 Abm:2 | Eb/Bb:2 Bb7:2 | Eb")]),
]

# ---- III. Finale, 6/8 (units are eighths, 6 to a bar) ---------------------------------
B = 6.0
REFRAIN = [
    Seg("hunt_p", "p<mf", "Bb5:2 F5:1 D5:2 F5:1 | Bb5:2 D6:1 C6:2 Bb5:1 | A5:2 C6:1 F5:2 A5:1 |"
                       "Bb5:3 F5:3 | G5:2 Bb5:1 Eb6:2 G5:1 | F5:2 Bb5:1 D6:2 F5:1 |"
                       "Eb5:1 G5:1 C6:1 A5:1 F5:1 Eb5:1 | D5:3 Bb4:3",
        "Bb | Bb:3 F7:3 | F7 | Bb | Eb | Bb | Cm:3 F7:3 | Bb", bar=B),
    Seg("hunt_f", "f", "F5:1 F5:1 F5:1 Bb5:3 | D6:1 C6:1 Bb5:1 F5:3 |"
                       "Eb6:1 D6:1 C6:1 Bb5:1 A5:1 G5:1 | F5:2 A5:1 C6:3 |"
                       "F5:1 F5:1 F5:1 Bb5:3 | D6:1 C6:1 Bb5:1 G5:3 |"
                       "F5:1 Bb5:1 D6:1 C6:2 A5:1 | Bb5:3 Bb4:3",
        "Bb | Bb | Cm:3 F7:3 | F | Bb | Bb:3 Eb:3 | Bb/F:3 F7:3 | Bb", bar=B)]
FINALE = [
    ("III Finale - Refrain", "#4C8BF5", REFRAIN),
    ("III Finale - Wind episode", "#5FB889", [
        Seg("hunt_winds", "mp", "A5:2 C6:1 F6:2 C6:1 | Bb5:2 G5:1 E5:3 | G5:2 Bb5:1 E6:2 Bb5:1 |"
                                "A5:3 F5:3 | D6:2 F6:1 Bb5:2 D6:1 | C6:2 A5:1 F5:3 |"
                                "G5:1 A5:1 Bb5:1 C6:1 Bb5:1 G5:1 | F5:3 r:3",
            "F | C7 | C7 | F | Bb | F | C7 | F", bar=B),
        Seg("hunt_winds", "mp<mf", "C6:1 A5:1 F5:1 Eb5:1 C5:1 A4:1 | Bb4:1 C5:1 D5:1 Eb5:1 E5:1 F5:1",
            "F7 | F7", bar=B)]),
    ("III Finale - Storm", "#9B59B6", [
        Seg("storm68", "ff", "G5:1 Bb5:1 D6:1 G6:3 | F#6:1 G6:1 A6:1 D6:3 |"
                             "Eb6:1 D6:1 C6:1 Bb5:1 A5:1 G5:1 | F#5:3 D5:3 | G5:1 Bb5:1 D6:1 G6:3 |"
                             "Eb6:1 D6:1 C6:1 Bb5:1 A5:1 G5:1 | C6:1 Bb5:1 A5:1 D6:2 F#5:1 | G5:3 r:3",
            "Gm | D7 | Cm:3 D7:3 | D7 | Gm | Cm | Cm:3 D7:3 | Gm", bar=B),
        Seg("pedal68", "f>mp", "F5:1 A5:1 C6:1 Eb6:3 | D6:1 C6:1 A5:1 F5:3", "F7 | F7", bar=B),
        Seg("pedal68", "mp<f", "F5:1 A5:1 C6:1 F6:3 | Eb6:1 D6:1 C6:1 A5:1 G5:1 Eb5:1",
            "F7 | F7", bar=B)]),
    ("III Finale - Coda", "#E05555", [
        Seg("hunt_f", "ff", "Bb5:2 F5:1 D5:2 F5:1 | Bb5:2 D6:1 C6:2 Bb5:1 |"
                            "Eb6:1 D6:1 C6:1 Bb5:1 A5:1 G5:1 | F5:3 A5:3 |"
                            "Bb5:1 D6:1 F6:1 D6:1 Bb5:1 F5:1 | Eb6:1 C6:1 A5:1 F5:1 A5:1 C6:1 |"
                            "Bb5:1 D6:1 F6:1 D6:1 Bb5:1 F5:1 | Eb6:1 C6:1 A5:1 F5:1 A5:1 C6:1",
            "Bb | Bb:3 F7:3 | Cm:3 F7:3 | F7 | Bb | F7 | Bb | F7", bar=B),
        Seg("hammer", "ff", "Bb5:1 r:2 F5:1 r:2 | Bb5:1 r:2 F5:1 r:2 | Bb5:3 Bb5:3 | Bb5:4 r:2",
            "Bb:3 F7:3 | Bb:3 F7:3 | Bb | Bb", bar=B)]),
]

# movement: (sections, FL beats per written unit, legato, playing order)
MOVEMENTS = [("I. Allegro con brio", ALLEGRO, 1, False, (0, 1, 2, 0, 1, 2, 3, 4, 5, 6, 7)),
             ("II. Adagio cantabile", ADAGIO, 2, True, (0, 1, 2, 3)),
             ("III. Finale: Allegro molto", FINALE, 1 / 3.0, False, (0, 1, 0, 2, 0, 3))]
GAP = 2


def shape(levels, notes, window, entry):
    """Velocities from offsets. levels = [(start, end, from, to)] in FL beats;
    the level heard at t is the average of the marked level over the `window`
    centred on t (`entry` before the start), so a change of dynamic becomes a
    crescendo or diminuendo that begins half a window early."""
    def marked(t):
        if t < 0:
            return entry
        for a, b, lo, hi in levels:
            if a <= t < b:
                return lo + (hi - lo) * (t - a) / (b - a)
        return levels[-1][3]
    cache = {}

    def heard(t):
        k = round(t * 4)
        if k not in cache:
            xs = [t - window / 2 + window * (i + 0.5) / 16 for i in range(16)]
            cache[k] = sum(map(marked, xs)) / len(xs)
        return cache[k]
    return [[p, s, d, max(1, min(127, int(round(heard(s) + off))))] for p, s, d, off in notes]


def compose(seed=1786):
    """[{"movement", "order", "sections": [{"name", "color", "bars", "parts", "leads"}]}].
    `leads` = [(start, end, instrument)] in FL beats: who carries the tune when."""
    rng, out = random.Random(seed), []
    for title, sections, scale, legato, order in MOVEMENTS:
        made = []
        for name, color, segs in sections:
            # a section starts at its own level: after the rest that ends the
            # section before, a Classical orchestra drops (or rises) at once
            entry = DYN[segs[0].soft]
            parts, leads, levels, at = collections.defaultdict(list), [], [], 0.0
            for seg in segs:
                levels.append((at * scale, (at + seg.beats) * scale,
                               DYN[seg.soft], DYN[seg.loud or seg.soft]))
                for inst, notes in seg.render(rng, legato).items():
                    parts[inst] += [[p, round((at + t) * scale, 4), round(d * scale, 4), v]
                                    for p, t, d, v in notes]
                leads += [(at * scale, (at + seg.beats) * scale, i) for i in seg.leads]
                at += seg.beats
            bars = round(at * scale / 4, 6)
            end = max(s + d for notes in parts.values() for _, s, d, _ in notes)
            if bars != int(bars) or end <= (bars - 1) * 4:
                raise ValueError("%s: %g bars, but its notes end at beat %g" % (name, bars, end))
            for inst, notes in parts.items():
                lo, hi = ORCHESTRA[inst][4:6]
                if any(not lo <= n[0] <= hi for n in notes):
                    raise ValueError("%s: %s leaves its range" % (name, inst))
            window = max(4.0, RAMP * segs[0].bar * scale)     # at least one FL bar
            made.append({"name": name, "color": color, "bars": int(bars), "leads": leads,
                         "parts": {inst: sorted(shape(levels, n, window, entry),
                                                key=lambda x: (x[1], x[0]))
                                   for inst, n in parts.items()}})
        out.append({"movement": title, "order": list(order), "sections": made})
    return out


def plan(piece):
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
                print("  bars %3d-%3d  %-34s %5d notes on %d parts" % (
                    bar, bar + bars - 1, sec["name"], sum(map(len, sec["parts"].values())),
                    len(sec["parts"])))
        print("%d bars, %.1f minutes at %d BPM" % (last, last * 4 / TEMPO, TEMPO))
        return
    if do == "json":
        print(json.dumps([{k: s[k] for k in ("name", "color", "parts")}
                          for mv in piece for s in mv["sections"]]))
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        if do == "rewrite":
            # new notes into the patterns `write` made (2, 3, ...), playlist untouched;
            # the piano-roll script replaces only Pattern Seeker's own notes
            first = int(argv[2]) if len(argv) > 2 else 2
            secs = [s for mv in piece for s in mv["sections"]]
            for n, sec in enumerate(secs):
                engine._song(pattern=first + n)
                bad = []
                for inst, notes in sec["parts"].items():
                    bad += engine.write_part(inst, notes)["problems"]
                print("pattern %d %s %s" % (first + n, sec["name"], bad or "ok"), flush=True)
        elif do == "write":
            sections = [{k: s[k] for k in ("name", "color", "parts")}
                        for mv in piece for s in mv["sections"]]
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
