"""Run with:  python -m unittest discover tests

Covers the pure logic, and drives the real FL script against a fake channel
rack so the SysEx round trip is exercised without FL Studio.
"""

import importlib.util
import os
import random
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seeker.generator import (CYCLE, SCALES, STEPS, Seeker, bass_pitches,  # noqa: E402
                              chord_notes, generate, genres_for_tempo, pad_notes)
from seeker.library import GENRES, ROLES  # noqa: E402
from seeker.mapping import build_tracks, detect_role, map_rack  # noqa: E402
from seeker import pianoroll, wire  # noqa: E402


class Library(unittest.TestCase):
    def test_every_variant_is_well_formed(self):
        for key, g in GENRES.items():
            for role in ROLES:
                self.assertTrue(g[role], "%s has no %s lane" % (key, role))
                for v in g[role]:
                    self.assertIn(len(v), (0, 16, 32), "%s/%s %r" % (key, role, v))
                    self.assertFalse(set(v) - set("Xxo."), "%s/%s %r" % (key, role, v))


    def test_bass_lines_and_chord_figures_use_known_symbols(self):
        from seeker.library import CHORDS
        for key, g in GENRES.items():
            for line in g["bass"].get("lines", []):
                self.assertIn(len(line), (16, 32), "%s %r" % (key, line))
                self.assertFalse(set(line) - set("12345678abc."), "%s %r" % (key, line))
            self.assertIn(key, CHORDS)
            for r in CHORDS[key]["rhythm"]:
                self.assertIn(len(r), (16, 32), "%s %r" % (key, r))
                self.assertFalse(set(r) - set("x-.1234"), "%s %r" % (key, r))


class NewGenres(unittest.TestCase):
    def test_upper_degrees_climb_instead_of_dropping(self):
        from seeker.generator import bass_pitches
        # C major boogie: C E G A C' A G E
        self.assertEqual(bass_pitches(list("1.3.a.b.8.b.a.3."), 0, "major")[::2],
                         [60, 64, 67, 69, 72, 69, 67, 64])
        self.assertEqual(bass_pitches(list("1...5..."), 0, "major")[::4], [60, 55])   # 5 = below
        # over the IV chord the run keeps climbing (F A C D), it is not folded back
        self.assertEqual(bass_pitches(list("1.3.a.b."), 0, "major", prog="4444")[::2],
                         [65, 69, 72, 74])

    def test_digits_in_a_chord_rhythm_break_the_chord(self):
        from seeker.generator import chord_notes
        notes = chord_notes("1-3-2-3-" * 2, "1111", 0, "major")     # Alberti on C major
        self.assertEqual([(n, s, l) for n, s, l, _ in notes],
                         [(55, 0, 2), (64, 2, 2), (60, 4, 2), (64, 6, 2)] * 1
                         + [(55, 8, 2), (64, 10, 2), (60, 12, 2), (64, 14, 2)])
        block = chord_notes("x-------", "11", 0, "major")
        self.assertEqual(sorted(n for n, _, _, _ in block), [55, 60, 64])
        mixed = chord_notes("1-..x-..", "11", 0, "major")           # bass note, then the chord
        self.assertEqual([n for n, s, _, _ in mixed if s == 0], [55])
        self.assertEqual(len([n for n, s, _, _ in mixed if s == 4]), 3)

    def test_a_genre_without_drums_still_gives_fresh_named_beats(self):
        from seeker.generator import Seeker
        seeker = Seeker(seed=5)
        beats = [seeker.next("classical") for _ in range(8)]
        self.assertTrue(all(b.drumless and not any(b.lanes["kick"]) for b in beats))
        self.assertTrue(all(any(b.lanes["bass"]) for b in beats))
        progs = [b.chords["progs"]["major"] for b in beats]
        self.assertEqual(len(set(progs)), 8)                # the harmony never repeats
        self.assertGreater(len({b.name for b in beats}), 2)
        self.assertFalse(seeker.next("jazz").drumless)

    def test_swing_genres_stay_on_the_shuffle_grid(self):
        for ride in GENRES["jazz"]["hat"]:
            self.assertEqual(len(ride), 32)         # two bars: never run through _vary_hat
            self.assertFalse([i for i, c in enumerate(ride) if c != "." and i % 4 in (1, 2)])


