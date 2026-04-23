# <p align="center"> Alive Forever </p>

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

- Always Active: Keeps Teams showing green "Available" status.
- System Tray App: Runs silently in the background.
- Retro Control Panel UI: Windows 95-inspired configuration panel.
- Multiple Activity Types: F15 key (invisible) or mouse jiggle.
- Configurable Interval: Set activity frequency from 10 to 300 seconds.
- Time-Based Schedule: Choose exactly when the app should stay active.
- Built-In Presets: Start from Always On, Workday, Evening, or Stealth.
- Windows Startup: Optional auto-start with Windows.
- Tray Notifications: See schedule and state changes without opening settings.
- Live Stats: Track session and lifetime activity counts.
- Persistent Logs: Troubleshoot silent mode from a rotating log file.
- Persistent Settings: Your preferences are saved automatically.

## Setup Wizard

```text
+---------------------------+
| Quick Start               |
+---------------------------+
```

### Option 1: Double-Click Launch

1. **Download** or clone this repository
2. **Double-click** `run.bat`
3. Done! Look for the **retro desktop-style icon** in your system tray

### Option 2: Manual Python Launch

```bash
# Clone the repository
git clone https://github.com/abutsik4/Alive_Forever.git
cd Alive_Forever

# Install dependencies
pip install -r requirements.txt

# Run the app
python keep_alive.py
```

### Option 3: Run Without Console Window (Silent Mode)

Double-click **`run_silent.bat`** to launch completely hidden - no console window, just the tray icon!

> **How it works:** Uses `pythonw.exe` instead of `python.exe` to run without a console.

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

- **Pause / Resume** - Toggle the keep-alive function.
- **Settings** - Open the configuration panel.
- **Quit** - Exit the application.

### Settings Panel

<p align="center">
  <em>Access via tray icon → Settings for a classic control-panel style window</em>
</p>

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
- Installs PyInstaller if needed
- Builds a packaged app into `dist/AliveForever/`
- Builds `dist/AliveForever-Setup.exe` if `makensis` is installed

If NSIS is not installed, the installer script is still available at `installer/AliveForever.nsi`.

## Startup Options

**Option A: Via Settings Panel**
1. Right-click tray icon → ⚙ Settings
2. Enable "Start with Windows"
3. Click "💾 Save Settings"

**Option B: Manual**
1. Press `Win + R`
2. Type `shell:startup` and press Enter
3. Create a shortcut to `run.bat` in this folder

## Help Topics

**Q: Will this get me in trouble at work?**
> This is a personal productivity tool. Use responsibly and in accordance with your organization's policies.

**Q: Does it work when Teams is minimized?**
> Yes! The activity simulation works at the Windows level, regardless of Teams' window state.

**Q: Will it prevent my PC from sleeping?**
> No, it only simulates keyboard/mouse activity. Your PC's power management settings are unaffected.

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
