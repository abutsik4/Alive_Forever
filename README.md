# Alive Forever

```text
+--------------------------------------------------------------+
| Alive Forever                                                |
+--------------------------------------------------------------+
| File  Edit  View  Help                                       |
+--------------------------------------------------------------+
| A Windows 95-inspired tray utility that keeps Teams active.  |
+--------------------------------------------------------------+
```

<p align="center">
  <img src="icon.png" alt="Alive Forever Icon" width="96" height="96">
</p>

<p align="center">
  <strong>Keep your Microsoft Teams status "Active" - forever.</strong>
</p>

<p align="center">
  <img src="https://github.com/abutsik4/Alive_Forever/actions/workflows/build.yml/badge.svg" alt="Build">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-000080?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.8%2B-c0c0c0?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/Theme-Windows%2095-808080?style=flat-square" alt="Theme">
  <img src="https://img.shields.io/badge/License-MIT-ffff00?style=flat-square" alt="License">
</p>

## Program Overview

**Alive Forever** is a lightweight Windows application that prevents Microsoft Teams from automatically setting your status to "Away" due to inactivity. It runs quietly in your system tray and simulates subtle keyboard activity to keep you appearing "Active".

```text
+---------------------------+
| Installed Components      |
+---------------------------+
```

- Keeps Teams Green: Stops the automatic switch to "Away".
- Real Keep-Awake: Blocks sleep and optionally display blanking through the
  Windows power API, with no simulated input involved.
- Stays Out Of Your Way: Only injects input once you have genuinely been idle,
  so it never fights you for the keyboard or the cursor.
- Invisible Mouse Jiggle: Zero-pixel movement that Windows counts as input but
  that never moves your pointer.
- Quick Timers: "Stay active for 2 hours" straight from the tray menu.
- Time-Based Schedule: Choose exactly when the app should stay active.
- Built-In Presets: Start from Always On, Workday, Evening, or Focus.
- Self-Healing Startup: Registers a logon task, checks it still works on every
  launch, and repairs it if you move the folder.
- Retro Control Panel UI: Windows 95-inspired, tabbed, and DPI-aware so it
  stays sharp on scaled displays.
- Live Stats: Track session and lifetime activity counts.
- Persistent Logs: Troubleshoot silent mode from a rotating log file.

## Install

```text
+---------------------------+
| Quick Start               |
+---------------------------+
```

### Option 1: Installer (recommended)

