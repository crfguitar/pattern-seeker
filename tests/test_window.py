"""The desktop window's words for what the engine did: songs, the ballad, the rack.
(The beat line is checked in test_engine.WindowText.)

    python -m unittest discover tests
"""

import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seeker.engine import SeekerError  # noqa: E402
from test_engine import SoundsFixture  # noqa: E402
from test_playlist import SongFixture  # noqa: E402


def window():
    spec = importlib.util.spec_from_file_location(
        "ps_window", os.path.join(ROOT, "pattern_seeker.pyw"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SongText(SongFixture):
    def test_a_song_lists_each_section_with_its_bars_and_chords(self):
        w = window()
        song = self.engine.new_song("trap", key="A", structure="ABAB", bars=8)
        lines = w.song_text(song).split("\n")
        self.assertIn("Trap", lines[0])
        self.assertIn("A minor", lines[0])
        self.assertIn("ABAB", lines[0])
        verse, chorus = (p["pattern"] for p in song["patterns"])
        self.assertTrue(lines[1].startswith("Verse  bars 1-8  ·  Pattern %d" % verse))
        self.assertTrue(lines[4].startswith("Chorus  bars 25-32  ·  Pattern %d" % chorus))
        self.assertIn(song["patterns"][0]["progression"][0]["chord"], lines[1])
        self.assertFalse(w.troubles(song))

    def test_placing_a_pattern_says_where_it_went(self):
        w = window()
        beat = self.engine.new_beat("trap", new_pattern=True, play=False)
        laid = self.engine.arrange([{"pattern": beat["pattern"], "bars": 8}], track=2)
        self.assertIn("Pattern %d  →  bars 1-8 on track 2  (2 clips)" % beat["pattern"],
                      w.arrange_text(laid))

    def test_a_ballad_lists_sections_chords_and_seed(self):
        w = window()
        self.roll.rack = self.rack
        self.rack.names[:] = ["Sampler", "Jazz Kick", "Jazz Snare", "Jazz Ride", "Jazz Rim",
                              "Upright Bass", "Rhodes"]
        song = self.engine.new_song("jazz ballad", key="Bb")
        text = w.song_text(song)                # new_song hands a ballad over
        self.assertIn("Jazz Ballad  ·  Bb major  ·  66 BPM  ·  seed %d" % song["seed"], text)
        self.assertIn("Intro  bars 1-4", text)
        self.assertIn("A3  bars 29-40", text)
        self.assertIn(" | ".join(song["sections"][0]["chords"]), text)


class RackText(SoundsFixture):
    def test_the_rack_tab_rows_and_its_actions(self):
        w = window()
        rows = w.rack_rows(self.engine.heartbeat()["channels"])
        self.assertEqual(rows[0], (0, "Kick", "kick", "master"))
        self.assertEqual(rows[4][2], "bass")
        done = self.engine.route_channels()
        self.assertIn("Kick  →  insert %d" % done["routed"][0]["insert"], w.route_text(done))
        self.assertIn("already", w.route_text(self.engine.route_channels()))
        made = self.engine.add_channel("909 Kick", "Perc")
        self.assertIn("Added Perc  (Drums/Kicks/909 Kick)", w.added_text(made))
        self.assertIn("perc part", w.added_text(made))

    def test_numbers_typed_into_the_window(self):
        w = window()
        self.assertIsNone(w.number("  ", "Tempo"))
        self.assertEqual(w.number("90", "Tempo"), 90.0)
        with self.assertRaisesRegex(SeekerError, "Bars must be a whole number"):
            w.number("8.5", "Bars", int)


if __name__ == "__main__":
    unittest.main()
