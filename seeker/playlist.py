"""Pattern clips go into the playlist by mouse: FL has no script call for it.

What makes that safe to do blind is FL's hint bar, which the controller script
reads back for us (`ask`, the engine's "song" request):

  * over the playlist grid it shows the time under the mouse ("6:04:90" = bar 6,
    beat 4, tick 90), so two hovers give the zoom and the scroll position;
  * over a track's header it shows the track's name, which finds the row;
  * after a click with the draw tool it shows where the clip landed
    ("12:01:00 for 4:00:00"), so every clip is checked, and undone when wrong.

Clips only land exactly on a bar when the playlist's own snap is "Bar". That
setting lives in the playlist's magnet menu and nowhere in the script API, so
it is set there for the duration and put back afterwards.

`Arranger` holds the method and talks to a `Screen`; the tests give it a
simulated playlist instead.
"""

import ctypes
import re
import time
from ctypes import wintypes

from . import pianoroll

PLAYLIST_CLASS = "TEventEditForm"
PLAYLIST_TITLE = "Playlist"
TOOL_DRAW = 0
COVERS = (0, 1, 3)      # FL's window numbers: mixer, channel rack, piano roll
WINDOW_CLASSES = {"TFXForm": 0, "TStepSeqForm": 1}
SNAP_ICON = (34, 12)    # the magnet, from the window's corner, at 100% scaling
# The magnet menu's rows, as fractions of its height (measured in FL 2026).
SNAP_NAMES = ["Main", "Line", "Cell", "(none)", "1/6 step", "1/4 step", "1/3 step",
              "1/2 step", "Step", "1/6 beat", "1/4 beat", "1/3 beat", "1/2 beat", "Beat",
              "Bar", "Events", "Markers"]
SNAP_ROWS = [y / 405.0 for y in (12, 43, 65, 96, 118, 140, 162, 184, 206, 228, 250, 272,
                                 294, 316, 338, 369, 391)]
SNAP_BAR = SNAP_NAMES.index("Bar")
SNAP_SHAPE = (3.4, 5.0)     # the menu is about 4.2 times as tall as it is wide
MARK = "Pattern Seeker..."  # put in the hint bar before a hover: never read a stale hint
MIN_BAR_PIXELS = 5          # zoomed out further than this, a click can't pick a bar
RIGHT_MARGIN = 0.1          # keep this much of the view right of a bar we click in
VK_ESCAPE, VK_SHIFT = 0x1B, 0x10

_TIME = re.compile(r"^(\d+):(\d+):(\d+)$")
_LANDED = re.compile(r"^(\d+):(\d+):(\d+) for ")


class PlaylistError(Exception):
    """Could not place the clips; `placed` holds the ones that did go in."""

    def __init__(self, message, placed=None):
        Exception.__init__(self, message)
        self.placed = placed or []