Download **`AliveForever-Setup.exe`** from the
[latest release](https://github.com/abutsik4/Alive_Forever/releases/latest)
and run it. No Python required.

The installer offers a **"Start automatically at sign-in"** option - leave it
ticked and you never have to launch the app by hand again.

> **SmartScreen warning:** the installer is not code-signed, so Windows will
> show a "Windows protected your PC" screen. Click **More info** then
> **Run anyway**. Every release publishes `SHA256SUMS.txt` so you can verify
> the download first:
>
> ```powershell
> Get-FileHash .\AliveForever-Setup.exe -Algorithm SHA256
> ```

### Option 2: Portable

Download **`AliveForever-portable.zip`**, extract it anywhere, and run
`AliveForever.exe`. Nothing is written outside `%APPDATA%\AliveForever`.

### Option 3: From source

```bash
git clone https://github.com/abutsik4/Alive_Forever.git
cd Alive_Forever

pip install -r requirements.txt
python keep_alive.py
```

Or double-click `run.bat` (with console) or `run_silent.bat` (hidden).

### Building it yourself

```powershell
.\build.ps1
```

Produces `dist/AliveForever` (portable) and, if NSIS is installed,
`dist/AliveForever-Setup.exe`.

## What this does, and what it does not

Being straight about this is more useful than a long feature list:

**It does:**
- Ask Windows not to sleep or blank the display, via the same power API that
  Caffeine and PowerToys Awake use. This involves no fake input at all.
- Send an F15 keypress (a key no keyboard has and no app reacts to) and/or an
  invisible mouse event, which is what keeps Teams from marking you Away.
- Only do that while you are actually away from the machine, so it never
  fights you for the cursor.

**It does not:**
- Hide anything from your employer. Teams reports presence, not keystrokes,
  but device management software can see what runs on your PC. This is an
  ordinary tray utility, not a stealth tool.
- Override a lock screen enforced by group policy. On a managed machine your
  IT policy still wins, and no keep-awake tool can change that.
- Send any data anywhere. There is no network code in this project.

## User Guide

```text
+---------------------------+
| Notification Area         |
+---------------------------+
```

### System Tray Icon

After launching, the app runs in your **system tray** (bottom-right corner, near the clock).

| Icon | Meaning |
|:----:|---------|
| Desktop icon + green light | **Active** - Keeping you online |
| Desktop icon + gray pause state | **Paused** - Normal Teams behavior |
| Desktop icon + dark red light | **Scheduled Off** - Outside active schedule |

### Tray Menu Options

**Right-click** the tray icon to access:

- **Status line** - Current state at a glance, no need to open Settings.
- **Pause / Resume** - Toggle the keep-alive function.
- **Stay active for** - 30 min / 1 h / 2 h / 4 h. Overrides the schedule.
- **Pause for** - Same durations, in the other direction.
- **Clear timer** - Drop a running override and go back to the schedule.
- **Settings** - Open the configuration panel.
- **Quit** - Exit the application.

### Settings Panel

<p align="center">
  <em>Access via tray icon -> Settings for a classic control-panel style window</em>
</p>

The panel is organised as tabs, so nothing scrolls:

| Tab | Contains |
|-----|----------|
| **Status** | Current state, session and lifetime counters, startup health |
| **Activity** | Preset, interval, activity type, and the Keep Awake options |
| **Schedule** | A 7x24 grid - click or drag to paint the hours you want active |
| **Startup** | Start with Windows, start minimized, notifications |
| **About** | What the app does and does not do, and where the logs live |

`Enter` saves, `Esc` closes. Saving reports into the status bar rather than
interrupting with a dialog.

> **A note on the schedule grid:** it works in whole hours. If your existing
> schedule uses minute precision (say 08:30-11:45) the panel says so, and it
> only rewrites your windows if you actually edit the grid.

| Setting | Description | Default |
|---------|-------------|---------|
| **Preset** | Quick starting point for schedule and activity settings | Custom |
| **Activity Interval** | Seconds between activity simulations | 60 |
| **Activity Type** | F15 Key (recommended), Mouse Jiggle, or Both | F15 Key |
| **Schedule** | One or more time windows with per-window active days | Disabled |
| **Start with Windows** | Auto-launch when you log in | Off |
| **Start Minimized** | Go straight to tray on launch | On |
| **Notifications** | Show tray notifications for state changes | On |

## System Behavior

The app uses one of two methods to simulate user activity:

### F15 Key Press (Recommended)
Simulates pressing the F15 key, which:
- Registers as keyboard activity to Windows.
- Is completely invisible with no on-screen effect.
- Won't interfere with your work.
- Works even with Teams minimized.

### Mouse Jiggle
Moves the mouse cursor 1 pixel and back:
- Registers as mouse activity.
- May be slightly noticeable if you're doing precise work.

## Program Manager View

```
Alive_Forever/
├── alive_forever/     # Extracted package modules (core, ui, system)
├── installer/         # NSIS installer script
├── tests/             # Schedule logic tests
├── keep_alive.py      # Thin entrypoint wrapper
├── build.ps1          # Build helper for exe + installer
├── AliveForever.spec  # PyInstaller spec
├── run.bat            # Windows launcher script
├── requirements.txt   # Python dependencies
├── requirements-build.txt  # Build-only dependency list
├── config.json        # Legacy/sample settings for first-run migration
├── icon.png           # Application icon
└── README.md          # This file
```

### Runtime Data Location

When the app runs, it now stores live settings and logs in:

```text
%APPDATA%\AliveForever\config.json
%APPDATA%\AliveForever\logs\alive_forever.log
```

## System Requirements

- **Windows 10/11**
- **Python 3.8+** ([Download](https://www.python.org/downloads/))

### Dependencies

| Package | Purpose |
|---------|---------|
| `pystray` | System tray icon functionality |
| `pillow` | Icon image generation |

Dependencies are automatically installed on first run.

## Packaging

To build a standalone Windows package that does not require Python for end users:

```powershell
./build.ps1
```

This does the following:

- Regenerates `icon.png` and `icon.ico`
- Installs PyInstaller from `requirements-build.txt`
- Builds a packaged app into `dist/AliveForever/`
- Builds `dist/AliveForever-Setup.exe` if `makensis` is installed

If NSIS is not installed, the installer script is still available at `installer/AliveForever.nsi`.

## Startup Options

The app asks once, on first launch, whether it should start with Windows.
If you said no and changed your mind:

1. Right-click tray icon -> Settings
2. Enable "Start with Windows"
3. Click "Save Settings"

**How it registers.** A Scheduled Task is created first, because Run-key
entries can be silently disabled from Task Manager's Startup tab. If task
creation is blocked by policy, it falls back to the Run key automatically.
Either way the entry is validated on every launch - if you move the folder or
reinstall Python, it repairs itself instead of quietly failing, and the Status
card shows whether startup is **registered**, **broken**, or **off**.

## Command Line

| Flag | Effect |
|------|--------|
| `--paused` | Start paused for this session only |
| `--minimized` | Start without opening the settings window |
| `--preset NAME` | Apply a preset (`Always On`, `Workday`, `Evening`, `Focus`, `Custom`) |
| `--register-startup` | Register auto-start and exit |
| `--unregister-startup` | Remove auto-start and exit |
| `--startup-status` | Report whether auto-start is registered (exit 0 if healthy) |

The installer uses `--register-startup` rather than calling `schtasks` itself,
because `schtasks /Create /SC ONLOGON` needs elevation while registering a
per-user logon task from an XML definition does not.

## Help Topics

**Q: Will this get me in trouble at work?**
> This is a personal productivity tool. Use responsibly and in accordance with your organization's policies.

**Q: Does it work when Teams is minimized?**
> Yes! The activity simulation works at the Windows level, regardless of Teams' window state.

**Q: Will it prevent my PC from sleeping?**
> Yes. "Prevent Sleep" is on by default and uses the Windows power API
> (`SetThreadExecutionState`) rather than fake input. "Keep Screen On" is a
> separate option, off by default. Note that a lock screen enforced by company
> policy still wins - no keep-awake tool can override that.

**Q: Does it move my mouse while I'm using the PC?**
> No. "Only Act While You Are Away" is on by default, so nothing is injected
> until you have been idle for 45 seconds. And "Invisible Mouse Jiggle" sends a
> zero-pixel movement, so even then the pointer never actually moves.

**Q: How do I completely close it?**
> Right-click the tray icon → ✕ Quit, or close the console window if visible.

**Q: Can I change the activity interval?**
> Yes! Open Settings and adjust the "Activity Interval" slider (10-300 seconds).

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **App doesn't start** | Ensure Python 3.8+ is installed and in PATH |
| **No tray icon visible** | Check the hidden icons area (^ arrow in taskbar) |
| **Settings won't open** | Try restarting the app |
| **Teams still shows Away** | Try "Both" activity type in settings |
| **Need to debug silent mode** | Check `%APPDATA%\AliveForever\logs\alive_forever.log` |

## License

MIT License - feel free to use, modify, and distribute.

## Contributing

Contributions welcome! Feel free to:
- Report bugs.
- Suggest features.
- Submit pull requests.

```text
+--------------------------------------------------------------+
| Status: Ready                                                |
+--------------------------------------------------------------+
| Made with care to keep you Alive Forever.                    |
+--------------------------------------------------------------+
```
