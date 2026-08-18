"""Win32 primitives for keeping the machine and your presence awake.

Three separate mechanisms live here, and they solve different problems:

* ``apply_execution_state`` tells Windows itself not to sleep or blank the
  display. This is the supported API for that (the same one Caffeine and
  PowerToys Awake use) and involves no synthetic input at all.
* ``send_*`` inject input, which is what actually resets an *application's*
  own idle timer -- Teams and friends do not consult the power policy.
* ``get_idle_seconds`` reports how long the user has genuinely been away, so
  we only inject when nobody is at the keyboard.

Injection uses SendInput rather than the superseded keybd_event/mouse_event
pair: it delivers the events atomically and cannot be interleaved with real
input the way two separate calls can.
"""

import ctypes
from ctypes import wintypes


USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

# SetThreadExecutionState flags.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
KEYEVENTF_KEYUP = 0x0002
VK_F15 = 0x7E

if ctypes.sizeof(ctypes.c_void_p) == 8:
    ULONG_PTR = ctypes.c_ulonglong
else:
    ULONG_PTR = ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", _INPUTUNION)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


USER32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
USER32.SendInput.restype = wintypes.UINT
USER32.GetLastInputInfo.argtypes = (ctypes.POINTER(LASTINPUTINFO),)
USER32.GetLastInputInfo.restype = wintypes.BOOL
KERNEL32.SetThreadExecutionState.argtypes = (wintypes.DWORD,)
KERNEL32.SetThreadExecutionState.restype = wintypes.DWORD
KERNEL32.GetTickCount.restype = wintypes.DWORD


def _send(inputs):
    count = len(inputs)
    array = (INPUT * count)(*inputs)
    sent = USER32.SendInput(count, array, ctypes.sizeof(INPUT))
    return sent == count


def send_key(virtual_key=VK_F15):
    """Press and release a key in a single atomic SendInput call."""
    down = INPUT(type=INPUT_KEYBOARD)
    down.value.ki = KEYBDINPUT(wVk=virtual_key, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    up = INPUT(type=INPUT_KEYBOARD)
    up.value.ki = KEYBDINPUT(wVk=virtual_key, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    return _send([down, up])


def send_mouse_jiggle(zen=True):
    """Register mouse input.

    In zen mode the movement is zero pixels: Windows counts it as real input
    and resets its idle timers, but the pointer never actually moves, so it
    cannot land somewhere unexpected or fight the user for the cursor.
    """
    if zen:
        event = INPUT(type=INPUT_MOUSE)
        event.value.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
        return _send([event])

    right = INPUT(type=INPUT_MOUSE)
    right.value.mi = MOUSEINPUT(dx=1, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
    left = INPUT(type=INPUT_MOUSE)
    left.value.mi = MOUSEINPUT(dx=-1, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)
    # Sent together so nothing can move the pointer between the two halves.
    return _send([right, left])


def get_idle_seconds():
    """Seconds since the last real user input. Our own injections reset this."""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not USER32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0

    # GetTickCount wraps every ~49.7 days; masking keeps the delta correct.
    delta = (KERNEL32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return delta / 1000.0


def build_execution_flags(prevent_sleep, keep_display_on):
    flags = ES_CONTINUOUS
    if prevent_sleep:
        flags |= ES_SYSTEM_REQUIRED
    if keep_display_on:
        flags |= ES_DISPLAY_REQUIRED
    return flags


def apply_execution_state(prevent_sleep, keep_display_on):
    """Hold Windows awake for the calling thread.

    The state is per-thread and lasts until the next call on that thread, so
    this must be called from the long-lived activity thread. Passing both flags
    false clears any hold we were keeping.
    """
    flags = build_execution_flags(prevent_sleep, keep_display_on)
    return KERNEL32.SetThreadExecutionState(flags) != 0


def release_execution_state():
    return KERNEL32.SetThreadExecutionState(ES_CONTINUOUS) != 0