class Generator(unittest.TestCase):
    def test_beats_are_two_bars_with_a_downbeat_kick(self):
        rng = random.Random(1)
        for key in GENRES:
            for _ in range(50):
                beat = generate(key, rng)
                self.assertEqual({len(v) for v in beat.lanes.values()}, {STEPS})
                self.assertTrue(beat.lanes["kick"][0] or beat.drumless)   # classical: no kit
                lo, hi = GENRES[key]["bpm"]
                self.assertTrue(lo <= beat.tempo <= hi)

    def test_seeker_does_not_repeat_itself(self):
        s = Seeker(seed=3)
        sigs = [s.next("trap").signature for _ in range(60)]
        self.assertEqual(len(set(sigs)), 60)

    def test_808_stays_in_key_and_in_range_for_every_genre(self):
        rng = random.Random(5)
        for key in GENRES:
            for _ in range(40):
                beat = generate(key, rng)
                hits = [i for i, v in enumerate(beat.lanes["bass"]) if v]
                self.assertTrue(hits, key)
                self.assertEqual(hits, [i for i, d in enumerate(beat.degrees) if d != "."])
                for root in range(12):
                    for scale, steps in SCALES.items():
                        notes = bass_pitches(beat.degrees, root, scale)
                        allowed = {(root + n) % 12 for n in steps}
                        self.assertTrue({notes[i] % 12 for i in hits} <= allowed)
                        self.assertTrue(all(48 <= notes[i] <= 78 for i in hits))

    def test_trap_808_only_lands_on_kicks(self):
        rng = random.Random(2)
        for _ in range(50):
            beat = generate("trap", rng)
            for i, v in enumerate(beat.lanes["bass"]):
                self.assertFalse(v and not beat.lanes["kick"][i])
            self.assertTrue(beat.lanes["bass"][0])

    def test_chords_are_in_key_voiced_close_and_the_808_plays_their_roots(self):
        rng = random.Random(11)
        for genre in GENRES:
            for _ in range(25):
                beat = generate(genre, rng)
                for root in (0, 4, 9, 11):
                    for scale, steps in SCALES.items():
                        allowed = {(root + n) % 12 for n in steps}
                        prog = beat.chords["progs"][scale]
                        notes = chord_notes(beat.chords["rhythm"], prog, root, scale,
                                            beat.chords["voicing"])
                        self.assertTrue(notes, genre)
                        for number, start, length, vel in notes:
                            self.assertIn(number % 12, allowed)
                            self.assertTrue(55 <= number < 67)
                            self.assertTrue(length > 0 and start + length <= CYCLE)
                            self.assertTrue(1 <= vel <= 127)
                        # every strike is a full chord of 3 or 4 different notes, or
                        # (where the rhythm has a digit) one note of a broken chord
                        starts = {}
                        for number, start, _, _ in notes:
                            starts.setdefault(start, set()).add(number)
                        rhythm = beat.chords["rhythm"]
                        for start, v in starts.items():
                            self.assertIn(len(v), (1,) if rhythm[start].isdigit()
                                          or (rhythm[start] == "-" and len(v) == 1) else (3, 4))

                        self.assertEqual(len(prog), 16)         # a root per beat, 4 bars
                        self.assertNotIn("7" if scale == "major" else "2", prog)
                        relative = beat.relative * 2
                        bass = bass_pitches(relative, root, scale, prog=prog)
                        for i, d in enumerate(relative):
                            if d == ".":
                                continue
                            self.assertIn(bass[i] % 12, allowed)
                            self.assertTrue(46 <= bass[i] <= 78)
                            if d == "1":
                                chord_root = (root + steps[int(prog[i // 4]) - 1]) % 12
                                self.assertEqual(bass[i] % 12, chord_root)

    def test_pad_holds_the_chord_softly_and_ties_shared_notes(self):
        rng = random.Random(5)
        for genre in GENRES:
            for _ in range(25):
                beat = generate(genre, rng)
                for root in (0, 1, 6, 11):
                    for scale, steps in SCALES.items():
                        prog = beat.chords["progs"][scale]
                        notes = pad_notes(prog, root, scale)
                        for beat_no, degree in enumerate(prog):
                            chord = {(root + steps[(int(degree) - 1 + t) % 7]) % 12
                                     for t in (0, 2, 4)}
                            sounding = {n % 12 for n, start, length, _ in notes
                                        if start <= beat_no * 4 < start + length}
                            self.assertEqual(sounding, chord)   # exactly the chord, always
                        for number, start, length, vel in notes:
                            self.assertTrue(67 <= number < 79 and vel < 80)
                            self.assertTrue(length >= 4 and start + length <= CYCLE)
        # C minor then Ab major share C and Eb: those two notes run through.
        notes = pad_notes("1111111166666666", 0, "minor")
        self.assertEqual(sorted((n % 12, s, ln) for n, s, ln, _ in notes),
                         [(0, 0, 64), (3, 0, 64), (7, 0, 32), (8, 32, 32)])

    def test_progressions_keep_changing(self):
        seeker = Seeker(seed=1)
        progs = [seeker.next("pop").chords["progs"]["major"] for _ in range(40)]
        self.assertTrue(len(set(progs)) >= 20)
        self.assertTrue(all(a != b for a, b in zip(progs, progs[1:])))
        self.assertTrue(any(p[0] != "1" for p in progs))        # not always starting at home
        self.assertTrue(any(len(set(p)) >= 5 for p in progs))   # five-chord turnarounds

    def test_a_held_chord_restrikes_when_the_harmony_changes(self):
        notes = chord_notes("x" + "-" * 31, "11116666", 0, "minor", "triad")
        self.assertEqual(sorted({(s, n) for _, s, n, _ in notes}), [(0, 16), (16, 16)])
        self.assertEqual({n % 12 for n, s, _, _ in notes if s == 0}, {0, 3, 7})     # C minor
        self.assertEqual({n % 12 for n, s, _, _ in notes if s == 16}, {8, 0, 3})    # Ab major

    def test_piano_roll_script_replaces_only_its_own_notes(self):
        class Note:
            def __init__(self, number=0, color=0):
                self.number, self.color = number, color
                self.time = self.length = 0
                self.velocity = 0.8

        class Score:
            PPQ = 96

            def __init__(self):
                self.notes = [Note(72, 0), Note(60, pianoroll.NOTE_COLOR), Note(74, 3)]

            noteCount = property(lambda self: len(self.notes))

            def getNote(self, i):
                return self.notes[i]

            def deleteNote(self, i):
                del self.notes[i]

            def addNote(self, note):
                self.notes.append(note)

        fake = types.ModuleType("flpianoroll")
        fake.Note, fake.score = Note, Score()
        sys.modules["flpianoroll"] = fake
        chords = pianoroll.tile([(60, 0, 16, 96), (63, 0, 16, 96), (67, 16, 16, 84)], 48, 32)
        self.assertEqual(len(chords), 5)                       # third bar gets half a copy
        self.assertEqual(max(s + n for _, s, n, _ in pianoroll.tile(chords, 10 ** 6, 32)),
                         pianoroll.MAX_STEPS)                  # a bogus length can't run away
        exec(compile(pianoroll.script_source(chords), "chords.pyscript", "exec"), {})
        kept = [n.number for n in fake.score.notes if n.color != pianoroll.NOTE_COLOR]
        ours = [(n.number, n.time, n.length) for n in fake.score.notes
                if n.color == pianoroll.NOTE_COLOR]
        self.assertEqual(kept, [72, 74])                       # the melody survives
        self.assertEqual(ours, [(60, 0, 384), (63, 0, 384), (67, 384, 384),
                                (60, 768, 384), (63, 768, 384)])
        exec(compile(pianoroll.script_source([]), "chords.pyscript", "exec"), {})
        self.assertEqual([n.number for n in fake.score.notes], [72, 74])

    def test_passing_diminished_chord(self):
        from seeker.generator import PASSING, add_passing, chord_name
        self.assertEqual(add_passing("1111555566664444"), "11115555666644" + PASSING * 2)
        self.assertEqual(add_passing("1166225511662253"), "116622551166225" + PASSING)
        prog = add_passing("1111555566664444")
        self.assertEqual(chord_name(PASSING, prog, 0, "major"), "Bdim")
        self.assertEqual(chord_name(PASSING, "6" + prog[1:], 0, "major"), "G#dim")
        self.assertEqual(chord_name(PASSING, prog, 0, "minor"), "Bdim")
        # keys: B D F (Ab with a seventh voicing); pad: B D F; 808: B under the C root
        tones = {n % 12 for n, s, _, _ in chord_notes("x---" * 16, prog, 0, "major", "seventh")
                 if s >= 56}
        self.assertEqual(tones, {11, 2, 5, 8})
        self.assertEqual({n % 12 for n, s, l, _ in pad_notes(prog, 0, "major") if s <= 56 < s + l},
                         {11, 2, 5})
        bass = bass_pitches(["1"] * 64, 0, "major", prog=prog)
        self.assertEqual(bass[0] - bass[63], 1)

    def test_auto_genre_follows_tempo(self):
        self.assertIn("trap", genres_for_tempo(140))
        self.assertNotIn("boombap", genres_for_tempo(140))
        self.assertIn("boombap", genres_for_tempo(90))
        self.assertEqual(len(genres_for_tempo(300)), 1)  # nearest, never empty


class Mapping(unittest.TestCase):
    def test_role_detection(self):
        cases = {"808 Kick": "kick", "808 Clap": "clap", "808 HiHat": "hat",
                 "808 Snare": "snare", "808 Astronomic": "bass", "Open Hat 2": "openhat",
                 "Sub Bass": "bass", "Bass Drum": "kick", "808 Cowbell": "perc",
                 "OH": "openhat", "BD_01": "kick", "Rimshot": "perc", "Tom Lo": "perc",
                 "Piano": "chords", "FL Keys": "chords", "Serum": None, "Synth": "pad", "Padilion": "pad", "Lead Pluck": None, "Warm Pad": "pad",
                 "Synth Bass": "bass", "Strings": "pad", "Cowbell": "perc",
                 "Bass (808)": "bass", "Closed hat": "hat"}
        for name, role in cases.items():
            self.assertEqual(detect_role(name), role, name)

    def test_snare_covers_for_missing_clap_and_back(self):
        lanes = {r: [0] * 4 for r in ROLES}
        lanes["snare"] = [0, 120, 56, 0]
        lanes["clap"] = [0, 0, 0, 100]
        # Instruments named after their preset are found by plugin, then by order.
        rack = [{"index": i, "name": n, "plugin": p} for i, (n, p) in enumerate([
            ("Kick", ""), ("Vox chop", ""), ("808", ""), ("default", "FL Keys"),
            ("Glassy", "Sytrus"), ("Third", "FLEX")])]
        roles = {r: ch["name"] for r, ch in map_rack(rack).items()}
        self.assertEqual(roles, {"kick": "Kick", "bass": "808", "chords": "default",
                                 "pad": "Glassy"})
        rack[3], rack[4] = dict(rack[4], index=3), dict(rack[3], index=4)   # synth first
        self.assertEqual(map_rack(rack)["chords"]["name"], "default")       # still FL Keys
        rack[4]["plugin"] = "Harmor"                                        # no keys plugin
        roles = {r: ch["name"] for r, ch in map_rack(rack).items()}
        self.assertEqual((roles["chords"], roles["pad"]), ("Glassy", "default"))
        named = map_rack(rack + [{"index": 6, "name": "Piano", "plugin": "Kontakt"}])
        self.assertEqual(named["chords"]["name"], "Piano")                  # a name still wins

        tracks, missing = build_tracks(lanes, map_rack([{"index": 0, "name": "Snare"}]))
        self.assertEqual(tracks[0]["bits"], [0, 1, 1, 1])
        self.assertEqual(missing, [])
        tracks, _ = build_tracks(lanes, map_rack([{"index": 0, "name": "Clap"}]))
        self.assertEqual(tracks[0]["bits"], [0, 1, 0, 1])  # ghost dropped


class FakeRack:
    """Stand-in for FL's channels/patterns modules."""

    def __init__(self, names):
        self.names = names
        self.grid = {}      # (pattern, channel, step) -> velocity
        self.pitch = {}     # (pattern, channel, step) -> note, when not the default 60
        self.pattern = 1
        self.length_beats = {}
        self.tempo = 140.0
        self.playing = False
        self.sent = []      # SysEx packets the script sent to its output port
        self.ui = []        # window calls the script made
        self.selected = 0
        self.roll = None    # channel the piano roll shows; None = hidden
        self.plugins = {}   # channel -> {"name", "params": [[name, value]], "preset": n}
        self.presets = ["Init", "Warm Pad", "Glass Keys", "Sub Bass", "Glass Bell"]
        self.hint = ""      # FL's hint bar
        self.props = {}     # channel -> {"color" / "volume" / "pan" / "editor": value}
        self.clips = []     # playlist: (track, pattern, start tick), in the order placed
        self.song_mode = False
        self.windows = {0: False, 1: True}      # mixer hidden, channel rack showing
        self.pattern_names = {}
        self.pattern_colors = {}
        self.inserts = {}       # channel -> mixer insert (missing = 0, the master)
        self.insert_names = {}  # insert -> name the user or the script gave it
        self.insert_colors = {}
        self.mixer_selected = 0
        self.fx = {}            # (insert, slot) -> {"name", "params": [[name, value]]}


class Event:
    def __init__(self, sysex):
        self.sysex = sysex
        self.handled = False


def load_script(rack):
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m

    def set_bit(ch, step, value):
        key = (rack.pattern, ch, step)
        if value:
            rack.grid[key] = 100
        else:
            rack.grid.pop(key, None)

    def set_vel(ch, pat, step, param, value):
        assert (pat, ch, step) in rack.grid, "parameter on an unlit step"
        (rack.grid if param == 1 else rack.pitch)[(pat, ch, step)] = value

    def get_param(ch, step, param):
        key = (rack.pattern, ch, step)
        return rack.grid[key] if param == 1 else rack.pitch.get(key, 60)

    def new_pattern(flags):
        rack.pattern = max([p for p, _, _ in rack.grid] + [rack.pattern]) + 1

    def pat_len(pat):
        last = max([s for p, _, s in rack.grid if p == pat] + [-1]) + 1
        # FL 2026 reports steps here, whatever the manual says about beats.
        return max(rack.length_beats.get(pat, 0) * 4, -(-last // 16) * 16)

    rack.pattern_steps = pat_len

    def song_length(mode):
        ends = [start + pat_len(p) * 24 for _, p, start in rack.clips]
        return max(ends) - 1 if ends else 0

    def prop(ch):
        return rack.props.setdefault(ch, {}).__setitem__

    def step_preset(by):
        def step(ch):       # like FL: wraps round, and the hint bar names the preset
            at = (rack.plugins[ch].get("preset", 0) + by) % len(rack.presets)
            rack.plugins[ch]["preset"] = at
            rack.plugins[ch].setdefault("steps", []).append(by)
            rack.hint = rack.presets[at]
        return step

    def set_param(value, i, ch):
        rack.plugins[ch]["params"][i][1] = value

    def target(ch, slot):
        """A channel's plugin, or (with a slot) the effect in a mixer insert's slot."""
        return rack.plugins[ch] if slot is None else rack.fx[(ch, slot)]

    def set_any(value, i, ch, slot=None):
        if slot is None:
            return set_param(value, i, ch)
        rack.fx[(ch, slot)]["params"][i][1] = value

    mod("plugins",
        isValid=lambda ch, slot=None: (ch in rack.plugins if slot is None
                                       else (ch, slot) in rack.fx),
        getPluginName=lambda ch, slot=None: target(ch, slot)["name"],
        getParamCount=lambda ch, slot=None: len(target(ch, slot)["params"]),
        getParamName=lambda i, ch, slot=None: target(ch, slot)["params"][i][0],
        getParamValue=lambda i, ch, slot=None: target(ch, slot)["params"][i][1],
        getParamValueString=lambda i, ch, slot=None: "%d%%" % round(
            target(ch, slot)["params"][i][1] * 100),
        setParamValue=set_any, nextPreset=step_preset(1), prevPreset=step_preset(-1),
        getPresetCount=lambda ch: len(rack.presets),
        getName=lambda ch, slot, flag, i: rack.presets[i])
    mod("channels", channelCount=lambda: len(rack.names),
        selectOneChannel=lambda i: setattr(rack, "selected", i),
        selectedChannel=lambda: rack.selected,
        getChannelName=lambda i: rack.names[i],
        getChannelType=lambda i: 2 if i in rack.plugins else 0,
        setChannelName=lambda i, n: rack.names.__setitem__(i, n),
        setChannelColor=lambda i, c: prop(i)("color", c),
        setChannelVolume=lambda i, v: prop(i)("volume", v),
        setChannelPan=lambda i, v: prop(i)("pan", v),
        getChannelColor=lambda i: rack.props.get(i, {}).get("color", 0x565148),
        getChannelVolume=lambda i: rack.props.get(i, {}).get("volume", 0.78125),
        getChannelPan=lambda i: rack.props.get(i, {}).get("pan", 0.0),
        showEditor=lambda i, v: prop(i)("editor", v),
        getGridBit=lambda ch, s: (rack.pattern, ch, s) in rack.grid,
        setGridBit=set_bit, setStepParameterByIndex=set_vel,
        getCurrentStepParam=get_param,
        getTargetFxTrack=lambda i: rack.inserts.get(i, 0),
        setTargetFxTrack=rack.inserts.__setitem__)
    mod("patterns", patternNumber=lambda: rack.pattern, getPatternLength=pat_len,
        getPatternName=lambda p: rack.pattern_names.get(p, "Pattern %d" % p),
        setPatternName=rack.pattern_names.__setitem__,
        setPatternColor=rack.pattern_colors.__setitem__,
        jumpToPattern=lambda p: setattr(rack, "pattern", p),
        findFirstNextEmptyPat=new_pattern)
    mod("playlist", trackCount=lambda: 500, getTrackName=lambda i: "Track %d" % i,
        selectTool=lambda i: setattr(rack, "tool", i))
    mod("mixer", getCurrentTempo=lambda: rack.tempo * 1000, trackCount=lambda: 127,
        getTrackName=lambda t: rack.insert_names.get(t, "Master" if t == 0 else "Insert %d" % t),
        setTrackName=rack.insert_names.__setitem__,
        setTrackColor=rack.insert_colors.__setitem__,
        trackNumber=lambda: rack.mixer_selected,
        setTrackNumber=lambda t: setattr(rack, "mixer_selected", t))
    mod("general", safeToEdit=lambda: True, saveUndo=lambda *a: None,
        getRecPPQ=lambda: 96, getRecPPB=lambda: 384,
        undoUp=lambda: rack.clips and rack.clips.pop(),
        processRECEvent=lambda ev, val, flags: setattr(rack, "tempo", val / 1000.0))
    mod("midi", pVelocity=1, pPitch=0, widPianoRoll=3, FFNEP_DontPromptName=1, REC_Tempo=5, REC_Control=1,
        REC_UpdateControl=2, UF_PR=2, widPlaylist=2, SONGLENGTH_ABSTICKS=2)
    mod("transport", isPlaying=lambda: rack.playing, getLoopMode=lambda: int(rack.song_mode),
        setLoopMode=lambda: setattr(rack, "song_mode", not rack.song_mode),
        getSongLength=song_length,
        start=lambda: setattr(rack, "playing", True))
    mod("device", isAssigned=lambda: True, midiOutSysex=rack.sent.append)
    def show(w):
        rack.ui.append(("show", w))
        if w == 3:
            rack.roll = rack.selected       # a hidden piano roll opens on the selection
        else:
            rack.windows[w] = True

    def hide(w):
        rack.ui.append(("hide", w))
        if w == 3:
            rack.roll = None
        else:
            rack.windows[w] = False

    def visible(w):
        return rack.roll is not None if w == 3 else rack.windows.get(w, w == 2)

    mod("ui", showWindow=show, hideWindow=hide, getVisible=visible,
        setSnapMode=lambda v: setattr(rack, "snap", v), getFocused=lambda w: False,
        setFocused=lambda w: rack.ui.append(("focus", w)), getHintMsg=lambda: rack.hint,
        setHintMsg=lambda text: setattr(rack, "hint", text))

    spec = importlib.util.spec_from_file_location(
        "ps_script", os.path.join(ROOT, "fl_script", "device_PatternSeeker.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


class Script(unittest.TestCase):
    def setUp(self):
        self.rack = FakeRack(["808 Kick", "808 Clap", "808 HiHat", "808 Snare",
                              "808 Astronomic", "Piano"])
        self.script = load_script(self.rack)
        self.script.OnInit()

    def received(self, kind):
        """Decode what the script sent, with the app's own decoder."""
        asm, found = wire.Assembler(), None
        for packet in self.rack.sent:
            self.assertLessEqual(len(packet), 1024)
            self.assertFalse([b for b in packet[1:-1] if b > 0x7F], "8-bit byte in SysEx")
            done = asm.feed(packet)
            if done and done[0] == kind:
                found = done[1]
        del self.rack.sent[:]
        return found

    def call(self, req):
        del self.rack.sent[:]
        for packet in wire.encode(wire.REQUEST, 9, dict(req, id="t")):
            event = Event(packet)
            self.script.OnSysEx(event)
            self.assertTrue(event.handled)
        res = self.received(wire.RESPONSE)
        self.assertEqual(res["id"], "t")
        return res

    def lit(self, ch, pattern=None):
        p = pattern or self.rack.pattern
        return sorted(s for pp, c, s in self.rack.grid if pp == p and c == ch)

    def beat_request(self, **extra):
        self.script._heartbeat()
        hb = self.received(wire.HEARTBEAT)
        beat = generate("trap", random.Random(7))
        pitches = {"bass": bass_pitches(beat.degrees, 9, "minor")}       # A minor
        tracks, _ = build_tracks(beat.lanes, map_rack(hb["channels"]), pitches)
        return beat, dict({"cmd": "apply", "tracks": tracks, "fill": True}, **extra)

    def test_beat_lands_on_the_right_channels_and_back_restores(self):
        self.rack.grid = {(1, 0, 0): 100, (1, 0, 40): 100,    # user's own kick
                          (1, 5, 3): 100}                     # unmapped channel
        beat, req = self.beat_request(autoPlay=True)
        res = self.call(req)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["warnings"], [])
        want = [i for i, v in enumerate(beat.lanes["kick"]) if v]
        # The old kick at step 40 made this a 3-bar pattern, so the beat tiles to 3 bars.
        self.assertEqual(self.lit(0), want + [s + 32 for s in want if s < 16])
        self.assertEqual(self.lit(5), [3])                    # melody untouched
        self.assertEqual(self.rack.grid[(1, 0, 0)], beat.lanes["kick"][0])
        self.assertTrue(self.rack.playing)

        res = self.call({"cmd": "apply", "tracks": res["prev"], "fill": False})
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.lit(0), [0, 40])
        self.assertEqual(self.lit(1), [])

    def test_fills_under_a_longer_melody(self):
        self.rack.length_beats[1] = 32                         # 8-bar piano roll
        _, req = self.beat_request()
        self.call(req)
        self.assertEqual(max(self.lit(0)) // 16, 7)

    def test_new_pattern_and_tempo(self):
        self.rack.grid = {(1, 0, 0): 100}
        _, req = self.beat_request(newPattern=True, tempo=92.0)
        res = self.call(req)
        self.assertEqual(res["pattern"], 2)
        self.assertEqual(self.lit(0, 1), [0])
        self.assertTrue(self.lit(0, 2))
        self.assertEqual(self.rack.tempo, 92.0)

    def test_long_request_and_reply_survive_chunking(self):
        self.rack.length_beats[1] = 128                        # 32 bars -> multi-packet
        _, req = self.beat_request()
        self.assertGreater(len(wire.encode(wire.REQUEST, 1, req)), 1)
        res = self.call(req)
        self.assertTrue(res["ok"], res)
        res = self.call({"cmd": "apply", "tracks": res["prev"], "fill": False})
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.rack.grid, {})

    def test_808_is_written_in_key_and_back_restores_the_old_notes(self):
        self.rack.grid = {(1, 4, 2): 90}                       # an existing 808 note...
        self.rack.pitch = {(1, 4, 2): 67}                      # ...on a G
        beat, req = self.beat_request()
        res = self.call(req)
        self.assertEqual(res["warnings"], [])
        want = bass_pitches(beat.degrees, 9, "minor")
        hits = [i for i, v in enumerate(beat.lanes["bass"]) if v]
        self.assertTrue(hits)
        self.assertEqual(self.lit(4), hits)
        self.assertEqual([self.rack.pitch[(1, 4, s)] for s in hits], [want[s] for s in hits])
        a_minor = {(57 + n) % 12 for n in SCALES["minor"]}
        self.assertTrue({want[s] % 12 for s in hits} <= a_minor)
        self.assertFalse(any("pitch" in t for t in res["prev"] if t["channel"] != 4))

        self.call({"cmd": "apply", "tracks": res["prev"], "fill": False})
        self.assertEqual(self.lit(4), [2])
        self.assertEqual(self.rack.pitch[(1, 4, 2)], 67)

    def test_808_off_leaves_the_bass_channel_alone(self):
        self.rack.grid = {(1, 4, 2): 90}
        beat, req = self.beat_request()
        lanes = {r: v for r, v in beat.lanes.items() if r != "bass"}
        req["tracks"], _ = build_tracks(lanes, map_rack(
            [{"index": i, "name": n} for i, n in enumerate(self.rack.names)]))
        self.call(req)
        self.assertEqual(self.lit(4), [2])

    def test_drums_last_as_long_as_the_four_bar_harmony(self):
        _, req = self.beat_request(minSteps=64)
        self.call(req)
        first = [s for s in self.lit(0) if s < 32]
        self.assertTrue(first)
        self.assertEqual(self.lit(0), first + [s + 32 for s in first])   # two bars, twice

    def test_aims_the_piano_roll_at_a_second_channel(self):
        _, req = self.beat_request(pianoRoll={"channel": 5, "name": "Piano"})
        self.call(req)
        name = self.rack.names[3]
        res = self.call({"cmd": "pianoRoll", "pianoRoll": {"channel": 3, "name": name}})
        self.assertEqual(res["pianoRoll"], "")
        self.assertEqual((self.rack.selected, self.rack.roll), (3, 3))
        self.call({"cmd": "closePianoRoll"})                   # back to before the FIRST open
        self.assertEqual((self.rack.selected, self.rack.roll), (0, None))

    def test_opens_the_piano_roll_of_the_keys_channel(self):
        _, req = self.beat_request(pianoRoll={"channel": 5, "name": "Piano"})
        res = self.call(req)
        self.assertEqual(res["pianoRoll"], "")
        self.assertEqual((self.rack.selected, self.rack.roll), (5, 5))
        self.assertEqual(self.rack.ui, [("show", 3), ("focus", 3)])
        self.assertEqual(self.lit(5), [])                      # its steps are never written
        self.call({"cmd": "closePianoRoll"})                   # back to how it was: hidden
        self.assertEqual((self.rack.selected, self.rack.roll), (0, None))

        # Open on a melody channel: it must be re-aimed, then handed back.
        self.rack.selected = self.rack.roll = 3
        _, req = self.beat_request(pianoRoll={"channel": 5, "name": "Piano"})
        self.call(req)
        self.assertEqual((self.rack.selected, self.rack.roll), (5, 5))
        self.call({"cmd": "closePianoRoll"})
        self.assertEqual((self.rack.selected, self.rack.roll), (3, 3))

        # FL reports a piano-roll script's edit through OnRefresh; we count those.
        before = self.call({"cmd": "edits"})["edits"]
        self.script.OnRefresh(0x20)                             # a focus change is not one
        self.script.OnRefresh(0x20000)
        self.assertEqual(self.call({"cmd": "edits"})["edits"], before + 1)

        _, req = self.beat_request(pianoRoll={"channel": 5, "name": "Something else"})
        self.assertEqual(self.call(req)["pianoRoll"], "rack_changed")

    def test_ignores_other_sysex(self):
        event = Event(b"\xF0\x7D\x01\x02\x03\x04\x05\x06\x07\xF7")
        self.script.OnSysEx(event)
        self.assertFalse(event.handled)

    def test_refuses_when_rack_was_reordered(self):
        _, req = self.beat_request()
        self.rack.names.insert(0, "Piano")
        res = self.call(req)
        self.assertEqual(res["error"], "rack_changed")
        self.assertEqual(self.rack.grid, {})


if __name__ == "__main__":
    unittest.main()
