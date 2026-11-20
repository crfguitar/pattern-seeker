"""Chords and the synth pad go into the piano roll, which only a piano-roll
script can write to (one run per channel).

FL's controller script cannot add piano-roll notes (and the step sequencer holds
one note per step), so the companion:

  1. writes "Pattern Seeker Chords.pyscript" with the notes baked in,
  2. has the controller script point the piano roll at the keys channel,
  3. runs that script for you: it opens the piano roll's Tools menu and walks to
     the script with the arrow keys (works on the first beat of an FL session),
     falling back to FL's "Run last script again" shortcut (Ctrl+Alt+Y),
  4. asks the controller script whether FL reported the edit (a piano-roll
     script cannot say so itself: FL 2026 blocks its file and environment access).

The script only ever deletes notes of its own colour, so anything else in that
piano roll - or in the wrong piano roll, should one be focused - is left alone.
"""

import ctypes
import os
import time
from ctypes import wintypes

from .link import _documents

SCRIPT_NAME = "Pattern Seeker Chords"
NOTE_COLOR = 9          # 0-15; our notes are recognised (and replaced) by this
MAX_STEPS = 1024        # never tile further than the drums do

_TEMPLATE = '''"""%(name)s - rewritten by Pattern Seeker on every beat. Do not edit.

Replaces the notes of colour %(color)d in this piano roll with the current chords.
"""
import flpianoroll as flp

COLOR = %(color)d
NOTES = %(notes)s    # (note, start step, length in steps, velocity 0-127); steps may be fractional

for _i in range(flp.score.noteCount - 1, -1, -1):
    if flp.score.getNote(_i).color == COLOR:
        flp.score.deleteNote(_i)

_step = flp.score.PPQ / 4.0
for _number, _start, _length, _vel in NOTES:
    _n = flp.Note()
    _n.number = _number
    _n.time = int(round(_start * _step))
    _n.length = max(1, int(round(_length * _step)))
    _n.velocity = _vel / 127.0
    _n.color = COLOR
    flp.score.addNote(_n)
'''


def tile(notes, total_steps, unit=64):
    """Repeat a lane of `unit` steps out to `total_steps`, trimming the last copy."""
    total_steps = min(MAX_STEPS, max(unit, int(total_steps)))
    out = []
    for offset in range(0, total_steps, unit):
        for number, start, length, vel in notes:
            begin = offset + start
            if begin < total_steps:
                out.append((number, begin, min(length, total_steps - begin), vel))
    return out


def _num(x):
    """A step position: whole steps print as ints, off-grid ones keep 4 decimals."""
    x = round(float(x), 4)
    return "%d" % x if x == int(x) else repr(x)


def script_source(notes):
    body = "[\n%s]" % "".join("    (%d, %s, %s, %d),\n" % (n[0], _num(n[1]), _num(n[2]), n[3])
                               for n in notes) if notes else "[]"
    return _TEMPLATE % {"name": SCRIPT_NAME, "color": NOTE_COLOR, "notes": body}


def script_path():
    return os.path.join(_documents(), "Image-Line", "FL Studio", "Settings",
                        "Piano roll scripts", SCRIPT_NAME + ".pyscript")


def write_script(notes):
    """Bake `notes` into the piano-roll script. Returns False if FL's folder is missing."""
    path = script_path()
    if not os.path.isdir(os.path.dirname(os.path.dirname(path))):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii", newline="\n") as fh:
        fh.write(script_source(notes))
    os.replace(tmp, path)
    return True


# ---- driving FL Studio's piano roll window -----------------------------------

PIANO_ROLL_CLASS = "TEventEditForm"
MENU_CLASS = "TQuickPopupMenuWindow"
TOOLS_ICON = (37, 15)   # the wrench, from the window's corner, at 100% scaling
VK_CONTROL, VK_MENU, VK_Y, KEYUP = 0x11, 0x12, 0x59, 0x2
VK_RETURN, VK_RIGHT, VK_DOWN = 0x0D, 0x27, 0x28

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _windows(class_name, title_prefix=""):
    found = []

    def visit(hwnd, _):
        if _user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == class_name:
                _user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value.startswith(title_prefix):
                    found.append(hwnd)
        return True

    _user32.EnumWindows(_EnumProc(visit), 0)
    return found


def find_piano_roll():
    """FL's piano roll window (it is a top-level window of its own), or None."""
    found = _windows(PIANO_ROLL_CLASS, "Piano roll")
    return found[0] if found else None