class Arranger:
    def __init__(self, screen, ask, sleep=time.sleep):
        self.screen, self.ask, self.sleep = screen, ask, sleep
        self.hidden = []        # FL windows we hid because they covered the playlist
        self.warnings = []
        self.tpb = self.ppq = 0

    # ---- reading the hint bar ----------------------------------------------
    def hint_at(self, x, y):
        """FL's hint for the point, "" when it gives none, None when another
        window covers the playlist there."""
        if not self.screen.clear(x, y) and not self.uncover(x, y):
            return None
        self.ask(hint=MARK)
        self.screen.move(x, y)
        deadline = time.time() + 0.6
        while True:
            hint = self.ask().get("hint", "")
            if hint != MARK:
                return hint
            if time.time() > deadline:
                return ""
            self.sleep(0.02)

    def ticks(self, hint):
        m = _TIME.match(hint or "")
        if not m:
            return None
        bar, beat, tick = (int(g) for g in m.groups())
        return (bar - 1) * self.tpb + (beat - 1) * self.ppq + tick

    def uncover(self, x, y):
        """Hide the FL window lying over the playlist at this point (the channel
        rack, the mixer, the piano roll: they come back afterwards). True when
        the point is clear now."""
        for _ in range(3):
            window = self.screen.cover(x, y)
            if window is None:
                return True
            if window not in COVERS or window in self.hidden:
                return False
            self.hidden.append(window)
            self.ask(hide=[window])
            self.sleep(0.3)
        return self.screen.clear(x, y)

    # ---- where things are -----------------------------------------------------
    def find_grid(self):
        """Two points of the grid, far apart, with their times: that is the zoom
        and the scroll. Then the column left of it where the track names are."""
        left, top, right, bottom = self.screen.rect()
        width, height = right - left, bottom - top
        for again in (True, False):
            for fy in (0.6, 0.8, 0.45, 0.9, 0.3):
                y = top + int(height * fy)
                hits = []
                for i in range(19, 0, -1):
                    x = left + width * i // 20
                    t = self.ticks(self.hint_at(x, y))
                    if t is not None:
                        hits.append((x, t))
                    elif hits:
                        break
                if len(hits) >= 2 and hits[0][1] > hits[-1][1]:
                    break
            else:
                if again and any([self.uncover(left + int(width * fx), top + int(height * 0.6))
                                  for fx in (0.9, 0.5)]):
                    continue
                raise PlaylistError("Couldn't read the playlist: its grid has to be visible "
                                    "in FL, without a window or a dialog over it.")
            break
        (self.x_right, self.t_right), (self.x_left, self.t_left) = hits[0], hits[-1]
        self.y_probe = y
        step = max(4, int(20 * self.screen.scale))
        x, self.x_names = self.x_left, None
        while x - step > left:
            x -= step
            hint = self.hint_at(x, y)
            t = self.ticks(hint)
            if t is not None:
                self.x_left, self.t_left = x, t
            elif hint in self.index:
                self.x_names = x
                break
        if self.x_names is None:
            raise PlaylistError("Couldn't find the playlist's track names (the column left "
                                "of the grid).")
        fine = max(2, int(3 * self.screen.scale))       # now the grid's very edge
        for x in range(self.x_left - fine, self.x_left - step, -fine):
            t = self.ticks(self.hint_at(x, y))
            if t is None:
                break
            self.x_left, self.t_left = x, t

    def remeasure(self):
        """The same two points again, after a scroll."""
        t_left = self.ticks(self.hint_at(self.x_left, self.y_probe))
        t_right = self.ticks(self.hint_at(self.x_right, self.y_probe))
        if t_left is None or t_right is None or t_right <= t_left:
            raise PlaylistError("Lost sight of the playlist grid while scrolling.")
        self.t_left, self.t_right = t_left, t_right

    @property
    def ticks_per_pixel(self):
        return (self.t_right - self.t_left) / float(self.x_right - self.x_left)

    def x_of(self, tick):
        return int(round(self.x_left + (tick - self.t_left) / self.ticks_per_pixel))

    def find_row(self, track):
        """The y of the middle of `track`'s row, scrolling it into view if needed."""
        left, top, right, bottom = self.screen.rect()
        scale = self.screen.scale
        step = max(4, int(16 * scale))
        tried = []
        for _ in range(16):
            seen, mine, covered = [], [], None
            for y in range(top + int(40 * scale), bottom - int(6 * scale), step):
                hint = self.hint_at(self.x_names, y)
                if hint is None:
                    covered = y
                at = self.index.get(hint)
                if at is None:
                    continue
                seen.append((y, at))
                if at == track:
                    mine.append(y)
                elif at > track:
                    break               # tracks run downwards: it is not further on
            if mine:
                return (mine[0] + mine[-1]) // 2
            if covered and covered not in tried:    # it may be under the channel rack
                tried.append(covered)
                self.uncover(self.x_names, covered)
                continue
            if not seen:
                raise PlaylistError("Couldn't read the playlist's track names.")
            first = min(at for _, at in seen)
            last = max(at for _, at in seen)
            # one notch of the wheel is about one track; never overshoot the far end
            notches = (first - track) if track < first else -max(1, (track - last + 1) // 2)
            self.screen.move(self.x_names, seen[0][0])
            self.screen.wheel(max(-12, min(12, notches)))
            self.sleep(0.2)
        raise PlaylistError("Couldn't scroll the playlist to track %d." % track)

    def bring(self, tick, center=False):
        """Scroll sideways until bar start `tick` can be clicked; returns the x
        to click. Bar snap rounds to the nearest bar, so anywhere in the bar's
        first 40% will do (bar 1 has nothing to its left). The whole bar has to
        be in view, clear of the right edge: a click near the edge makes FL
        scroll the playlist under the mouse, and the clip lands elsewhere."""
        per_notch = 0
        for i in range(40):
            margin = max(self.tpb, (self.t_right - self.t_left) * RIGHT_MARGIN)
            near_left = tick - self.t_left < (self.t_right - self.t_left) * 0.5
            if (self.t_left <= tick + self.tpb * 0.4 and tick + margin <= self.t_right
                    and (not center or near_left or tick < self.tpb)):
                return max(self.x_left, self.x_of(tick + self.tpb * 0.25))
            if self.tpb / self.ticks_per_pixel < MIN_BAR_PIXELS:
                raise PlaylistError("The playlist is zoomed out too far to pick a bar - "
                                    "zoom in (Ctrl + mouse wheel) and try again.")
            # aim to have it a third of the way in from the left
            aim = self.t_left + (self.t_right - self.t_left) * 0.33
            notches = round((tick - aim) / per_notch) if per_notch else (1 if tick > aim else -1)
            notches = max(-60, min(60, notches)) or (1 if tick > aim else -1)
            before = self.t_left
            self.screen.move(self.x_left, self.y_probe)
            self.screen.wheel(-notches, shift=True)     # wheel down = later bars
            self.sleep(0.2)
            self.remeasure()
            moved = (self.t_left - before) / float(notches)
            if moved > 0:
                per_notch = moved
            elif self.t_left == before and (notches > 0 or before > 0):
                break
        raise PlaylistError("Couldn't scroll the playlist to bar %d." % (tick // self.tpb + 1))

    # ---- the playlist's own snap --------------------------------------------------
    def set_snap(self, want):
        """Pick row `want` of the magnet menu. Returns the row that was set
        before, or None when that couldn't be told."""
        left, top, _, _ = self.screen.rect()
        scale = self.screen.scale
        x, y = left + int(SNAP_ICON[0] * scale), top + int(SNAP_ICON[1] * scale)
        if not self.screen.clear(x, y, toolbar=True):
            raise PlaylistError("A window covers the playlist's toolbar.")
        self.screen.click(x, y)
        menu = self.screen.menu()
        if not menu:
            raise PlaylistError("The playlist's snap menu didn't open.")
        m_left, m_top, m_right, m_bottom = menu
        shape = (m_bottom - m_top) / float(max(1, m_right - m_left))
        if not SNAP_SHAPE[0] <= shape <= SNAP_SHAPE[1]:
            self.screen.key(VK_ESCAPE)
            raise PlaylistError("FL opened a different menu than the playlist's snap menu "
                                "- closed it. Has the playlist toolbar changed?")
        rows = [m_top + int((m_bottom - m_top) * f) for f in SNAP_ROWS]
        probe = m_left + int((m_right - m_left) * 0.85)     # right of every label
        was = _odd_one_out([self.screen.brightness(probe, row) for row in rows])
        if was == want:
            self.screen.key(VK_ESCAPE)
        else:
            self.screen.click((m_left + m_right) // 2, rows[want])
        self.sleep(0.15)
        return was

    # ---- placing --------------------------------------------------------------------
    def run(self, clips, track=1):
        """clips: [(pattern number, bar it starts on, counted from 1)], all on
        `track`. Returns {"placed": [...], "warnings": [...]}."""
        placed = []
        if not self.screen.find():
            raise PlaylistError("FL Studio's playlist isn't open (press F5 in FL).")
        self.screen.forward()
        info = self.ask(focus=True, tool=TOOL_DRAW, tracks=500)
        if not self.screen.find():
            raise PlaylistError("FL Studio's playlist isn't open (press F5 in FL).")
        self.tpb, self.ppq = int(info["ticksPerBar"]), int(info["ppq"])
        names = info.get("tracks") or []
        if not 1 <= track <= len(names):
            raise PlaylistError("The playlist has tracks 1 to %d." % len(names))
        self.index = {}
        for i, name in enumerate(names):
            self.index.setdefault(name, i + 1)
        self.sleep(0.2)
        snap_was = False        # False = never changed
        try:
            self.find_grid()
            y = self.find_row(track)
            snap_was = self.set_snap(SNAP_BAR)
            self.remeasure()
            for pattern, bar in clips:
                start = (bar - 1) * self.tpb
                self.ask(pattern=pattern)
                for attempt in (0, 1):
                    # a second try scrolls the bar to the left of the view first
                    x = self.bring(start, center=attempt > 0)
                    if not self.uncover(x, y):
                        raise PlaylistError("A window covers track %d of the playlist."
                                            % track)
                    under = self.ticks(self.hint_at(x, y))
                    if under is None or not start <= under < start + self.tpb * 0.45:
                        raise PlaylistError("Lost track of where bar %d is in the playlist."
                                            % bar)
                    self.screen.click(x, y)
                    landed = self.landed()
                    if landed is None:
                        raise PlaylistError("FL didn't confirm the clip at bar %d - is there "
                                            "already a clip on track %d there?" % (bar, track))
                    if landed == start:
                        break
                    self.ask(undo=1)
                    self.sleep(0.2)
                    self.remeasure()
                    if attempt:
                        raise PlaylistError(
                            "A clip meant for bar %d landed at bar %s instead; it was "
                            "undone. (Clicked x=%d; the view showed bars %.1f to %.1f.)"
                            % (bar, landed // self.tpb + 1, x, self.t_left / float(self.tpb) + 1,
                               self.t_right / float(self.tpb) + 1))
                    self.warnings.append("The clip for bar %d first landed on bar %d; it "
                                         "was undone and placed again."
                                         % (bar, landed // self.tpb + 1))
                placed.append((pattern, bar))
        except PlaylistError as e:
            e.placed = placed
            raise
        finally:
            self.restore(snap_was)
        return {"placed": placed, "warnings": self.warnings}

    def landed(self):
        """The tick FL says the clip just placed starts on, or None."""
        deadline = time.time() + 1.0
        while True:
            m = _LANDED.match(self.ask().get("hint", ""))
            if m:
                bar, beat, tick = (int(g) for g in m.groups())
                return (bar - 1) * self.tpb + (beat - 1) * self.ppq + tick
            if time.time() > deadline:
                return None
            self.sleep(0.03)

    def restore(self, snap_was):
        try:
            if snap_was is None:
                self.warnings.append("The playlist's snap is now Bar (couldn't tell what "
                                     "it was before).")
            elif snap_was is not False and snap_was != SNAP_BAR:
                self.set_snap(snap_was)
        except PlaylistError:
            self.warnings.append("The playlist's snap was left on Bar (it was %s)."
                                 % SNAP_NAMES[snap_was])
        finally:
            if self.hidden:
                self.ask(show=self.hidden)


def _odd_one_out(values):
    """Index of the one value far from the rest (the menu row that is ticked)."""
    middle = sorted(values)[len(values) // 2]
    far = [i for i, v in enumerate(values) if abs(v - middle) > 18]
    return far[0] if len(far) == 1 else None


def place_clips(ask, clips, track=1):
    """Put pattern clips on a playlist track of the FL Studio that is running."""
    with Screen() as screen:
        return Arranger(screen, ask).run(clips, track)


# ---- the real screen ------------------------------------------------------------------

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_user32.GetDC.restype = wintypes.HDC
_user32.GetParent.restype = wintypes.HWND
_user32.GetParent.argtypes = [wintypes.HWND]
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.GetPixel.restype = wintypes.DWORD


class Screen:
    """Mouse, keys and pixels, in real pixels, and only ever while FL Studio is
    the program in front."""

    def __enter__(self):
        self.context = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        self.cursor = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(self.cursor))
        self.front_before = _user32.GetForegroundWindow()
        self.hwnd = self.main = None
        self.scale = 1.0
        return self

    def __exit__(self, *exc):
        _user32.SetCursorPos(self.cursor.x, self.cursor.y)
        if self.front_before and self.front_before != _user32.GetForegroundWindow():
            _user32.SetForegroundWindow(self.front_before)
        _user32.SetThreadDpiAwarenessContext(self.context)

    def find(self):
        """Locate the playlist: a window inside FL's main one, or one on its own."""
        mains = pianoroll._windows(pianoroll.MAIN_CLASS)
        if not mains:
            return False
        self.main = mains[0]
        found = pianoroll._windows(PLAYLIST_CLASS, PLAYLIST_TITLE)

        def visit(hwnd, _):
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == PLAYLIST_CLASS and _user32.IsWindowVisible(hwnd):
                _user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value.startswith(PLAYLIST_TITLE):
                    found.append(hwnd)
            return True

        _user32.EnumChildWindows(self.main, pianoroll._EnumProc(visit), 0)
        self.hwnd = found[0] if found else None
        if self.hwnd:
            self.scale = (_user32.GetDpiForWindow(self.hwnd) or 96) / 96.0
        return bool(self.hwnd)

    def forward(self):
        if _user32.IsIconic(self.main):
            _user32.ShowWindow(self.main, 9)        # restore a minimised FL
            time.sleep(0.6)
        top = _user32.GetAncestor(self.hwnd, 2) or self.main
        deadline = time.time() + 1.5
        while not pianoroll.bring_forward(top):     # Windows takes a moment to hand over
            if time.time() > deadline:
                raise PlaylistError("Couldn't bring FL Studio to the front.")
            time.sleep(0.15)
        time.sleep(0.2)

    def _fl_in_front(self):
        mine, theirs = wintypes.DWORD(), wintypes.DWORD()
        _user32.GetWindowThreadProcessId(self.main, ctypes.byref(mine))
        _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), ctypes.byref(theirs))
        if mine.value != theirs.value:
            raise PlaylistError("FL Studio lost the keyboard and mouse to another program - "
                                "stopped.")

    def rect(self):
        r = wintypes.RECT()
        _user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    def _at(self, x, y):
        """(class, title) of the window at the point and of each one above it."""
        hwnd = _user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        buf = ctypes.create_unicode_buffer(256)
        while hwnd:
            _user32.GetClassNameW(hwnd, buf, 256)
            name = buf.value
            _user32.GetWindowTextW(hwnd, buf, 256)
            yield hwnd, name, buf.value
            hwnd = _user32.GetParent(hwnd)

    def clear(self, x, y, toolbar=False):
        """Is the playlist what the mouse would hit there? Its toolbar is a
        window of its own, a sibling with the same title."""
        hwnd, name, title = next(self._at(x, y), (None, "", ""))
        if toolbar:
            return name == "TNewCaption" and title.startswith(PLAYLIST_TITLE)
        return hwnd == self.hwnd

    def cover(self, x, y):
        """None when the playlist is clear at the point, else FL's number for
        the window over it (-1 for anything else)."""
        for hwnd, name, title in self._at(x, y):
            if hwnd == self.hwnd:
                return None
            if name in WINDOW_CLASSES:
                return WINDOW_CLASSES[name]
            if name == PLAYLIST_CLASS and title.startswith("Piano roll"):
                return 3
        return -1

    def move(self, x, y):
        _user32.SetCursorPos(int(x) - 2, int(y))    # a real move, so FL renews the hint
        time.sleep(0.01)
        _user32.SetCursorPos(int(x), int(y))
        time.sleep(0.03)

    def click(self, x, y):
        self._fl_in_front()
        self.move(x, y)
        _user32.mouse_event(0x2, 0, 0, 0, 0)
        time.sleep(0.03)
        _user32.mouse_event(0x4, 0, 0, 0, 0)
        time.sleep(0.05)

    def wheel(self, notches, shift=False):
        """Positive = wheel up. With Shift the playlist scrolls sideways."""
        self._fl_in_front()
        if shift:
            _user32.keybd_event(VK_SHIFT, 0, 0, 0)
        try:
            for _ in range(abs(int(notches))):
                _user32.mouse_event(0x800, 0, 0, 120 if notches > 0 else -120, 0)
                time.sleep(0.015)
        finally:
            if shift:
                _user32.keybd_event(VK_SHIFT, 0, pianoroll.KEYUP, 0)

    def key(self, vk):
        self._fl_in_front()
        pianoroll._press(vk)
        time.sleep(0.05)

    def menu(self, wait=0.8):
        """The popup menu that is open, as a rectangle, or None."""
        deadline = time.time() + wait
        while True:
            found = pianoroll._windows(pianoroll.MENU_CLASS)
            if found:
                time.sleep(0.12)        # let it finish drawing
                r = wintypes.RECT()
                _user32.GetWindowRect(found[0], ctypes.byref(r))
                return r.left, r.top, r.right, r.bottom
            if time.time() > deadline:
                return None
            time.sleep(0.01)

    def brightness(self, x, y):
        dc = _user32.GetDC(None)
        try:
            c = _gdi32.GetPixel(dc, int(x), int(y))
        finally:
            _user32.ReleaseDC(None, dc)
        return ((c & 255) + ((c >> 8) & 255) + ((c >> 16) & 255)) / 3.0
