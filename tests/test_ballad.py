"""The Jazz Ballad: the composer on its own, and a whole ballad laid out in a
simulated FL (the real FL script, a fake piano roll and playlist window).

    python -m unittest discover tests
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seeker import ballad  # noqa: E402
from seeker.engine import SeekerError  # noqa: E402
from test_playlist import BAR, SongFixture  # noqa: E402

FORM = [("Intro", 4), ("A1", 8), ("A2", 8), ("B", 8), ("A3", 12)]


class ComposerTest(unittest.TestCase):
    def test_every_key_and_many_seeds_give_playable_parts(self):
        for seed in range(12):
            for key in range(12):
                song = ballad.compose(key, seed)
                self.assertEqual([(s["name"], s["bars"]) for s in song["sections"]], FORM)
                for sec in song["sections"]:
                    beats = sec["bars"] * 4
                    for part, notes in sec["parts"].items():
                        for p, s, l, v in notes:
                            self.assertTrue(0 <= s < beats and 0 < l and s + l <= beats + 0.01,
                                            (seed, key, sec["name"], part, s, l))
                            self.assertTrue(1 <= v <= 127)
                            if part == "bass":
                                self.assertTrue(28 <= p <= 48, p)   # never above FL's C4
                        by_pitch = {}
                        for p, s, l, v in notes:
                            by_pitch.setdefault(p, []).append((s, s + l))
                        for p, spans in by_pitch.items():     # FL merges same-pitch overlaps
                            spans.sort()
                            for (_, end), (start, _) in zip(spans, spans[1:]):
                                self.assertGreaterEqual(start, end - 1e-6,
                                                        (seed, key, sec["name"], part, p))

    def test_the_same_seed_gives_the_same_ballad(self):
        self.assertEqual(ballad.compose(3, 42), ballad.compose(3, 42))
        self.assertNotEqual(ballad.compose(3, 42), ballad.compose(3, 43))

    def test_the_form_holds_together(self):
        song = ballad.compose(3, 7)                     # Eb
        intro, a1, a2, b, a3 = song["sections"]
        self.assertNotIn("ride", intro["parts"])        # the intro is Rhodes and bass
        self.assertEqual(a1["chords"][:7], a2["chords"][:7])
        self.assertEqual(a1["chords"][:7], a3["chords"][:7])
        self.assertTrue(a3["chords"][-1].endswith("maj9#11"))      # the held last chord
        theme = [n for n in a1["parts"]["keys"] if n[0] >= 63 and n[1] < 24]
        again = [n for n in a3["parts"]["keys"] if n[0] >= 63 and n[1] < 24]
        self.assertEqual([n[:2] for n in theme], [n[:2] for n in again])  # the head returns
        # the bridge walks: a bass note on every beat
        self.assertEqual(sorted({n[1] for n in b["parts"]["bass"]}), [float(i) for i in range(32)])
        # a ii followed by its V mid-bar: the V is pushed a swung eighth early
        starts = {round(n[1], 2) for n in a1["parts"]["keys"] if n[0] < 63}
        self.assertTrue(any(round(s % 1, 2) == 0.67 for s in starts))

    def test_voicings_move_smoothly(self):
        prev = None
        for degree, quality in [(0, "maj9"), (9, "m11"), (2, "m9"), (7, "13"), (4, "m9"),
                                (9, "7alt"), (5, "maj9"), (10, "9#11")]:
            notes = ballad.voice(3, degree, quality, prev)
            self.assertTrue(ballad.COMP_LOW <= notes[0] and notes[-1] <= ballad.COMP_HIGH)
            if prev:
                self.assertLessEqual(sum(abs(a - b) for a, b in zip(notes, prev)), 12)
            prev = notes


class BalladSongTest(SongFixture):
    def setUp(self):
        super().setUp()
        self.roll.rack = self.rack
        self.rack.names[:] = ["Sampler", "Jazz Kick", "Jazz Snare", "Jazz Ride", "Jazz Rim",
                              "Upright Bass", "Rhodes"]

    def test_a_ballad_is_five_patterns_laid_out_in_order(self):
        out = self.engine.new_ballad("Bb", tempo=62, seed=5)
        self.assertEqual(out["key"], "Bb major")
        self.assertEqual([(s["section"], s["bars"]) for s in out["sections"]], FORM)
        pats = [s["pattern"] for s in out["sections"]]
        self.assertEqual(len(set(pats)), 5)
        starts = [0, 4, 12, 20, 28]
        self.assertEqual(sorted((p, start) for _, p, start in self.rack.clips),
                         sorted((p, b * BAR) for p, b in zip(pats, starts)))
        self.assertEqual(out["arrangement"]["endBar"], 40)
        self.assertEqual(self.rack.tempo, 62)
        self.assertTrue(self.rack.pattern_names[pats[3]].startswith("B - Jazz Ballad"))
        self.assertEqual(out["written"]["keys"], "Rhodes")
        self.assertEqual(out["written"]["ride"], "Jazz Ride")
        self.assertEqual(out["problems"], [])

    def test_new_song_with_jazz_ballad_comes_here(self):
        out = self.engine.new_song("Jazz Ballad", key="F", scale="major")
        self.assertEqual(out["genre"], "Jazz Ballad")
        self.assertEqual(out["key"], "F major")

    def test_a_rack_without_jazz_sounds_is_told_to_build(self):
        self.rack.names[:] = ["808 Kick", "808 Bass", "Pad"]
        with self.assertRaisesRegex(SeekerError, "build=true"):
            self.engine.new_ballad("Eb")
        with self.assertRaises(SeekerError):
            self.engine.new_ballad("Eb", tempo=140)


if __name__ == "__main__":
    unittest.main()
