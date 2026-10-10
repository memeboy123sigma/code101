# THE PI DECK

A 45-game mini-console running on a **Raspberry Pi Pico 2W** with a 1.30" SH1106 OLED
display and a Freenove ES7148/PAM8403 audio converter amplifier.

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Boot, hardware init, audio engine, 31 games, menu |
| `games2.py` | 14 additional games (injected with shared helpers by main.py) |
| `sh1106.py` | Minimal SH1106 I2C OLED driver (no external library needed) |

Flash all three files to the **root** of the Pico 2W's filesystem.

---

## Hardware wiring

| Component | Pin |
|---|---|
| OLED SDA | GP0 |
| OLED SCL | GP1 |
| Joystick VRx | GP26 (ADC0) |
| Joystick VRy | GP27 (ADC1) |
| Joystick SW (button) | GP22 |
| Audio BCK | GP16 |
| Audio LRCK | GP17 |
| Audio DIN | GP18 |
| Audio EN (amp enable) | GP15 |

All VCC pins → 3V3. All GND pins → GND.  
Speaker wires to LOUT+ / LOUT- (mono — only one channel needed).

---

## Dependencies / libraries

- **MicroPython** for Raspberry Pi Pico 2W (tested with MicroPython v1.24+)
- **`sh1106.py`** — bundled, no external install needed
- **Standard MicroPython modules used**: `machine` (Pin, I2C, ADC, I2S), `framebuf`,
  `math`, `time`, `random`, `struct`
- No `pip` packages. Everything runs from the three files above.

---

## Controls

| Action | Effect |
|---|---|
| Joystick | Navigate menu / move in-game |
| Button (SW) | Confirm selection / fire / action |
| Double-tap button | Return to main menu from any game |

---

## Architecture

### Boot sequence (`main.py: main()`)
1. `make_display()` — initialises I2C + SH1106 OLED
2. `calibrate_joystick()` — reads the joystick at rest to measure true centre (prevents drift)
3. `init_audio()` — drives GP15 HIGH to enable PAM8403 amplifier, then opens I2S channel
4. `play_boot_animation()` — title screen with bounce animation + boot jingle
5. `menu()` → `game_fn(display)` loop — runs selected game, catches `GoHome` to re-enter menu

### Audio engine
- `AUDIO_RATE = 8000` Hz — low enough that sin() stays fast on Pico 2W without perceptible
  quality loss for game SFX
- `beep()` — sine wave tone; pre-computes ONE cycle, repeats it with fade envelope
- `square_tone()` — square wave for punchy retro clicks
- `noise_burst()` — white noise with exponential decay, used for explosions/impacts
- `play_chord()` — sums multiple sine waves; reserved for future use
- All audio functions are silent no-ops when `_i2s is None` (safe if audio init fails)

### Two-file game split
`games2.py` has no hardware access of its own. After `import games2`, `main.py` injects
the shared helpers (`read_axes`, `button`, `game_over_screen`, etc.) as module-level
attributes. This keeps hardware setup in one place and lets the file be syntax-checked
offline without a Pico attached.

### Double-tap home gesture
`button()` in `main.py` tracks tap timing. Two presses within `DOUBLE_TAP_MS` (400 ms)
raises `GoHome`, which is caught in `main()` and resets all tap state before re-entering
the menu. Every game that calls `button()` therefore gets the gesture for free.

---

## Games list (45 total)

**Pack 1 (main.py):** Mini-DOOM, Snake, Pong, Breakout, Tetris, Flappy, Invaders,
Pac-Maze, Reaction, Simon, Asteroids, Frogger, TicTacToe, Connect4, 2048, Memory Match,
Whack-a-Mole, Lunar Lander, Rock Paper Scissors, Dino Run, Doom Maze, Racer, Platformer,
Zombies, RPG Battle, Boxing, Battleship, Heli, Air Hockey, Lane Runner, Sniper

**Pack 2 (games2.py):** Centipede, Shmup, Missile Command, Pinball, Bomberman, Sokoban,
Lights Out, Sudoku, Ice Climb, Checkers, Othello, Yahtzee, Hangman, Match-3

---

## What was fixed in this refactor

| # | Bug | Fix |
|---|---|---|
| 1 | `main.py` and `games2.py` started with raw prose → `SyntaxError` on import | Wrapped in `"""` module docstrings |
| 2 | `AUDIO_RATE` constant never defined → `NameError` in all audio functions | Added `AUDIO_RATE = 8000` after pin constants |
| 3 | `_i2s` never initialised at module level → `NameError` in audio functions | Added `_i2s = None` at module level |
| 4 | Audio setup function renamed `_removed_init_audio` and commented out → no sound | Restored as `init_audio()`, uncommented call in `main()` |
| 5 | PAM8403 EN pin (GP15) never driven HIGH → amplifier stayed muted | Added `Pin(AUDIO_EN, Pin.OUT).value(1)` inside `init_audio()` |
| 6 | File named `python2games.py` but imported as `games2` → `ModuleNotFoundError` | Created `games2.py` with corrected docstring |

---

## Extending the project

### Adding a new game
1. Write `play_mygame(display)` in either `main.py` or `games2.py`
2. Add `("My Game", play_mygame)` to the `GAMES` list (main.py) or `GAMES2` list (games2.py)
3. If adding to `games2.py` and you need audio, also inject the function in the
   `import games2` block in `main.py`

### Audio in games2.py games
The audio helpers (`beep`, `square_tone`, `noise_burst`) are defined in `main.py`.
To use them in a games2 game, add injection lines after the existing block:
```python
games2.beep = beep
games2.square_tone = square_tone
games2.noise_burst = noise_burst
```
Then declare module-level placeholders in `games2.py` alongside the other placeholders.

### Changing display resolution
Update `SCREEN_W` and `SCREEN_H` in `main.py`. The SH1106 driver accepts arbitrary
width/height via `SH1106_I2C(width, height, i2c, ...)`.

### Changing audio sample rate
Change `AUDIO_RATE` in `main.py`. Higher rates (e.g. 11025, 22050) improve tone quality
at the cost of more sin() computation per frame. 8000 Hz is the practical minimum.