SCRIPT_DIALOG_CLASS = "TScriptDialog"    # what a piano-roll script with createDialog opens


def close_script_dialogs():
    """Close any piano-roll script dialog (without applying it). True if one was open."""
    found = _windows(SCRIPT_DIALOG_CLASS)
    for hwnd in found:
        _user32.PostMessageW(hwnd, 0x10, 0, 0)     # WM_CLOSE = the dialog's X: no changes
    return bool(found)


def bring_forward(hwnd):
    """Give `hwnd` the keyboard. False if Windows wouldn't let us."""
    if _user32.GetForegroundWindow() != hwnd and not _user32.SetForegroundWindow(hwnd):
        # Windows refuses focus changes from a background app; a tap of Alt lifts that.
        _user32.keybd_event(VK_MENU, 0, 0, 0)
        _user32.keybd_event(VK_MENU, 0, KEYUP, 0)
        _user32.SetForegroundWindow(hwnd)
    return _user32.GetForegroundWindow() == hwnd


def _press(*keys):
    for vk in keys:
        _user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(keys):
        _user32.keybd_event(vk, 0, KEYUP, 0)


def press_run_last_script():
    """Send Ctrl+Alt+Y to whichever window has the keyboard."""
    _press(VK_CONTROL, VK_MENU, VK_Y)


MAIN_CLASS = "TFruityLoopsMainForm"


def _exe_of(hwnd):
    """Full path of the program that owns `hwnd`, or None."""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = _kernel32.OpenProcess(0x1000, False, pid)     # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
    finally:
        _kernel32.CloseHandle(handle)
    return buf.value


def fl_exe():
    """The FL Studio program that is running (its main window's owner), or None."""
    for hwnd in _windows(MAIN_CLASS):
        exe = _exe_of(hwnd)
        if exe:
            return exe
    return None


def _fl_script_folder(hwnd):
    """The scripts that ship with the FL Studio that owns `hwnd`."""
    exe = _exe_of(hwnd)
    return os.path.join(os.path.dirname(exe), "System", "Config", "Piano roll scripts")         if exe else None


def menu_position(folders, name=SCRIPT_NAME):
    """Where `name` sits in the Tools menu's script list: FL shows the scripts of
    all its folders together, sorted by name. None if it isn't there."""
    names = set()
    for folder in folders:
        try:
            names.update(f[:-9] for f in os.listdir(folder) if f.lower().endswith(".pyscript"))
        except OSError:
            pass
    ordered = sorted(names, key=str.lower)
    return ordered.index(name) if name in ordered else None


def run_from_menu(hwnd):
    """Run our script from the piano roll's Tools menu, with no help from you.

    Clicks the Tools (wrench) icon, then Down, Right lands on the Scripts column
    and Down walks to our script. Nothing is typed unless the menu really opened.
    Returns False if it could not be done; True only means the keys were sent."""
    position = menu_position([os.path.dirname(script_path()), _fl_script_folder(hwnd) or ""])
    if position is None:
        return False
    old_context = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # real pixels
    try:
        rect, cursor = wintypes.RECT(), wintypes.POINT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        scale = (_user32.GetDpiForWindow(hwnd) or 96) / 96.0
        spot = wintypes.POINT(int(rect.left + TOOLS_ICON[0] * scale),
                              int(rect.top + TOOLS_ICON[1] * scale))
        if _user32.GetAncestor(_user32.WindowFromPoint(spot), 2) != hwnd:
            return False                    # something (our own window?) covers the icon
        _user32.GetCursorPos(ctypes.byref(cursor))
        try:
            _user32.SetCursorPos(spot.x, spot.y)
            time.sleep(0.03)
            _user32.mouse_event(0x2, 0, 0, 0, 0)
            _user32.mouse_event(0x4, 0, 0, 0, 0)
            deadline = time.time() + 0.6
            while not _windows(MENU_CLASS):
                if time.time() > deadline:
                    return False
                time.sleep(0.01)
            time.sleep(0.05)
            # Down = first built-in tool, Right = "Run last script again",
            # then past "Open script folder" to the scripts themselves.
            for vk in [VK_DOWN, VK_RIGHT] + [VK_DOWN] * (position + 2) + [VK_RETURN]:
                _press(vk)
                time.sleep(0.012)
            return True
        finally:
            _user32.SetCursorPos(cursor.x, cursor.y)
    finally:
        _user32.SetThreadDpiAwarenessContext(old_context)
