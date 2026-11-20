"""Songs: pattern clips clicked into a simulated playlist window, through the
engine and the real FL script.

    python -m unittest discover tests
"""

import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_engine import EngineFixture  # noqa: E402
from seeker import playlist  # noqa: E402
from seeker.engine import SeekerError  # noqa: E402

BAR = 384               # ticks
NONE, BAR_SNAP = 3, 14  # rows of the snap menu


class FakeScreen:
    """A playlist like the one in FL 2026 at 100%: toolbar, picker, track names,
    a grid of 60 pixels a bar and 70 a track, and the channel rack floating over
    the top rows. Hovering fills FL's hint bar the way FL does."""

    WINDOW = (0, 100, 1900, 1000)
    GRID_X, GRID_Y, NAMES_X = 340, 180, 200
    RACK = (183, 184, 1686, 342)
    MENU = (29, 131, 126, 536)
    TICKS_PER_PIXEL = BAR / 60.0
    scale = 1.0

    def __init__(self, rack):
        self.fl = rack
        self.snap = NONE
        self.snap_works = True
        self.scroll_x = 0       # ticks
        self.scroll_y = 0       # tracks
        self.menu_open = False
        self.moves = self.scrolls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def find(self):
        return True

    def forward(self):
        pass

    def rect(self):
        return self.WINDOW

    @staticmethod
    def _inside(box, x, y):
        return box[0] <= x < box[2] and box[1] <= y < box[3]

    def cover(self, x, y):
        if self.menu_open and self._inside(self.MENU, x, y):
            return -1
        if self.fl.windows.get(1) and self._inside(self.RACK, x, y):
            return 1
        if x >= 1880 or not self._inside(self.WINDOW, x, y):
            return -1           # the scroll bar is a window of its own
        return None

    def clear(self, x, y, toolbar=False):
        return self.cover(x, y) is None and (not toolbar or y < 130)

    def _tick(self, x):
        return self.scroll_x + (x - self.GRID_X) * self.TICKS_PER_PIXEL

    def _track(self, y):
        return (y - self.GRID_Y) // 70 + 1 + self.scroll_y

    @staticmethod
    def _time(tick):
        tick = int(tick)
        return "%d:%02d:%02d" % (tick // BAR + 1, tick % BAR // 96 + 1, tick % 96)

    def move(self, x, y):
        self.moves += 1
        if self.cover(x, y) is not None:
            self.fl.hint = "Channel rack"
        elif y < self.GRID_Y:
            self.fl.hint = "Snap to grid" if y < 130 else ""
        elif x >= self.GRID_X:
            self.fl.hint = self._time(self._tick(x))
        elif x >= 330:
            self.fl.hint = "Mute / solo"
        elif x >= self.NAMES_X:
            self.fl.hint = "Track %d" % self._track(y)
        else:
            self.fl.hint = "Pattern %d" % self.fl.pattern

    def click(self, x, y):
        self.move(x, y)
        if self.menu_open:
            self.menu_open = False
            if self._inside(self.MENU, x, y) and self.snap_works:
                top, bottom = self.MENU[1], self.MENU[3]
                rows = [top + (bottom - top) * f for f in playlist.SNAP_ROWS]
                self.snap = min(range(len(rows)), key=lambda i: abs(rows[i] - y))
        elif y < 130 and abs(x - 34) < 10:
            self.menu_open = True
        elif x >= self.GRID_X and y >= self.GRID_Y and self.cover(x, y) is None:
            tick = self._tick(x)
            start = int(round(tick / BAR)) * BAR if self.snap == BAR_SNAP else int(tick)
            length = self.fl.pattern_steps(self.fl.pattern) * 24
            track = self._track(y)
            if any(t == track and s <= tick < s + self.fl.pattern_steps(p) * 24
                   for t, p, s in self.fl.clips):
                return          # a click on a clip picks it up: nothing new
            self.fl.clips.append((track, self.fl.pattern, start))
            self.fl.hint = "%s for %s" % (self._time(start), self._time(length - BAR))

    def wheel(self, notches, shift=False):
        self.scrolls += 1
        if shift:
            self.scroll_x = max(0, self.scroll_x - notches * 2 * BAR)
        else:
            self.scroll_y = max(0, self.scroll_y - notches)

    def key(self, vk):
        if vk == playlist.VK_ESCAPE:
            self.menu_open = False

    def menu(self):
        return self.MENU if self.menu_open else None

    def brightness(self, x, y):
        top, bottom = self.MENU[1], self.MENU[3]
        rows = [top + int((bottom - top) * f) for f in playlist.SNAP_ROWS]
        return 60 if rows[self.snap] == y else 200


class SongFixture(EngineFixture):
    def setUp(self):
        super().setUp()
        self.screen = FakeScreen(self.rack)
        self.saved_screen, playlist.Screen = playlist.Screen, lambda: self.screen
        self.saved_sleep, time.sleep = time.sleep, lambda seconds: None

    def tearDown(self):
        playlist.Screen, time.sleep = self.saved_screen, self.saved_sleep
        super().tearDown()

    def two_patterns(self):
        first = self.engine.new_beat("trap", new_pattern=True, play=False)["pattern"]
        second = self.engine.new_beat("trap", new_pattern=True, play=False)["pattern"]
        return first, second


class ArrangeTest(SongFixture):
    def test_clips_land_on_their_bars_and_everything_is_put_back(self):
        a, b = self.two_patterns()
        out = self.engine.arrange([{"pattern": a, "bars": 8}, b], track=2)
        # four-bar patterns: the first twice to fill eight bars, then the second
        self.assertEqual(self.rack.clips, [(2, a, 0), (2, a, 4 * BAR), (2, b, 8 * BAR)])
        self.assertEqual((out["startBar"], out["endBar"], out["clips"]), (1, 12, 3))
        self.assertEqual([s["bar"] for s in out["sections"]], [1, 9])
        self.assertEqual(self.screen.snap, NONE)        # the user's snap, as it was
        self.assertIn(("hide", 1), self.rack.ui)        # track 2 lay under the channel rack
        self.assertTrue(self.rack.windows[1])           # ...which is showing again
        self.assertTrue(self.rack.song_mode and out["songMode"])
        self.assertEqual(out["warnings"], [])

    def test_the_next_call_continues_where_the_song_ends(self):
        a, b = self.two_patterns()
        self.engine.arrange([a], track=5)
        out = self.engine.arrange([b], track=5, song_mode=False)
        self.assertEqual(out["startBar"], 5)
        self.assertEqual(self.rack.clips, [(5, a, 0), (5, b, 4 * BAR)])

    def test_far_bars_and_far_tracks_are_scrolled_to(self):
        a, _ = self.two_patterns()
        self.engine.arrange([a], track=40, start_bar=101)
        self.assertEqual(self.rack.clips, [(40, a, 100 * BAR)])
        self.assertGreater(self.screen.scrolls, 1)

    def test_a_snap_that_is_already_bar_is_left_alone(self):
        a, _ = self.two_patterns()
        self.screen.snap = BAR_SNAP
        self.engine.arrange([a], track=6)
        self.assertEqual(self.screen.snap, BAR_SNAP)
        self.assertFalse(self.screen.menu_open)

    def test_back_takes_the_clips_out_again(self):
        a, b = self.two_patterns()
        self.engine.arrange([a], track=5)
        self.engine.arrange([b, b], track=5)
        out = self.engine.back()
        self.assertEqual(out["removedClips"], 2)
        self.assertEqual(out["problems"], [])
        self.assertEqual(self.rack.clips, [(5, a, 0)])

    def test_a_clip_that_lands_off_the_bar_is_undone(self):
        a, _ = self.two_patterns()
        self.screen.snap_works = False          # the menu click doesn't take
        with self.assertRaises(SeekerError) as caught:
            self.engine.arrange([a, a], track=5, start_bar=3)
        self.assertIn("0 of 2", str(caught.exception))
        self.assertEqual(self.rack.clips, [])

    def test_a_spot_that_is_taken_is_reported(self):
        a, b = self.two_patterns()
        self.engine.arrange([a], track=5, start_bar=1)
        with self.assertRaises(SeekerError) as caught:
            self.engine.arrange([b], track=5, start_bar=1)
        self.assertIn("already a clip", str(caught.exception))
        self.assertEqual(len(self.rack.clips), 1)

    def test_bad_input_is_explained(self):
        for sections, kwargs in (([], {}), (["x"], {}), ([1], {"track": 0}),
                                 ([1], {"start_bar": 0}), ([{"pattern": 1, "bars": -2}], {})):
            with self.assertRaises(SeekerError):
                self.engine.arrange(sections, **kwargs)
        self.assertEqual(self.rack.clips, [])


class SongTest(SongFixture):
    def test_a_song_is_a_pattern_per_section_laid_out_in_order(self):
        out = self.engine.new_song("trap", key="A", scale="minor", structure="ABABCB", bars=8)
        verse, chorus, bridge = (p["pattern"] for p in out["patterns"])
        self.assertEqual([p["section"] for p in out["patterns"]], ["Verse", "Chorus", "Bridge"])
        self.assertEqual(len({verse, chorus, bridge}), 3)
        order = [verse, chorus, verse, chorus, bridge, chorus]
        self.assertEqual(self.rack.clips,
                         [(1, p, (i * 8 + half * 4) * BAR)
                          for i, p in enumerate(order) for half in (0, 1)])
        self.assertEqual(out["arrangement"]["endBar"], 48)
        self.assertEqual([s["section"] for s in out["arrangement"]["sections"]],
                         ["Verse", "Chorus", "Verse", "Chorus", "Bridge", "Chorus"])
        self.assertTrue(self.rack.pattern_names[verse].startswith("Verse - "))
        self.assertEqual(len(set(self.rack.pattern_colors.values())), 3)
        written = {p["section"]: p["written"] for p in out["patterns"]}
        self.assertNotIn("pad", written["Verse"])       # the verse sits lower
        self.assertIn("pad", written["Chorus"])
        self.assertNotIn("kick", written["Bridge"])     # the bridge is a breakdown
        self.assertIn("chords", written["Bridge"])
        self.assertFalse([s for p, c, s in self.rack.grid if p == bridge and c == 0])
        self.assertTrue([s for p, c, s in self.rack.grid if p == chorus and c == 0])
        self.assertFalse(self.rack.playing)

    def test_other_structures_and_lengths(self):
        out = self.engine.new_song("house", structure="aaba", bars=4, start_bar=5, track=3)
        a, b = (p["pattern"] for p in out["patterns"])
        self.assertEqual(self.rack.clips, [(3, a, 4 * BAR), (3, a, 8 * BAR), (3, b, 12 * BAR),
                                           (3, a, 16 * BAR)])
        self.assertEqual(out["structure"], "AABA")

    def test_bad_input_is_explained(self):
        for kwargs in ({"structure": "123"}, {"bars": 0}, {"bars": "x"},
                       {"structure": "ABCDEFGHI"}):
            with self.assertRaises(SeekerError):
                self.engine.new_song("trap", **kwargs)
        self.assertEqual(self.rack.clips, [])


class HelpersTest(unittest.TestCase):
    def test_the_ticked_menu_row_is_the_one_unlike_the_rest(self):
        self.assertEqual(playlist._odd_one_out([200] * 6 + [70] + [203] * 10), 6)
        self.assertIsNone(playlist._odd_one_out([200] * 17))
        self.assertIsNone(playlist._odd_one_out([200, 60, 60] + [200] * 14))


if __name__ == "__main__":
    unittest.main()
