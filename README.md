# reminder

 discreet desktop activity simulator for Windows. Prevents sleep and generates
organic mouse, scroll, keyboard, and app-switching activity with adaptive
intensity modes and configurable safe zones.

## Features

- Adaptive work rhythms: Low, Med, High intensity
- Coordinated inputs: mouse movement, scrolling, keyboard actions
- Safe click zones and click-in-place mode
- Silent keys and optional natural typing with variable WPM
- App/tab cycling with self-exclusion
- Micro-breaks and short randomized pauses
- Basic and advanced modes
- Global hotkeys for start/stop/emergency stop
- Runs minimized as `reminder.exe` when built with PyInstaller

## Install

    pip install -r requirements.txt

## Run

    python -m src.main --intensity med --mode basic
    python -m src.gui

## Build

    pyinstaller --onefile --windowed --name reminder --icon NONE src/main.py

The output is `dist/reminder.exe`. Task Manager Details shows `reminder.exe`.

## Stop

- Ctrl+C in console mode
- Global hotkey in GUI/advanced mode
- Emergency stop clears all held inputs immediately

## Notes

- The app keeps the display and system awake via Windows
  `SetThreadExecutionState` while running and restores it on exit.
- Activity logs are written to `%LOCALAPPDATA%\reminder\reminder.log`.
- The app never transmits data externally.
