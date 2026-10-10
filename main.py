"""
THE PI DECK - main module.

Flash this file as main.py on the Pico 2W, alongside sh1106.py (the SH1106
I2C OLED driver) and games2.py (second batch of games) in the root folder.
The device boots straight into the game menu.

WIRING (change the pin constants below if yours differs):
  OLED  (I2C):  SDA=GP0,  SCL=GP1,  VCC=3V3, GND=GND
  Joystick:     VRx=GP26, VRy=GP27, SW=GP22,  VCC=3V3, GND=GND
  Audio (Freenove ES7148 / PAM8403 Amplifier):
    BCK=GP16, LRCK=GP17, DIN=GP18, EN=GP15,  VCC=3V3, GND=GND
    Speaker wires to LOUT+ / LOUT- (mono - only one channel needed)

Controls:
  Joystick    - navigate menus / move in games
  Button (SW) - confirm / fire / action
  Double-tap  - return to main menu from any game at any time
"""
import math, time, random, struct
from machine import Pin, I2C, ADC, I2S

# ------------------------------------------------------------- pin map --
I2C_SDA, I2C_SCL = 0, 1
JOY_VRX, JOY_VRY, JOY_SW = 26, 27, 22
AUDIO_BCK, AUDIO_LRCK, AUDIO_DIN, AUDIO_EN = 16, 17, 18, 15
# --------------------------------------------------------------------------

SCREEN_W, SCREEN_H = 128, 64
JOY_DEAD = 6000
DOUBLE_TAP_MS = 400  # max gap between taps to count as a double-tap home gesture
AUDIO_RATE = 8000   # 8 kHz keeps sin() computation fast enough for real-time SFX on Pico 2W

_i2s = None         # set by init_audio(); None disables all audio gracefully


class GoHome(Exception):
    """Raised by button() on a double-tap; caught in main() to return to menu."""
    pass


_vrx = ADC(Pin(JOY_VRX))
_vry = ADC(Pin(JOY_VRY))
_btn = Pin(JOY_SW, Pin.IN, Pin.PULL_UP)

_btn_was_pressed = False
_last_tap_time = 0
_tap_count = 0

def init_audio():
    """Set up I2S output to the Freenove ES7148/PAM8403 board.
    EN pin must be driven HIGH before I2S starts or the amplifier stays muted."""
    global _i2s
    Pin(AUDIO_EN, Pin.OUT).value(1)  # enable PAM8403 amplifier
    try:
        _i2s = I2S(0, sck=Pin(AUDIO_BCK), ws=Pin(AUDIO_LRCK), sd=Pin(AUDIO_DIN),
                   mode=I2S.TX, bits=16, format=I2S.MONO, rate=AUDIO_RATE, ibuf=4000)
        print("audio: I2S init OK")
    except Exception as e:
        print("audio: I2S init FAILED:", e)
        _i2s = None


def beep(freq=440, duration_ms=100, volume=0.3):
    """Plays a single tone. Computes ONE waveform cycle (a few dozen samples at
    most) and repeats that tiny buffer to fill the duration, instead of
    recalculating math.sin() for every output sample - the latter is too slow
    for MicroPython to keep up with real-time audio and causes static/buzzing
    from buffer underruns rather than an actual error."""
    if _i2s is None or freq <= 0:
        return
    cycle_samples = max(4, int(AUDIO_RATE / freq))
    total_samples = int(AUDIO_RATE * duration_ms / 1000)
    repeats = max(1, total_samples // cycle_samples)
    fade = max(1, repeats // 6)  # fade in/out over ~1/6 of the note - kills pops
    try:
        for r in range(repeats):
            if r < fade: scale = (r + 1) / fade
            elif r >= repeats - fade: scale = (repeats - r) / fade
            else: scale = 1.0
            amp = int(32767 * volume * scale)
            cycle = bytearray(cycle_samples * 2)
            for i in range(cycle_samples):
                s = int(amp * math.sin(2 * math.pi * i / cycle_samples))
                struct.pack_into('<h', cycle, i * 2, s)
            _i2s.write(cycle)
    except Exception:
        pass


def square_tone(freq=440, duration_ms=80, volume=0.15):
    """Square wave instead of sine - punchier, more 'retro game' than a pure tone.
    Used for clicks and UI feedback rather than musical notes."""
    if _i2s is None or freq <= 0:
        return
    cycle_samples = max(4, int(AUDIO_RATE / freq))
    half = cycle_samples // 2
    total_samples = int(AUDIO_RATE * duration_ms / 1000)
    repeats = max(1, total_samples // cycle_samples)
    fade = max(1, repeats // 6)
    try:
        for r in range(repeats):
            if r < fade: scale = (r + 1) / fade
            elif r >= repeats - fade: scale = (repeats - r) / fade
            else: scale = 1.0
            amp = int(32767 * volume * scale)
            cycle = bytearray(cycle_samples * 2)
            for i in range(cycle_samples):
                struct.pack_into('<h', cycle, i * 2, amp if i < half else -amp)
            _i2s.write(cycle)
    except Exception:
        pass


def noise_burst(duration_ms=60, volume=0.18):
    """White-noise burst with a fast decay envelope - a real gunshot/explosion
    is loud for an instant then fades, not flat-volume for its whole length.
    Flat noise is what sounds like harsh screeching static; the decay is what
    makes it read as an actual impact sound."""
    if _i2s is None:
        return
    n = int(AUDIO_RATE * duration_ms / 1000)
    amp = int(32767 * volume)
    buf = bytearray(n * 2)
    for i in range(n):
        decay = 1.0 - (i / n)        # loud at the start, fades to silence
        decay = decay * decay        # curve it so the fade feels snappier
        s = int(random.randint(-amp, amp) * decay)
        struct.pack_into('<h', buf, i * 2, s)
    try:
        _i2s.write(buf)
    except Exception:
        pass


def play_chord(freqs, duration_ms, volume=0.22):
    """Sums several sine waves into one buffer - real chords, not just one note.
    Not currently used anywhere (the menu's background loop was removed for
    being too slow), kept here in case you want to use it for something later."""
    if _i2s is None or not freqs:
        return
    n = int(AUDIO_RATE * duration_ms / 1000)
    buf = bytearray(n * 2)
    amp = int(32767 * volume / len(freqs))
    for i in range(n):
        s = 0
        for f in freqs:
            s += amp * math.sin(2 * math.pi * f * i / AUDIO_RATE)
        s = int(max(-32768, min(32767, s)))
        struct.pack_into('<h', buf, i * 2, s)
    try:
        _i2s.write(buf)
    except Exception:
        pass


# ---- tiny built-in composer: named notes + real short melodies ----------
NOTES = {
    'C3': 131, 'D3': 147, 'E3': 165, 'F3': 175, 'G3': 196, 'A3': 220, 'B3': 247,
    'C4': 262, 'D4': 294, 'E4': 330, 'F4': 349, 'F#4': 370, 'G4': 392,
    'A4': 440, 'B4': 494, 'C5': 523, 'D5': 587, 'E5': 659, 'F5': 698,
    'G5': 784, 'A5': 880, 'B5': 988, 'C6': 1047, 'D6': 1175, 'E6': 1319,
}


def play_tune(notes, gap_ms=15, volume=0.3):
    """notes is a list of (note_name_or_freq_or_None, duration_ms). None is a rest."""
    for n, dur in notes:
        if n is None:
            time.sleep_ms(dur)
        else:
            freq = NOTES.get(n, n) if isinstance(n, str) else n
            beep(freq, dur, volume)
        time.sleep_ms(gap_ms)


BOOT_THEME = [('C5', 90), ('E5', 90), ('G5', 90), ('C6', 180)]
SELECT_CHIME = [('C5', 55), ('E5', 90)]
VICTORY_TUNE = [('C5', 90), ('E5', 90), ('G5', 90), ('C6', 90), ('G5', 90), ('C6', 240)]
DEFEAT_TUNE = [('G4', 160), ('F#4', 160), ('F4', 160), ('E4', 320)]

# Mellow Cmaj7-Am7-Fmaj7-G7 style loop (bass note, chord tones, duration ms) -
# plays softly while browsing the menu, one chord advancing every cycle.
LOFI_PROGRESSION = [
    ('C3', ['C4', 'E4', 'G4'], 650),
    ('A3', ['A3', 'C4', 'E4'], 650),
    ('F3', ['F3', 'A3', 'C4'], 650),
    ('G3', ['G3', 'B3', 'D4'], 650),
]

# Real resting values rarely sit exactly at 32768 - calibrate_joystick()
# measures the actual center at boot so small offsets don't get read as
# a held direction (the cause of a menu/game that scrolls on its own).
JOY_CENTER_X = 32768
JOY_CENTER_Y = 32768


def calibrate_joystick(display=None, samples=80):
    global JOY_CENTER_X, JOY_CENTER_Y
    if display:
        display.fill(0)
        centered_text(display, "Calibrating...", 24)
        centered_text(display, "don't touch stick", 36)
        display.show()
    xs = ys = 0
    for _ in range(samples):
        xs += _vrx.read_u16()
        ys += _vry.read_u16()
        time.sleep_ms(5)
    JOY_CENTER_X = xs // samples
    JOY_CENTER_Y = ys // samples


def make_display():
    import sh1106
    i2c = I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=400000)
    # res=None: this is the 4-pin module, no hardware reset line wired
    return sh1106.SH1106_I2C(SCREEN_W, SCREEN_H, i2c, res=None, addr=0x3c)


def read_axes():
    x = _vrx.read_u16() - JOY_CENTER_X
    y = _vry.read_u16() - JOY_CENTER_Y
    x = 0.0 if abs(x) < JOY_DEAD else x / 32768.0
    y = 0.0 if abs(y) < JOY_DEAD else y / 32768.0
    return x, y


def read_dir():
    x, y = read_axes()
    if y < -0.5: return 'U'
    if y > 0.5: return 'D'
    if x < -0.5: return 'L'
    if x > 0.5: return 'R'
    return None


def button():
    global _btn_was_pressed, _last_tap_time, _tap_count
    pressed = _btn.value() == 0
    if pressed and not _btn_was_pressed:
        square_tone(1000, 18, 0.07)  # short, quiet click on every press
        now = time.ticks_ms()
        if time.ticks_diff(now, _last_tap_time) < DOUBLE_TAP_MS:
            _tap_count += 1
        else:
            _tap_count = 1
        _last_tap_time = now
        if _tap_count >= 2:
            _tap_count = 0
            _btn_was_pressed = pressed
            raise GoHome()
    _btn_was_pressed = pressed
    return pressed


def wait_release():
    while button():
        time.sleep_ms(10)


def wait_for_press(timeout_ms=None):
    start = time.ticks_ms()
    while not button():
        if timeout_ms and time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
            return False
        time.sleep_ms(5)
    return True


def centered_text(display, text, y, invert=False):
    x = max(0, (SCREEN_W - len(text) * 8) // 2)
    display.text(text, x, y, 0 if invert else 1)


def game_over_screen(display, title, score=None):
    for i in range(1, len(title) + 1):
        display.fill(0)
        centered_text(display, title[:i], 20)
        display.show()
        time.sleep_ms(30)
    t = title.upper()
    if any(w in t for w in ("WIN", "SOLVED", "ESCAPED", "LANDED", "SUNK")):
        square_tone(880, 150, 0.15)
    else:
        square_tone(180, 220, 0.15)
    if score is not None:
        centered_text(display, "Score: {}".format(score), 34)
    centered_text(display, "press to menu", 50)
    display.show()
    wait_for_press()
    wait_release()


def play_boot_animation(display):
    title = "THE PI DECK"
    play_tune(BOOT_THEME, volume=0.15)
    for i in range(1, len(title) + 1):
        display.fill(0)
        centered_text(display, title[:i], 24)
        display.show()
        time.sleep_ms(35)
    bx, bdir, blink = 10, 2, 0
    while not button():
        display.fill(0)
        centered_text(display, title, 18)
        bx += bdir
        if bx <= 4 or bx >= SCREEN_W - 8:
            bdir = -bdir
        display.fill_rect(bx, 36, 6, 6, 1)
        blink += 1
        if (blink // 15) % 2 == 0:
            centered_text(display, "press to start", 52)
        display.show()
        time.sleep_ms(30)
    wait_release()


# ============================================================ MINI-DOOM --
def play_minidoom(display):
    MAP = [
        "########",
        "#..#...#",
        "#..#.#.#",
        "#....#.#",
        "#.##.#.#",
        "#.#....#",
        "#.#.####",
        "########",
    ]
    MAP_W, MAP_H = len(MAP[0]), len(MAP)
    FOV = math.radians(60)
    NUM_RAYS = 64
    COL_W = SCREEN_W // NUM_RAYS
    MAX_STEPS = 20
    MOVE_SPEED = 0.07
    TURN_SPEED = 0.07
    BULLET_SPEED = 0.25
    BULLET_LIFE = 25
    HIT_RADIUS = 0.5

    def is_wall(mx, my):
        if mx < 0 or my < 0 or mx >= MAP_W or my >= MAP_H:
            return True
        return MAP[my][mx] == '#'

    class Enemy:
        def __init__(self, x, y):
            self.x, self.y, self.alive = x, y, True

    def cast_ray(px, py, angle):
        sin_a, cos_a = math.sin(angle), math.cos(angle)
        map_x, map_y = int(px), int(py)
        d_x = abs(1 / cos_a) if cos_a != 0 else 1e30
        d_y = abs(1 / sin_a) if sin_a != 0 else 1e30
        if cos_a < 0:
            step_x = -1; side_x = (px - map_x) * d_x
        else:
            step_x = 1; side_x = (map_x + 1 - px) * d_x
        if sin_a < 0:
            step_y = -1; side_y = (py - map_y) * d_y
        else:
            step_y = 1; side_y = (map_y + 1 - py) * d_y
        side = 0
        for _ in range(MAX_STEPS):
            if side_x < side_y:
                side_x += d_x; map_x += step_x; side = 0
            else:
                side_y += d_y; map_y += step_y; side = 1
            if is_wall(map_x, map_y):
                break
        if side == 0:
            dist = (map_x - px + (1 - step_x) / 2) / cos_a
        else:
            dist = (map_y - py + (1 - step_y) / 2) / sin_a
        return max(abs(dist), 0.0001), side

    def draw_column(x, dist, side):
        h = min(int(SCREEN_H / dist), SCREEN_H)
        y0 = (SCREEN_H - h) // 2
        step = 1 if dist < 2 else 2 if dist < 4 else 3
        if side == 1:
            step += 1
        for y in range(y0, y0 + h, step):
            display.hline(x, y, COL_W, 1)

    def project(px, py, pa, ex, ey, zbuf, max_dist):
        """Returns (screen_x, size, col) if ex,ey is visible, else None."""
        dx, dy = ex - px, ey - py
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.1 or dist > max_dist:
            return None
        ang_to = math.atan2(dy, dx) - pa
        while ang_to > math.pi: ang_to -= 2 * math.pi
        while ang_to < -math.pi: ang_to += 2 * math.pi
        if abs(ang_to) > FOV / 2 + 0.2:
            return None
        screen_x = int((0.5 + ang_to / FOV) * SCREEN_W)
        col = max(0, min(NUM_RAYS - 1, screen_x // COL_W))
        if dist > zbuf[col]:
            return None
        return screen_x, dist, col

    def draw_sprite(px, py, pa, ex, ey, zbuf):
        hit = project(px, py, pa, ex, ey, zbuf, 8)
        if not hit: return
        screen_x, dist, _ = hit
        size = int(SCREEN_H / dist * 0.6)
        x0, y0 = screen_x - size // 2, (SCREEN_H - size) // 2
        display.fill_rect(max(0, x0), max(0, y0), size, size, 1)
        display.fill_rect(max(0, x0 + size // 4), max(0, y0 + size // 4),
                           max(1, size // 2), max(1, size // 2), 0)

    def draw_bullet(px, py, pa, bx, by, zbuf):
        hit = project(px, py, pa, bx, by, zbuf, 8)
        if not hit: return
        screen_x, dist, _ = hit
        size = max(1, int(SCREEN_H / dist * 0.08))
        y0 = SCREEN_H // 2 - size // 2
        display.fill_rect(screen_x - size // 2, y0, size, size, 1)

    def find_open_tile():
        for y in range(MAP_H):
            for x in range(MAP_W):
                if MAP[y][x] == '.':
                    return x + 0.5, y + 0.5
        return 1.5, 1.5

    def draw_weapon(recoil, flash):
        # simple gun view-model: grip + barrel, bottom-center
        gy = SCREEN_H - 2 - recoil
        display.fill_rect(SCREEN_W // 2 - 3, gy - 14, 6, 14, 1)   # barrel
        display.fill_rect(SCREEN_W // 2 - 7, gy - 4, 14, 6, 1)    # grip/body
        if flash:
            fx, fy = SCREEN_W // 2, gy - 16
            display.fill_rect(fx - 4, fy - 4, 8, 8, 1)
            display.pixel(fx - 5, fy, 1)
            display.pixel(fx + 5, fy, 1)

    px, py = find_open_tile()
    pa = 0.0
    enemies = [Enemy(5.5, 2.5), Enemy(2.5, 5.5), Enemy(5.5, 5.5)]
    bullets = []   # each: [x, y, dx, dy, ttl]
    score = 0
    last_shot = 0
    recoil = 0

    while True:
        turn, move = read_axes()
        pa += turn * TURN_SPEED
        if move != 0:
            nx = px + math.cos(pa) * (-move) * MOVE_SPEED
            ny = py + math.sin(pa) * (-move) * MOVE_SPEED
            if not is_wall(int(nx), int(py)): px = nx
            if not is_wall(int(px), int(ny)): py = ny

        now = time.ticks_ms()
        flash = False
        if button() and time.ticks_diff(now, last_shot) > 300:
            last_shot = now
            recoil = 3
            flash = True
            noise_burst(45, 0.2)
            bullets.append([px, py, math.cos(pa) * BULLET_SPEED,
                             math.sin(pa) * BULLET_SPEED, BULLET_LIFE])
        if recoil > 0:
            recoil -= 1

        # advance bullets, check walls/enemy hits
        for b in bullets[:]:
            b[0] += b[2]; b[1] += b[3]; b[4] -= 1
            if b[4] <= 0 or is_wall(int(b[0]), int(b[1])):
                bullets.remove(b)
                continue
            for e in enemies:
                if e.alive and abs(e.x - b[0]) < HIT_RADIUS and abs(e.y - b[1]) < HIT_RADIUS:
                    e.alive = False
                    score += 1
                    if b in bullets: bullets.remove(b)
                    break

        display.fill(0)
        zbuf = [0.0] * NUM_RAYS
        for i in range(NUM_RAYS):
            ray_angle = pa - FOV / 2 + i * (FOV / NUM_RAYS)
            dist, side = cast_ray(px, py, ray_angle)
            zbuf[i] = dist * math.cos(ray_angle - pa)
            draw_column(i * COL_W, dist, side)

        for e in enemies:
            if e.alive:
                draw_sprite(px, py, pa, e.x, e.y, zbuf)
        for b in bullets:
            draw_bullet(px, py, pa, b[0], b[1], zbuf)

        draw_weapon(recoil, flash)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()

        if all(not e.alive for e in enemies):
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(16)


# ================================================================ SNAKE --
def play_snake(display):
    CELL = 4
    COLS, ROWS = SCREEN_W // CELL, SCREEN_H // CELL
    TICK_MS = 120

    snake = [(COLS // 2, ROWS // 2), (COLS // 2 - 1, ROWS // 2)]
    direction = (1, 0)
    food = (random.randrange(COLS), random.randrange(ROWS))
    score = 0
    last_move = time.ticks_ms()

    while True:
        d = read_dir()
        if d == 'U' and direction != (0, 1): direction = (0, -1)
        elif d == 'D' and direction != (0, -1): direction = (0, 1)
        elif d == 'L' and direction != (1, 0): direction = (-1, 0)
        elif d == 'R' and direction != (-1, 0): direction = (1, 0)

        now = time.ticks_ms()
        if time.ticks_diff(now, last_move) >= TICK_MS:
            last_move = now
            hx, hy = snake[0]
            nx, ny = (hx + direction[0]) % COLS, (hy + direction[1]) % ROWS
            if (nx, ny) in snake:
                game_over_screen(display, "GAME OVER", score)
                return score
            snake.insert(0, (nx, ny))
            if (nx, ny) == food:
                score += 1
                while food in snake:
                    food = (random.randrange(COLS), random.randrange(ROWS))
            else:
                snake.pop()

        display.fill(0)
        fx, fy = food
        display.fill_rect(fx * CELL, fy * CELL, CELL, CELL, 1)
        for sx, sy in snake:
            display.fill_rect(sx * CELL, sy * CELL, CELL - 1, CELL - 1, 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# ================================================================= PONG --
def play_pong(display):
    PADDLE_H = 14
    PADDLE_W = 3
    WIN_SCORE = 5

    player_y = SCREEN_H // 2 - PADDLE_H // 2
    cpu_y = SCREEN_H // 2 - PADDLE_H // 2
    ball_x, ball_y = SCREEN_W // 2, SCREEN_H // 2
    vx, vy = -2, 1
    player_score, cpu_score = 0, 0

    while True:
        _, y = read_axes()
        player_y += int(y * 4)
        player_y = max(0, min(SCREEN_H - PADDLE_H, player_y))

        target = ball_y - PADDLE_H // 2
        if cpu_y < target: cpu_y += 2
        elif cpu_y > target: cpu_y -= 2
        cpu_y = max(0, min(SCREEN_H - PADDLE_H, cpu_y))

        ball_x += vx
        ball_y += vy
        if ball_y <= 0 or ball_y >= SCREEN_H - 1:
            vy = -vy

        if ball_x <= PADDLE_W and cpu_y <= ball_y <= cpu_y + PADDLE_H:
            vx = -vx
        elif ball_x >= SCREEN_W - PADDLE_W - 1 and player_y <= ball_y <= player_y + PADDLE_H:
            vx = -vx

        if ball_x < 0:
            player_score += 1
            ball_x, ball_y, vx, vy = SCREEN_W // 2, SCREEN_H // 2, 2, 1
        elif ball_x > SCREEN_W:
            cpu_score += 1
            ball_x, ball_y, vx, vy = SCREEN_W // 2, SCREEN_H // 2, -2, 1

        display.fill(0)
        display.fill_rect(0, cpu_y, PADDLE_W, PADDLE_H, 1)
        display.fill_rect(SCREEN_W - PADDLE_W, player_y, PADDLE_W, PADDLE_H, 1)
        display.fill_rect(ball_x, ball_y, 2, 2, 1)
        display.text("{}-{}".format(cpu_score, player_score), SCREEN_W // 2 - 10, 0, 1)
        display.show()

        if player_score >= WIN_SCORE:
            game_over_screen(display, "YOU WIN")
            return player_score
        if cpu_score >= WIN_SCORE:
            game_over_screen(display, "CPU WINS")
            return player_score
        time.sleep_ms(20)


# ============================================================= BREAKOUT --
def play_breakout(display):
    PADDLE_W, PADDLE_H = 20, 2
    BRICK_W, BRICK_H = 14, 4
    COLS = SCREEN_W // BRICK_W

    paddle_x = SCREEN_W // 2 - PADDLE_W // 2
    ball_x, ball_y = SCREEN_W // 2, SCREEN_H - 10
    vx, vy = 1, -1
    bricks = [[True] * COLS for _ in range(4)]
    score = 0

    while True:
        x, _ = read_axes()
        paddle_x += int(x * 4)
        paddle_x = max(0, min(SCREEN_W - PADDLE_W, paddle_x))

        ball_x += vx
        ball_y += vy
        if ball_x <= 0 or ball_x >= SCREEN_W - 1:
            vx = -vx
        if ball_y <= 0:
            vy = -vy

        if ball_y >= SCREEN_H - PADDLE_H - 2 and paddle_x <= ball_x <= paddle_x + PADDLE_W:
            vy = -vy
        elif ball_y > SCREEN_H:
            game_over_screen(display, "GAME OVER", score)
            return score

        row = int(ball_y // BRICK_H)
        col = int(ball_x // BRICK_W)
        if 0 <= row < len(bricks) and 0 <= col < COLS and bricks[row][col]:
            bricks[row][col] = False
            vy = -vy
            score += 1

        display.fill(0)
        for r, row_bricks in enumerate(bricks):
            for c, alive in enumerate(row_bricks):
                if alive:
                    display.fill_rect(c * BRICK_W, r * BRICK_H, BRICK_W - 1, BRICK_H - 1, 1)
        display.fill_rect(paddle_x, SCREEN_H - PADDLE_H, PADDLE_W, PADDLE_H, 1)
        display.fill_rect(ball_x, ball_y, 2, 2, 1)
        display.show()

        if score == sum(len(r) for r in bricks):
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(20)


# =============================================================== TETRIS --
def play_tetris(display):
    CELL = 4
    COLS, ROWS = 10, 16
    OFFSET_X = (SCREEN_W - COLS * CELL) // 2
    PIECES = {
        'I': [(0, 1), (1, 1), (2, 1), (3, 1)],
        'O': [(1, 0), (2, 0), (1, 1), (2, 1)],
        'T': [(1, 0), (0, 1), (1, 1), (2, 1)],
        'S': [(1, 0), (2, 0), (0, 1), (1, 1)],
        'Z': [(0, 0), (1, 0), (1, 1), (2, 1)],
        'L': [(0, 0), (0, 1), (1, 1), (2, 1)],
        'J': [(2, 0), (0, 1), (1, 1), (2, 1)],
    }

    def rotate(cells):
        return [(y, 3 - x) for x, y in cells]

    def collides(cells, ox, oy, grid):
        for cx, cy in cells:
            x, y = ox + cx, oy + cy
            if x < 0 or x >= COLS or y >= ROWS:
                return True
            if y >= 0 and grid[y][x]:
                return True
        return False

    grid = [[0] * COLS for _ in range(ROWS)]
    score = 0
    piece = random.choice(list(PIECES.values()))
    px, py = 3, -1
    drop_ms = 400
    last_drop = time.ticks_ms()
    last_move = time.ticks_ms()

    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 140:
            last_move = now
            if d == 'L' and not collides(piece, px - 1, py, grid): px -= 1
            elif d == 'R' and not collides(piece, px + 1, py, grid): px += 1
            elif d == 'D': drop_ms = 60
        else:
            drop_ms = 400

        if button() and time.ticks_diff(now, last_move) > 200:
            last_move = now
            rotated = rotate(piece)
            if not collides(rotated, px, py, grid):
                piece = rotated

        if time.ticks_diff(now, last_drop) > drop_ms:
            last_drop = now
            if not collides(piece, px, py + 1, grid):
                py += 1
            else:
                for cx, cy in piece:
                    if py + cy < 0:
                        game_over_screen(display, "GAME OVER", score)
                        return score
                    grid[py + cy][px + cx] = 1
                new_grid = [row for row in grid if not all(row)]
                cleared = ROWS - len(new_grid)
                score += cleared * 10
                for _ in range(cleared):
                    new_grid.insert(0, [0] * COLS)
                grid = new_grid
                piece = random.choice(list(PIECES.values()))
                px, py = 3, -1

        display.fill(0)
        for y in range(ROWS):
            for x in range(COLS):
                if grid[y][x]:
                    display.fill_rect(OFFSET_X + x * CELL, y * CELL, CELL - 1, CELL - 1, 1)
        for cx, cy in piece:
            if py + cy >= 0:
                display.fill_rect(OFFSET_X + (px + cx) * CELL, (py + cy) * CELL, CELL - 1, CELL - 1, 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# =============================================================== FLAPPY --
def play_flappy(display):
    GAP = 20
    PIPE_W = 6
    GRAVITY = 0.35
    FLAP = -3.0

    bird_y, vel = SCREEN_H // 2, 0.0
    pipes = [[SCREEN_W, random.randint(10, SCREEN_H - GAP - 10)]]
    score = 0
    last_press = False

    while True:
        pressed = button()
        if pressed and not last_press:
            vel = FLAP
        last_press = pressed

        vel += GRAVITY
        bird_y += vel
        if bird_y < 0 or bird_y >= SCREEN_H:
            game_over_screen(display, "GAME OVER", score)
            return score

        for p in pipes:
            p[0] -= 2
        if pipes[-1][0] < SCREEN_W - 50:
            pipes.append([SCREEN_W, random.randint(10, SCREEN_H - GAP - 10)])
        if pipes[0][0] < -PIPE_W:
            pipes.pop(0)
            score += 1

        bird_x = 20
        for px, gap_y in pipes:
            if px < bird_x + 2 and px + PIPE_W > bird_x:
                if bird_y < gap_y or bird_y > gap_y + GAP:
                    game_over_screen(display, "GAME OVER", score)
                    return score

        display.fill(0)
        display.fill_rect(bird_x, int(bird_y), 3, 3, 1)
        for px, gap_y in pipes:
            display.fill_rect(px, 0, PIPE_W, gap_y, 1)
            display.fill_rect(px, gap_y + GAP, PIPE_W, SCREEN_H - (gap_y + GAP), 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(30)


# ============================================================= INVADERS --
def play_invaders(display):
    ROWS, COLS = 3, 8
    SPACING_X, SPACING_Y = 14, 8

    enemies = [[True] * COLS for _ in range(ROWS)]
    ex_off, ey_off = 4, 4
    e_dir = 1
    player_x = SCREEN_W // 2
    bullet = None
    enemy_bullet = None
    score = 0
    last_shot = 0
    last_enemy_shot = 0

    while True:
        x, _ = read_axes()
        player_x += int(x * 3)
        player_x = max(2, min(SCREEN_W - 2, player_x))

        now = time.ticks_ms()
        if button() and bullet is None and time.ticks_diff(now, last_shot) > 250:
            bullet = [player_x, SCREEN_H - 6]
            last_shot = now

        if bullet:
            bullet[1] -= 3
            if bullet[1] < 0:
                bullet = None

        hit_edge = False
        for r in range(ROWS):
            for c in range(COLS):
                if enemies[r][c]:
                    ex = ex_off + c * SPACING_X
                    if ex <= 2 or ex >= SCREEN_W - 2:
                        hit_edge = True
        if hit_edge:
            e_dir = -e_dir
            ey_off += 4
        ex_off += e_dir

        if ey_off > SCREEN_H - 12:
            game_over_screen(display, "GAME OVER", score)
            return score

        if bullet:
            for r in range(ROWS):
                for c in range(COLS):
                    if enemies[r][c]:
                        ex, ey = ex_off + c * SPACING_X, ey_off + r * SPACING_Y
                        if abs(bullet[0] - ex) < 5 and abs(bullet[1] - ey) < 4:
                            enemies[r][c] = False
                            bullet = None
                            score += 1
                            break

        if time.ticks_diff(now, last_enemy_shot) > 900 and enemy_bullet is None:
            alive = [(r, c) for r in range(ROWS) for c in range(COLS) if enemies[r][c]]
            if alive:
                r, c = random.choice(alive)
                enemy_bullet = [ex_off + c * SPACING_X, ey_off + r * SPACING_Y]
                last_enemy_shot = now

        if enemy_bullet:
            enemy_bullet[1] += 2
            if abs(enemy_bullet[0] - player_x) < 3 and enemy_bullet[1] > SCREEN_H - 6:
                game_over_screen(display, "GAME OVER", score)
                return score
            if enemy_bullet[1] > SCREEN_H:
                enemy_bullet = None

        display.fill(0)
        for r in range(ROWS):
            for c in range(COLS):
                if enemies[r][c]:
                    display.fill_rect(ex_off + c * SPACING_X, ey_off + r * SPACING_Y, 6, 3, 1)
        display.fill_rect(player_x - 3, SCREEN_H - 3, 6, 2, 1)
        if bullet:
            display.pixel(bullet[0], bullet[1], 1)
        if enemy_bullet:
            display.pixel(enemy_bullet[0], enemy_bullet[1], 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()

        if not any(any(row) for row in enemies):
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(25)


# =============================================================== MAZE ----
def play_maze(display):
    MAP = [
        "############",
        "#..........#",
        "#.##.##.##.#",
        "#..........#",
        "#.##.##.##.#",
        "#..........#",
        "############",
    ]
    ROWS, COLS = len(MAP), len(MAP[0])
    CELL = SCREEN_W // COLS

    def open_tiles():
        return [(x, y) for y in range(ROWS) for x in range(COLS) if MAP[y][x] != '#']

    dots = set(open_tiles())
    px, py = COLS // 2, ROWS // 2
    dots.discard((px, py))
    gx, gy = 1, 1
    score = 0
    last_move = time.ticks_ms()
    last_ghost = time.ticks_ms()

    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 150:
            last_move = now
            nx, ny = px, py
            if d == 'U': ny -= 1
            elif d == 'D': ny += 1
            elif d == 'L': nx -= 1
            elif d == 'R': nx += 1
            if MAP[ny][nx] != '#':
                px, py = nx, ny
                if (px, py) in dots:
                    dots.discard((px, py))
                    score += 1

        if time.ticks_diff(now, last_ghost) > 250:
            last_ghost = now
            options = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = gx + dx, gy + dy
                if 0 <= ny < ROWS and MAP[ny][nx] != '#':
                    options.append((nx, ny))
            if options:
                options.sort(key=lambda p: abs(p[0] - px) + abs(p[1] - py))
                gx, gy = options[0] if random.random() < 0.6 else random.choice(options)

        if (gx, gy) == (px, py):
            game_over_screen(display, "CAUGHT!", score)
            return score

        display.fill(0)
        for y in range(ROWS):
            for x in range(COLS):
                if MAP[y][x] == '#':
                    display.fill_rect(x * CELL, y * CELL, CELL, CELL, 1)
        for dx, dy in dots:
            display.pixel(dx * CELL + CELL // 2, dy * CELL + CELL // 2, 1)
        display.fill_rect(px * CELL + 1, py * CELL + 1, CELL - 2, CELL - 2, 1)
        display.fill_rect(gx * CELL + 2, gy * CELL + 2, CELL - 4, CELL - 4, 1)
        display.show()

        if not dots:
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(16)


# ============================================================= REACTION --
def play_reaction(display):
    ROUNDS = 5
    times = []
    for round_num in range(ROUNDS):
        display.fill(0)
        centered_text(display, "Round {}/{}".format(round_num + 1, ROUNDS), 20)
        centered_text(display, "wait...", 36)
        display.show()
        wait_release()
        time.sleep_ms(random.randint(1000, 3000))

        if button():
            display.fill(0)
            centered_text(display, "TOO SOON!", 28)
            display.show()
            time.sleep(1)
            times.append(9999)
            continue

        display.fill(0)
        centered_text(display, "GO!", 28)
        display.show()
        start = time.ticks_ms()
        wait_for_press(timeout_ms=3000)
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        times.append(elapsed)
        wait_release()

        display.fill(0)
        centered_text(display, "{} ms".format(elapsed), 28)
        display.show()
        time.sleep(1)

    avg = sum(times) // len(times)
    game_over_screen(display, "Avg: {}ms".format(avg))
    return avg


# ================================================================ SIMON --
def play_simon(display):
    DIRS = ['U', 'D', 'L', 'R']
    ARROW_POS = {'U': (60, 10), 'D': (60, 46), 'L': (10, 28), 'R': (110, 28)}

    def show_arrows(lit=None):
        display.fill(0)
        for d, (x, y) in ARROW_POS.items():
            display.text(d, x, y, 1)
            if d == lit:
                display.fill_rect(x - 4, y - 4, 16, 16, 1)
                display.text(d, x, y, 0)
        display.show()

    sequence = []
    while True:
        sequence.append(random.choice(DIRS))

        for step in sequence:
            show_arrows(step)
            time.sleep_ms(450)
            show_arrows()
            time.sleep_ms(150)

        for step in sequence:
            got = None
            start = time.ticks_ms()
            while got is None:
                got = read_dir()
                if time.ticks_diff(time.ticks_ms(), start) > 4000:
                    game_over_screen(display, "TOO SLOW", len(sequence) - 1)
                    return len(sequence) - 1
                time.sleep_ms(10)
            show_arrows(got)
            time.sleep_ms(150)
            if got != step:
                game_over_screen(display, "WRONG!", len(sequence) - 1)
                return len(sequence) - 1
            while read_dir() is not None:
                time.sleep_ms(10)

        time.sleep_ms(400)


# ============================================================= ASTEROIDS --
def play_asteroids(display):
    ship_x, ship_y, angle = SCREEN_W / 2, SCREEN_H / 2, 0.0
    vx, vy = 0.0, 0.0
    bullets = []
    rocks = [[random.randint(0, SCREEN_W), random.randint(0, SCREEN_H),
              random.uniform(-1, 1), random.uniform(-1, 1), 6] for _ in range(5)]
    score, last_shot = 0, 0

    while True:
        turn, thrust = read_axes()
        angle += turn * 0.15
        if thrust < -0.3:
            vx += math.cos(angle) * 0.15
            vy += math.sin(angle) * 0.15
        vx *= 0.98; vy *= 0.98
        ship_x = (ship_x + vx) % SCREEN_W
        ship_y = (ship_y + vy) % SCREEN_H

        now = time.ticks_ms()
        if button() and time.ticks_diff(now, last_shot) > 250:
            last_shot = now
            bullets.append([ship_x, ship_y, math.cos(angle) * 3, math.sin(angle) * 3, 30])
        for b in bullets:
            b[0] = (b[0] + b[2]) % SCREEN_W
            b[1] = (b[1] + b[3]) % SCREEN_H
            b[4] -= 1
        bullets[:] = [b for b in bullets if b[4] > 0]
        for r in rocks:
            r[0] = (r[0] + r[2]) % SCREEN_W
            r[1] = (r[1] + r[3]) % SCREEN_H

        for b in bullets[:]:
            for r in rocks[:]:
                if abs(b[0] - r[0]) < r[4] and abs(b[1] - r[1]) < r[4]:
                    rocks.remove(r)
                    if b in bullets: bullets.remove(b)
                    score += 1
                    if r[4] > 3:
                        rocks.append([r[0], r[1], random.uniform(-1, 1), random.uniform(-1, 1), r[4] // 2])
                        rocks.append([r[0], r[1], random.uniform(-1, 1), random.uniform(-1, 1), r[4] // 2])
                    break

        for r in rocks:
            if abs(ship_x - r[0]) < r[4] and abs(ship_y - r[1]) < r[4]:
                game_over_screen(display, "GAME OVER", score)
                return score

        display.fill(0)
        p1 = (ship_x + math.cos(angle) * 4, ship_y + math.sin(angle) * 4)
        p2 = (ship_x + math.cos(angle + 2.5) * 4, ship_y + math.sin(angle + 2.5) * 4)
        p3 = (ship_x + math.cos(angle - 2.5) * 4, ship_y + math.sin(angle - 2.5) * 4)
        display.line(int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]), 1)
        display.line(int(p2[0]), int(p2[1]), int(p3[0]), int(p3[1]), 1)
        display.line(int(p3[0]), int(p3[1]), int(p1[0]), int(p1[1]), 1)
        for b in bullets:
            display.pixel(int(b[0]), int(b[1]), 1)
        for r in rocks:
            display.fill_rect(int(r[0] - r[4] / 2), int(r[1] - r[4] / 2), r[4], r[4], 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        if not rocks:
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(30)


# =============================================================== FROGGER --
def play_frogger(display):
    LANES = 6
    LANE_H = SCREEN_H // LANES
    px, py = SCREEN_W // 2, SCREEN_H - LANE_H // 2
    lanes = []
    for _ in range(LANES - 1):
        speed = random.choice([-2, -1, 1, 2])
        cars = [random.randint(0, SCREEN_W) for _ in range(2)]
        lanes.append([speed, cars])
    last_move = time.ticks_ms()

    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 150:
            last_move = now
            if d == 'U': py -= LANE_H
            elif d == 'D': py = min(SCREEN_H - LANE_H // 2, py + LANE_H)
            elif d == 'L': px = max(2, px - 6)
            elif d == 'R': px = min(SCREEN_W - 2, px + 6)

        for speed, cars in lanes:
            for i in range(len(cars)):
                cars[i] = (cars[i] + speed) % SCREEN_W

        lane_idx = py // LANE_H
        if 0 <= lane_idx < len(lanes):
            _, cars = lanes[lane_idx]
            for c in cars:
                if abs(px - c) < 6:
                    game_over_screen(display, "SQUASHED")
                    return 0

        display.fill(0)
        for li, (speed, cars) in enumerate(lanes):
            y = li * LANE_H + LANE_H // 2
            for c in cars:
                display.fill_rect(int(c), y - 2, 8, 4, 1)
        display.fill_rect(px - 2, py - 2, 4, 4, 1)
        display.show()
        if py <= LANE_H // 2:
            game_over_screen(display, "YOU WIN")
            return 1
        time.sleep_ms(16)


# ============================================================= TIC-TAC-TOE --
def play_tictactoe(display):
    board = [0] * 9
    cursor = 0

    def winner(b):
        for a, c, d in ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)):
            if b[a] != 0 and b[a] == b[c] == b[d]:
                return b[a]
        return 0

    def cpu_move():
        empties = [i for i in range(9) if board[i] == 0]
        for i in empties:
            board[i] = 2
            if winner(board) == 2: return
            board[i] = 0
        for i in empties:
            board[i] = 1
            if winner(board) == 1:
                board[i] = 0
                board[i] = 2
                return
            board[i] = 0
        board[random.choice(empties)] = 2

    CW = 20
    ox, oy = (SCREEN_W - 3 * CW) // 2, (SCREEN_H - 3 * CW) // 2
    while True:
        d = read_dir()
        if d == 'L': cursor = (cursor - 1) % 9
        elif d == 'R': cursor = (cursor + 1) % 9
        elif d == 'U': cursor = (cursor - 3) % 9
        elif d == 'D': cursor = (cursor + 3) % 9
        if button() and board[cursor] == 0:
            board[cursor] = 1
            wait_release()
            if winner(board) == 0 and 0 in board:
                cpu_move()

        display.fill(0)
        for i in range(9):
            cx, cy = ox + (i % 3) * CW, oy + (i // 3) * CW
            display.rect(cx, cy, CW - 2, CW - 2, 1)
            if board[i] == 1: display.text("X", cx + 6, cy + 6, 1)
            elif board[i] == 2: display.text("O", cx + 6, cy + 6, 1)
            if i == cursor and board[i] == 0:
                display.rect(cx + 1, cy + 1, CW - 4, CW - 4, 1)
        w = winner(board)
        if w or 0 not in board:
            display.show()
            msg = "YOU WIN" if w == 1 else "CPU WINS" if w == 2 else "DRAW"
            game_over_screen(display, msg)
            return 0
        display.show()
        time.sleep_ms(16)


# ============================================================ CONNECT FOUR --
def play_connect4(display):
    COLS, ROWS = 7, 6
    CW, CH = 16, 9
    ox, oy = (SCREEN_W - COLS * CW) // 2, SCREEN_H - ROWS * CH - 2
    grid = [[0] * ROWS for _ in range(COLS)]
    col_sel = COLS // 2

    def drop(b, col, player):
        for row in range(ROWS):
            if b[col][row] == 0:
                b[col][row] = player
                return row
        return -1

    def check_win(b, player):
        for c in range(COLS):
            for r in range(ROWS):
                if b[c][r] != player: continue
                for dc, dr in ((1, 0), (0, 1), (1, 1), (1, -1)):
                    cnt, cc, rr = 0, c, r
                    while 0 <= cc < COLS and 0 <= rr < ROWS and b[cc][rr] == player:
                        cnt += 1; cc += dc; rr += dr
                    if cnt >= 4: return True
        return False

    def cpu_move():
        valid = [c for c in range(COLS) if grid[c][ROWS - 1] == 0]
        for c in valid:
            r = drop(grid, c, 2)
            if check_win(grid, 2): return
            grid[c][r] = 0
        for c in valid:
            r = drop(grid, c, 1)
            if check_win(grid, 1):
                grid[c][r] = 0
                drop(grid, c, 2)
                return
            grid[c][r] = 0
        drop(grid, random.choice(valid), 2)

    last_move = time.ticks_ms()
    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 180:
            last_move = now
            if d == 'L': col_sel = (col_sel - 1) % COLS
            elif d == 'R': col_sel = (col_sel + 1) % COLS
        if button() and grid[col_sel][ROWS - 1] == 0:
            wait_release()
            drop(grid, col_sel, 1)
            if not check_win(grid, 1) and any(grid[c][ROWS - 1] == 0 for c in range(COLS)):
                cpu_move()

        display.fill(0)
        display.vline(ox + col_sel * CW + CW // 2, 0, oy - 2, 1)
        for c in range(COLS):
            for r in range(ROWS):
                cx, cy = ox + c * CW, oy + (ROWS - 1 - r) * CH
                display.rect(cx, cy, CW - 1, CH - 1, 1)
                if grid[c][r] == 1: display.fill_rect(cx + 2, cy + 2, CW - 5, CH - 5, 1)
                elif grid[c][r] == 2: display.rect(cx + 2, cy + 2, CW - 5, CH - 5, 1)
        if check_win(grid, 1):
            display.show(); game_over_screen(display, "YOU WIN"); return 0
        if check_win(grid, 2):
            display.show(); game_over_screen(display, "CPU WINS"); return 0
        if all(grid[c][ROWS - 1] != 0 for c in range(COLS)):
            display.show(); game_over_screen(display, "DRAW"); return 0
        display.show()
        time.sleep_ms(16)


# =================================================================== 2048 --
def play_2048(display):
    SIZE = 4
    grid = [[0] * SIZE for _ in range(SIZE)]
    score = 0

    def add_tile():
        empties = [(r, c) for r in range(SIZE) for c in range(SIZE) if grid[r][c] == 0]
        if empties:
            r, c = random.choice(empties)
            grid[r][c] = 2 if random.random() < 0.9 else 4

    def compress_merge(row):
        nonlocal score
        vals = [v for v in row if v != 0]
        merged, i = [], 0
        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                merged.append(vals[i] * 2); score += vals[i] * 2; i += 2
            else:
                merged.append(vals[i]); i += 1
        return merged + [0] * (SIZE - len(merged))

    def move(direction):
        changed = False
        if direction in ('L', 'R'):
            for r in range(SIZE):
                row = grid[r][:]
                if direction == 'R': row = row[::-1]
                newrow = compress_merge(row)
                if direction == 'R': newrow = newrow[::-1]
                if newrow != grid[r]: changed = True
                grid[r] = newrow
        else:
            for c in range(SIZE):
                col = [grid[r][c] for r in range(SIZE)]
                if direction == 'D': col = col[::-1]
                newcol = compress_merge(col)
                if direction == 'D': newcol = newcol[::-1]
                for r in range(SIZE):
                    if grid[r][c] != newcol[r]: changed = True
                    grid[r][c] = newcol[r]
        return changed

    add_tile(); add_tile()
    CW, CH = 30, 15
    ox, oy = (SCREEN_W - SIZE * CW) // 2, (SCREEN_H - SIZE * CH) // 2
    last_move = time.ticks_ms()
    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 200:
            last_move = now
            if move(d): add_tile()

        display.fill(0)
        for r in range(SIZE):
            for c in range(SIZE):
                cx, cy = ox + c * CW, oy + r * CH
                display.rect(cx, cy, CW - 2, CH - 2, 1)
                if grid[r][c]:
                    display.text(str(grid[r][c]), cx + 2, cy + 3, 1)
        display.show()

        if all(grid[r][c] != 0 for r in range(SIZE) for c in range(SIZE)):
            moves_left = False
            for dr, dc in ((0, 1), (1, 0)):
                for r in range(SIZE):
                    for c in range(SIZE):
                        nr, nc = r + dr, c + dc
                        if nr < SIZE and nc < SIZE and grid[r][c] == grid[nr][nc]:
                            moves_left = True
            if not moves_left:
                game_over_screen(display, "GAME OVER", score)
                return score
        time.sleep_ms(16)


# ============================================================ MEMORY MATCH --
def play_memory(display):
    COLS, ROWS = 4, 3
    pairs = list(range(1, 7)) * 2
    random.shuffle(pairs)
    revealed = [False] * 12
    matched = [False] * 12
    cursor, first, score = 0, None, 0
    wait_timer, pending = 0, None
    CW, CH = 30, 20
    ox, oy = (SCREEN_W - COLS * CW) // 2, (SCREEN_H - ROWS * CH) // 2

    while True:
        d = read_dir()
        if d == 'L': cursor = (cursor - 1) % 12
        elif d == 'R': cursor = (cursor + 1) % 12
        elif d == 'U': cursor = (cursor - COLS) % 12
        elif d == 'D': cursor = (cursor + COLS) % 12

        if button() and not matched[cursor] and not revealed[cursor] and wait_timer == 0:
            revealed[cursor] = True
            wait_release()
            if first is None:
                first = cursor
            else:
                if pairs[first] == pairs[cursor] and first != cursor:
                    matched[first] = matched[cursor] = True
                    score += 1
                    first = None
                else:
                    wait_timer = time.ticks_ms()
                    pending = (first, cursor)
                    first = None

        if wait_timer and time.ticks_diff(time.ticks_ms(), wait_timer) > 500:
            revealed[pending[0]] = False
            revealed[pending[1]] = False
            wait_timer = 0

        display.fill(0)
        for i in range(12):
            r, c = divmod(i, COLS)
            cx, cy = ox + c * CW, oy + r * CH
            display.rect(cx, cy, CW - 2, CH - 2, 1)
            if matched[i] or revealed[i]:
                display.text(str(pairs[i]), cx + 8, cy + 6, 1)
            if i == cursor:
                display.rect(cx + 1, cy + 1, CW - 4, CH - 4, 1)
        display.show()
        if all(matched):
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(16)


# ============================================================ WHACK-A-MOLE --
def play_whack(display):
    cursor = random.randrange(9)
    mole = random.randrange(9)
    mole_timer = time.ticks_ms()
    score = 0
    start = time.ticks_ms()
    DURATION = 20000
    CW, CH = SCREEN_W // 3, SCREEN_H // 3

    while time.ticks_diff(time.ticks_ms(), start) < DURATION:
        d = read_dir()
        if d == 'L': cursor = (cursor - 1) % 9
        elif d == 'R': cursor = (cursor + 1) % 9
        elif d == 'U': cursor = (cursor - 3) % 9
        elif d == 'D': cursor = (cursor + 3) % 9
        if button() and cursor == mole:
            score += 1
            mole = random.randrange(9)
            mole_timer = time.ticks_ms()
            wait_release()
        if time.ticks_diff(time.ticks_ms(), mole_timer) > 900:
            mole = random.randrange(9)
            mole_timer = time.ticks_ms()

        display.fill(0)
        for i in range(9):
            r, c = divmod(i, 3)
            cx, cy = c * CW, r * CH
            display.rect(cx + 2, cy + 2, CW - 4, CH - 4, 1)
            if i == mole:
                display.fill_rect(cx + 8, cy + 6, CW - 16, CH - 12, 1)
            if i == cursor:
                display.rect(cx, cy, CW, CH, 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(16)
    game_over_screen(display, "TIME UP", score)
    return score


# ============================================================ LUNAR LANDER --
def play_lander(display):
    x, y, vy = SCREEN_W / 2, 10.0, 0.0
    fuel = 100
    pad_x = random.randint(20, SCREEN_W - 20)
    pad_w = 16
    GRAVITY, THRUST = 0.05, -0.15

    while True:
        tx, _ = read_axes()
        x = max(2, min(SCREEN_W - 2, x + tx * 2))
        if button() and fuel > 0:
            vy += THRUST
            fuel -= 1
        vy += GRAVITY
        y += vy

        display.fill(0)
        display.hline(pad_x - pad_w // 2, SCREEN_H - 2, pad_w, 1)
        display.fill_rect(int(x) - 2, int(y) - 2, 4, 4, 1)
        display.text("F:{}".format(fuel), 0, 0, 1)
        display.show()

        if y >= SCREEN_H - 4:
            if pad_x - pad_w // 2 <= x <= pad_x + pad_w // 2 and abs(vy) < 1.5:
                game_over_screen(display, "LANDED!", fuel)
            else:
                game_over_screen(display, "CRASHED")
            return fuel
        time.sleep_ms(30)


# ================================================== ROCK PAPER SCISSORS --
def play_rps(display):
    choices = ["ROCK", "PAPER", "SCSR"]
    sel, wins, losses = 0, 0, 0

    while wins < 3 and losses < 3:
        d = read_dir()
        if d == 'L': sel = (sel - 1) % 3
        elif d == 'R': sel = (sel + 1) % 3

        display.fill(0)
        centered_text(display, "W:{} L:{}".format(wins, losses), 4)
        for i, c in enumerate(choices):
            prefix = "> " if i == sel else "  "
            display.text(prefix + c, 36, 20 + i * 12, 1)
        display.show()

        if button():
            wait_release()
            cpu = random.randrange(3)
            if sel == cpu:
                result = 0
            elif (sel - cpu) % 3 == 1:
                result = 1
            else:
                result = -1
            if result == 1: wins += 1
            elif result == -1: losses += 1
            display.fill(0)
            centered_text(display, "You:{} CPU:{}".format(choices[sel], choices[cpu]), 20)
            centered_text(display, "WIN" if result == 1 else "LOSE" if result == -1 else "TIE", 36)
            display.show()
            time.sleep(1)
        time.sleep_ms(16)

    game_over_screen(display, "YOU WIN" if wins > losses else "CPU WINS", wins)
    return wins


# =============================================================== DINO RUN --
def play_dinorun(display):
    y, vy, jumping = SCREEN_H - 10, 0.0, False
    GRAVITY = 0.5
    obstacles = [SCREEN_W]
    score, speed = 0, 2.0
    dino_x = 10

    while True:
        if button() and not jumping:
            vy, jumping = -5, True
        if jumping:
            vy += GRAVITY
            y += vy
            if y >= SCREEN_H - 10:
                y, jumping, vy = SCREEN_H - 10, False, 0

        for i in range(len(obstacles)):
            obstacles[i] -= speed
        if obstacles[0] < -4:
            obstacles.pop(0)
            score += 1
            speed = min(6, speed + 0.1)
        if obstacles[-1] < SCREEN_W - 40:
            obstacles.append(SCREEN_W + random.randint(0, 30))

        for ox in obstacles:
            if abs(ox - dino_x) < 5 and y > SCREEN_H - 14:
                game_over_screen(display, "GAME OVER", score)
                return score

        display.fill(0)
        display.hline(0, SCREEN_H - 4, SCREEN_W, 1)
        display.fill_rect(dino_x, int(y) - 6, 6, 6, 1)
        for ox in obstacles:
            display.fill_rect(int(ox), SCREEN_H - 10, 4, 6, 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(20)


# ============================================================ DOOM MAZE --
def play_doommaze(display):
    W, H = 6, 6

    def generate_maze(w, h):
        grid = [['#'] * (2 * w + 1) for _ in range(2 * h + 1)]
        visited = [[False] * w for _ in range(h)]
        stack = [(0, 0)]
        visited[0][0] = True
        grid[1][1] = '.'
        while stack:
            cx, cy = stack[-1]
            dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
            random.shuffle(dirs)
            moved = False
            for dx, dy in dirs:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx]:
                    visited[ny][nx] = True
                    grid[2 * cy + 1 + dy][2 * cx + 1 + dx] = '.'
                    grid[2 * ny + 1][2 * nx + 1] = '.'
                    stack.append((nx, ny))
                    moved = True
                    break
            if not moved:
                stack.pop()
        return [''.join(row) for row in grid]

    MAP = generate_maze(W, H)
    MAP_W, MAP_H = len(MAP[0]), len(MAP)
    goal_x, goal_y = MAP_W - 2 + 0.5, MAP_H - 2 + 0.5

    def is_wall(mx, my):
        if mx < 0 or my < 0 or mx >= MAP_W or my >= MAP_H:
            return True
        return MAP[my][mx] == '#'

    FOV = math.radians(60)
    NUM_RAYS = 64
    COL_W = SCREEN_W // NUM_RAYS
    MAX_STEPS = 30
    MOVE_SPEED = 0.07
    TURN_SPEED = 0.07

    def cast_ray(px, py, angle):
        sin_a, cos_a = math.sin(angle), math.cos(angle)
        map_x, map_y = int(px), int(py)
        d_x = abs(1 / cos_a) if cos_a != 0 else 1e30
        d_y = abs(1 / sin_a) if sin_a != 0 else 1e30
        if cos_a < 0:
            step_x = -1; side_x = (px - map_x) * d_x
        else:
            step_x = 1; side_x = (map_x + 1 - px) * d_x
        if sin_a < 0:
            step_y = -1; side_y = (py - map_y) * d_y
        else:
            step_y = 1; side_y = (map_y + 1 - py) * d_y
        side = 0
        for _ in range(MAX_STEPS):
            if side_x < side_y:
                side_x += d_x; map_x += step_x; side = 0
            else:
                side_y += d_y; map_y += step_y; side = 1
            if is_wall(map_x, map_y):
                break
        if side == 0:
            dist = (map_x - px + (1 - step_x) / 2) / cos_a
        else:
            dist = (map_y - py + (1 - step_y) / 2) / sin_a
        return max(abs(dist), 0.0001), side

    def draw_column(x, dist, side):
        h = min(int(SCREEN_H / dist), SCREEN_H)
        y0 = (SCREEN_H - h) // 2
        step = 1 if dist < 2 else 2 if dist < 4 else 3
        if side == 1:
            step += 1
        for y in range(y0, y0 + h, step):
            display.hline(x, y, COL_W, 1)

    def draw_goal(px, py, pa, zbuf):
        dx, dy = goal_x - px, goal_y - py
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.2 or dist > 14:
            return
        ang_to = math.atan2(dy, dx) - pa
        while ang_to > math.pi: ang_to -= 2 * math.pi
        while ang_to < -math.pi: ang_to += 2 * math.pi
        if abs(ang_to) > FOV / 2 + 0.2:
            return
        screen_x = int((0.5 + ang_to / FOV) * SCREEN_W)
        size = max(2, int(SCREEN_H / dist * 0.5))
        col = max(0, min(NUM_RAYS - 1, screen_x // COL_W))
        if dist > zbuf[col]:
            return
        x0, y0 = screen_x - size // 2, SCREEN_H - size - 2
        display.rect(x0, y0, size, size, 1)
        display.line(x0 + size // 2, y0, x0 + size // 2, max(0, y0 - 6), 1)

    px, py, pa = 1.5, 1.5, 0.0
    start = time.ticks_ms()
    blink = 0
    CAM_OFFSET = 0.45  # how far back the camera sits behind the player

    while True:
        turn, move = read_axes()
        pa += turn * TURN_SPEED
        if move != 0:
            nx = px + math.cos(pa) * (-move) * MOVE_SPEED
            ny = py + math.sin(pa) * (-move) * MOVE_SPEED
            if not is_wall(int(nx), int(py)): px = nx
            if not is_wall(int(px), int(ny)): py = ny

        # camera sits behind the player (over-the-shoulder) unless that
        # would put it inside a wall, in which case fall back to first-person
        cam_x = px - math.cos(pa) * CAM_OFFSET
        cam_y = py - math.sin(pa) * CAM_OFFSET
        if is_wall(int(cam_x), int(cam_y)):
            cam_x, cam_y = px, py

        display.fill(0)
        zbuf = [0.0] * NUM_RAYS
        for i in range(NUM_RAYS):
            ray_angle = pa - FOV / 2 + i * (FOV / NUM_RAYS)
            dist, side = cast_ray(cam_x, cam_y, ray_angle)
            zbuf[i] = dist * math.cos(ray_angle - pa)
            draw_column(i * COL_W, dist, side)

        blink += 1
        if (blink // 10) % 2 == 0:
            draw_goal(cam_x, cam_y, pa, zbuf)

        # character silhouette, bottom-center - gives the over-the-shoulder feel
        display.fill_rect(SCREEN_W // 2 - 9, SCREEN_H - 9, 18, 9, 1)
        display.fill_rect(SCREEN_W // 2 - 4, SCREEN_H - 15, 8, 7, 1)

        elapsed = time.ticks_diff(time.ticks_ms(), start) // 1000
        display.text("T:{}s".format(elapsed), 0, 0, 1)
        display.show()

        if abs(px - goal_x) < 0.4 and abs(py - goal_y) < 0.4:
            game_over_screen(display, "ESCAPED!", elapsed)
            return elapsed
        time.sleep_ms(16)


# ================================================================ RACER --
def play_racer(display):
    HORIZON = 20
    MAX_HALF_WIDTH = 50
    player_x = 0.0
    speed = 1.0
    MAX_SPEED = 3.0
    distance = 0.0
    obstacles = []
    lives = 3
    invuln = 0

    while True:
        turn, accel = read_axes()
        if accel < -0.2 or button():
            speed = min(MAX_SPEED, speed + 0.08)
        else:
            speed = max(0.6, speed - 0.04)
        player_x += turn * 0.12
        player_x = max(-1.6, min(1.6, player_x))

        distance += speed
        curve = math.sin(distance * 0.01) * 1.4
        if abs(player_x - curve * 0.3) > 1.1:
            speed = max(0.4, speed - 0.08)

        if not obstacles or obstacles[-1][0] < distance + 60:
            obstacles.append([distance + 90, random.choice([-1, 0, 1])])
        for ob in obstacles[:]:
            if ob[0] < distance - 5:
                obstacles.remove(ob)

        if invuln > 0:
            invuln -= 1
        else:
            for ob in obstacles:
                dz = ob[0] - distance
                if 0 < dz < 4 and abs(ob[1] - player_x) < 0.6:
                    lives -= 1
                    speed = 0.6
                    invuln = 40
                    if lives <= 0:
                        game_over_screen(display, "CRASHED", int(distance))
                        return int(distance)

        display.fill(0)
        display.hline(0, HORIZON, SCREEN_W, 1)
        for y in range(HORIZON, SCREEN_H):
            t = (y - HORIZON) / (SCREEN_H - HORIZON)
            width = int(t * t * MAX_HALF_WIDTH) + 4
            c_off = int((curve * (1 - t) * 30) - player_x * t * 40)
            cx = SCREEN_W // 2 + c_off
            lx = max(0, min(SCREEN_W - 1, cx - width))
            rx = max(0, min(SCREEN_W - 1, cx + width))
            display.pixel(lx, y, 1)
            display.pixel(rx, y, 1)
            if int(y + distance) % 8 < 4:
                display.pixel(max(0, min(SCREEN_W - 1, cx)), y, 1)

        for ob in obstacles:
            dz = ob[0] - distance
            if dz <= 0 or dz > 80:
                continue
            t = 1 - dz / 80
            size = max(2, int(t * t * 26))
            c_off = int((curve * (1 - t) * 30) - player_x * t * 40)
            ox = SCREEN_W // 2 + c_off + int(ob[1] * t * 40)
            oy = HORIZON + int(t * (SCREEN_H - HORIZON)) - size
            display.rect(ox - size // 2, oy, size, size, 1)

        display.text("D:{} L:{}".format(int(distance), lives), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# =========================================================== PLATFORMER --
def play_platformer(display):
    GRAVITY = 0.4
    player_x, player_y = 10.0, 40.0
    vy = 0.0
    platforms = [(0, 56, 40), (50, 48, 30), (90, 56, 40),
                 (140, 40, 30), (180, 56, 50), (240, 46, 30)]
    coins = [(60, 38), (100, 46), (150, 30), (200, 46)]
    collected = set()
    score = 0
    goal_x = platforms[-1][0] + platforms[-1][2] - 10

    while True:
        tx, _ = read_axes()
        player_x += tx * 2
        on_ground = False
        if button() and vy == 0:
            for (px_, py_, pw) in platforms:
                if px_ <= player_x <= px_ + pw and abs(player_y - (py_ - 4)) < 2:
                    vy = -6
                    break
        vy += GRAVITY
        player_y += vy
        for (px_, py_, pw) in platforms:
            if px_ <= player_x <= px_ + pw and py_ - 6 <= player_y + 4 <= py_ + 4 and vy >= 0:
                player_y = py_ - 4
                vy = 0
                on_ground = True
        if player_y > SCREEN_H + 10:
            game_over_screen(display, "FELL!", score)
            return score

        camera_x = player_x - 30
        display.fill(0)
        for (px_, py_, pw) in platforms:
            sx = int(px_ - camera_x)
            ex = sx + pw
            if ex <= 0 or sx >= SCREEN_W:
                continue
            draw_x = max(0, sx)
            draw_w = min(SCREEN_W, ex) - draw_x
            if draw_w > 0:
                display.hline(draw_x, py_, draw_w, 1)
        for i, (cx, cy) in enumerate(coins):
            if i in collected:
                continue
            sx = int(cx - camera_x)
            if 0 <= sx < SCREEN_W:
                display.fill_rect(sx - 1, cy - 1, 3, 3, 1)
            if abs(cx - player_x) < 4 and abs(cy - player_y) < 6:
                collected.add(i)
                score += 1
        sx = int(player_x - camera_x)
        display.fill_rect(sx - 2, int(player_y) - 4, 4, 4, 1)
        display.text("C:{}".format(score), 0, 0, 1)
        display.show()

        if player_x > goal_x:
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(16)


# ============================================================== ZOMBIES --
def play_zombies(display):
    px, py = float(SCREEN_W // 2), float(SCREEN_H // 2)
    facing = 0.0
    bullets = []
    zombies = []
    score = 0
    wave = 1
    hp = 5
    last_shot = 0

    def spawn_wave(n):
        for _ in range(n):
            edge = random.randint(0, 3)
            if edge == 0: zx, zy = random.randint(0, SCREEN_W), 0
            elif edge == 1: zx, zy = random.randint(0, SCREEN_W), SCREEN_H
            elif edge == 2: zx, zy = 0, random.randint(0, SCREEN_H)
            else: zx, zy = SCREEN_W, random.randint(0, SCREEN_H)
            zombies.append([float(zx), float(zy)])

    spawn_wave(3)
    while True:
        tx, ty = read_axes()
        if tx or ty:
            facing = math.atan2(ty, tx)
            px += tx * 2
            py += ty * 2
        px = max(2, min(SCREEN_W - 2, px))
        py = max(2, min(SCREEN_H - 2, py))

        now = time.ticks_ms()
        if button() and time.ticks_diff(now, last_shot) > 200:
            last_shot = now
            bullets.append([px, py, math.cos(facing) * 4, math.sin(facing) * 4, 20])

        for b in bullets[:]:
            b[0] += b[2]; b[1] += b[3]; b[4] -= 1
            if b[4] <= 0 or b[0] < 0 or b[0] > SCREEN_W or b[1] < 0 or b[1] > SCREEN_H:
                bullets.remove(b)
                continue
            for z in zombies[:]:
                if abs(z[0] - b[0]) < 4 and abs(z[1] - b[1]) < 4:
                    zombies.remove(z)
                    score += 1
                    if b in bullets: bullets.remove(b)
                    break

        for z in zombies:
            dx, dy = px - z[0], py - z[1]
            d = math.sqrt(dx * dx + dy * dy) or 1
            z[0] += dx / d * 0.5
            z[1] += dy / d * 0.5
            if d < 4:
                hp -= 1
                z[0], z[1] = random.randint(0, SCREEN_W), 0

        if hp <= 0:
            game_over_screen(display, "GAME OVER", score)
            return score
        if not zombies:
            wave += 1
            spawn_wave(2 + wave)

        display.fill(0)
        display.fill_rect(int(px) - 2, int(py) - 2, 4, 4, 1)
        for z in zombies:
            display.fill_rect(int(z[0]) - 2, int(z[1]) - 2, 4, 4, 1)
        for b in bullets:
            display.pixel(int(b[0]), int(b[1]), 1)
        display.text("HP{} S{}".format(hp, score), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# ============================================================= RPGBATTLE --
def play_rpgbattle(display):
    player_hp, player_mp = 30, 10
    enemy_list = [{"name": "SLIME", "hp": 15}, {"name": "GOBLIN", "hp": 20}, {"name": "ORC", "hp": 28}]
    idx = 0
    enemy = dict(enemy_list[idx])
    sel = 0
    options = ["ATTACK", "HEAL"]
    msg = ""

    while True:
        d = read_dir()
        if d == 'U': sel = (sel - 1) % 2
        elif d == 'D': sel = (sel + 1) % 2

        display.fill(0)
        display.text(enemy["name"], 0, 0, 1)
        display.text("E:{}".format(enemy["hp"]), 0, 10, 1)
        display.text("Y:{} MP{}".format(player_hp, player_mp), 0, 20, 1)
        for i, o in enumerate(options):
            prefix = "> " if i == sel else "  "
            display.text(prefix + o, 0, 34 + i * 10, 1)
        display.text(msg[:16], 0, 56, 1)
        display.show()

        if button():
            wait_release()
            if sel == 0:
                dmg = random.randint(4, 8)
                enemy["hp"] -= dmg
                msg = "Hit {}!".format(dmg)
            else:
                if player_mp >= 3:
                    player_mp -= 3
                    heal = random.randint(5, 10)
                    player_hp = min(30, player_hp + heal)
                    msg = "Heal {}".format(heal)
                else:
                    msg = "No MP!"
            time.sleep_ms(400)
            if enemy["hp"] <= 0:
                idx += 1
                if idx >= len(enemy_list):
                    game_over_screen(display, "VICTORY!")
                    return idx
                enemy = dict(enemy_list[idx])
                msg = "Next foe!"
            else:
                edmg = random.randint(3, 7)
                player_hp -= edmg
                msg = "Hit for {}".format(edmg)
                if player_hp <= 0:
                    game_over_screen(display, "DEFEATED")
                    return idx
            time.sleep_ms(500)
        time.sleep_ms(16)


# ================================================================ BOXING --
def play_boxing(display):
    player_hp, cpu_hp = 100, 100
    state, timer = "READY", 0

    while player_hp > 0 and cpu_hp > 0:
        display.fill(0)
        display.text("YOU:{}".format(player_hp), 0, 0, 1)
        display.text("CPU:{}".format(cpu_hp), 0, 10, 1)
        if state == "READY":
            centered_text(display, "get ready", 28)
            display.show()
            time.sleep_ms(random.randint(800, 1800))
            state, timer = "PUNCH", time.ticks_ms()
        elif state == "PUNCH":
            centered_text(display, "PUNCH!", 28)
            display.show()
            if button():
                rt = time.ticks_diff(time.ticks_ms(), timer)
                dmg = max(5, 20 - rt // 50)
                cpu_hp -= dmg
                display.fill(0)
                centered_text(display, "-{} cpu".format(dmg), 28)
                display.show()
                time.sleep_ms(400)
                wait_release()
                state = "READY"
            elif time.ticks_diff(time.ticks_ms(), timer) > 1000:
                player_hp -= random.randint(5, 15)
                state = "READY"
        time.sleep_ms(10)

    game_over_screen(display, "YOU WIN" if cpu_hp <= 0 else "KO'd")
    return 0


# ============================================================ BATTLESHIP --
def play_battleship(display):
    GRID = 6
    ships = set()
    while len(ships) < 4:
        ships.add((random.randrange(GRID), random.randrange(GRID)))
    hits, misses = set(), set()
    cur = [0, 0]
    CELL, oy = 9, 8
    ox = (SCREEN_W - GRID * CELL) // 2

    while True:
        d = read_dir()
        if d == 'L': cur[0] = (cur[0] - 1) % GRID
        elif d == 'R': cur[0] = (cur[0] + 1) % GRID
        elif d == 'U': cur[1] = (cur[1] - 1) % GRID
        elif d == 'D': cur[1] = (cur[1] + 1) % GRID
        if button():
            wait_release()
            t = tuple(cur)
            if t in ships:
                hits.add(t)
            elif t not in misses:
                misses.add(t)

        display.fill(0)
        for x in range(GRID):
            for y in range(GRID):
                cx, cy = ox + x * CELL, oy + y * CELL
                display.rect(cx, cy, CELL - 1, CELL - 1, 1)
                if (x, y) in hits:
                    display.fill_rect(cx + 2, cy + 2, CELL - 5, CELL - 5, 1)
                elif (x, y) in misses:
                    display.pixel(cx + CELL // 2, cy + CELL // 2, 1)
        cx, cy = ox + cur[0] * CELL, oy + cur[1] * CELL
        display.rect(cx + 1, cy + 1, CELL - 3, CELL - 3, 1)
        display.text("H:{}/4".format(len(hits)), 0, 0, 1)
        display.show()
        if len(hits) >= 4:
            game_over_screen(display, "ALL SUNK!", len(misses))
            return len(misses)
        time.sleep_ms(16)


# ================================================================ HELI --
def play_heli(display):
    y, vy = float(SCREEN_H // 2), 0.0
    GRAVITY, THRUST = 0.06, -0.12
    score = 0.0
    scroll = 0.0
    ceiling, floor = [], []
    for _ in range(0, SCREEN_W + 40, 20):
        ceiling.append(random.randint(5, 20))
        floor.append(random.randint(5, 20))

    def ensure(lst):
        while len(lst) * 20 - scroll < SCREEN_W + 20:
            lst.append(random.randint(5, 20))

    while True:
        if button():
            vy += THRUST
        vy += GRAVITY
        y += vy
        scroll += 2
        ensure(ceiling); ensure(floor)
        idx = int(scroll // 20)
        top = ceiling[idx] if idx < len(ceiling) else 10
        bot = SCREEN_H - (floor[idx] if idx < len(floor) else 10)
        if y < top or y > bot:
            game_over_screen(display, "CRASHED", int(score))
            return int(score)
        score += 1

        display.fill(0)
        for i in range(len(ceiling)):
            x = int(i * 20 - scroll)
            if -20 < x < SCREEN_W:
                display.vline(x, 0, ceiling[i], 1)
                fb = SCREEN_H - (floor[i] if i < len(floor) else 10)
                display.vline(x, fb, SCREEN_H - fb, 1)
        display.fill_rect(20, int(y) - 2, 6, 4, 1)
        display.text("S:{}".format(int(score)), 0, 0, 1)
        display.show()
        time.sleep_ms(20)


# ============================================================ AIRHOCKEY --
def play_airhockey(display):
    pw, ph = 12, 3
    player = [SCREEN_W // 2, SCREEN_H - 8]
    cpu = [SCREEN_W // 2, 8]
    puck = [SCREEN_W // 2, SCREEN_H // 2]
    pv = [2, 2]
    player_score, cpu_score = 0, 0

    while True:
        x, y = read_axes()
        player[0] = max(pw // 2, min(SCREEN_W - pw // 2, player[0] + int(x * 3)))
        player[1] = max(SCREEN_H // 2 + 4, min(SCREEN_H - 4, player[1] + int(y * 3)))

        if cpu[0] < puck[0]: cpu[0] += 1
        elif cpu[0] > puck[0]: cpu[0] -= 1
        cpu[0] = max(pw // 2, min(SCREEN_W - pw // 2, cpu[0]))

        puck[0] += pv[0]; puck[1] += pv[1]
        if puck[0] <= 1 or puck[0] >= SCREEN_W - 1: pv[0] = -pv[0]
        if abs(puck[1] - player[1]) < 3 and abs(puck[0] - player[0]) < pw // 2 + 2:
            pv[1] = -abs(pv[1])
        if abs(puck[1] - cpu[1]) < 3 and abs(puck[0] - cpu[0]) < pw // 2 + 2:
            pv[1] = abs(pv[1])

        if puck[1] < 0:
            player_score += 1
            puck, pv = [SCREEN_W // 2, SCREEN_H // 2], [2, -2]
        elif puck[1] > SCREEN_H:
            cpu_score += 1
            puck, pv = [SCREEN_W // 2, SCREEN_H // 2], [2, 2]

        display.fill(0)
        display.hline(0, SCREEN_H // 2, SCREEN_W, 1)
        display.fill_rect(player[0] - pw // 2, player[1] - ph // 2, pw, ph, 1)
        display.fill_rect(cpu[0] - pw // 2, cpu[1] - ph // 2, pw, ph, 1)
        display.fill_rect(puck[0] - 1, puck[1] - 1, 2, 2, 1)
        display.text("{}-{}".format(cpu_score, player_score), SCREEN_W // 2 - 10, 0, 1)
        display.show()

        if player_score >= 5:
            game_over_screen(display, "YOU WIN")
            return player_score
        if cpu_score >= 5:
            game_over_screen(display, "CPU WINS")
            return player_score
        time.sleep_ms(20)


# ========================================================== LANE RUNNER --
def play_lanerunner(display):
    LANES = [24, 64, 104]
    lane = 1
    obstacles = []
    score = 0
    speed = 2.0
    last_move = time.ticks_ms()
    next_spawn = 0

    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d in ('L', 'R') and time.ticks_diff(now, last_move) > 180:
            last_move = now
            if d == 'L': lane = max(0, lane - 1)
            elif d == 'R': lane = min(2, lane + 1)

        for ob in obstacles:
            ob[1] += speed
        obstacles[:] = [ob for ob in obstacles if ob[1] < SCREEN_H + 10]
        next_spawn -= 1
        if next_spawn <= 0:
            obstacles.append([random.randint(0, 2), -10])
            next_spawn = random.randint(20, 40)

        for ob in obstacles:
            if SCREEN_H - 14 < ob[1] < SCREEN_H - 2 and ob[0] == lane:
                game_over_screen(display, "GAME OVER", score // 10)
                return score // 10

        score += 1
        speed = min(6, 2.0 + score * 0.002)

        display.fill(0)
        display.vline(44, 0, SCREEN_H, 1)
        display.vline(84, 0, SCREEN_H, 1)
        for ob in obstacles:
            display.fill_rect(LANES[ob[0]] - 6, int(ob[1]), 12, 8, 1)
        display.fill_rect(LANES[lane] - 6, SCREEN_H - 12, 12, 8, 1)
        display.text("S:{}".format(score // 10), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# ============================================================== SNIPER --
def play_sniper(display):
    cursor_x = SCREEN_W // 2
    targets = [[random.randint(10, SCREEN_W - 10), random.randint(10, SCREEN_H - 10), random.choice([-1, 1])]]
    ammo, score = 10, 0

    while ammo > 0:
        x, _ = read_axes()
        cursor_x = max(2, min(SCREEN_W - 2, cursor_x + int(x * 3)))

        for t in targets:
            t[0] += t[2]
            if t[0] < 5 or t[0] > SCREEN_W - 5: t[2] = -t[2]

        if button():
            ammo -= 1
            for t in targets[:]:
                if abs(t[0] - cursor_x) < 5:
                    targets.remove(t)
                    score += 1
                    targets.append([random.randint(10, SCREEN_W - 10),
                                     random.randint(10, SCREEN_H - 10), random.choice([-1, 1])])
            wait_release()

        display.fill(0)
        display.vline(cursor_x, 0, SCREEN_H, 1)
        for t in targets:
            display.fill_rect(t[0] - 4, t[1] - 4, 8, 8, 1)
        display.text("Ammo:{} S:{}".format(ammo, score), 0, 0, 1)
        display.show()
        time.sleep_ms(30)

    game_over_screen(display, "OUT OF AMMO", score)
    return score


# ================================================================= MENU --
GAMES = [
    ("Mini-DOOM", play_minidoom),
    ("Snake", play_snake),
    ("Pong", play_pong),
    ("Breakout", play_breakout),
    ("Tetris", play_tetris),
    ("Flappy", play_flappy),
    ("Invaders", play_invaders),
    ("Pac-Maze", play_maze),
    ("Reaction", play_reaction),
    ("Simon", play_simon),
    ("Asteroids", play_asteroids),
    ("Frogger", play_frogger),
    ("TicTacToe", play_tictactoe),
    ("Connect4", play_connect4),
    ("2048", play_2048),
    ("Memory", play_memory),
    ("Whack-Mole", play_whack),
    ("Lander", play_lander),
    ("RPS", play_rps),
    ("DinoRun", play_dinorun),
    ("Doom Maze", play_doommaze),
    ("Racer", play_racer),
    ("Platformer", play_platformer),
    ("Zombies", play_zombies),
    ("RPG Battle", play_rpgbattle),
    ("Boxing", play_boxing),
    ("Battleship", play_battleship),
    ("Heli", play_heli),
    ("AirHockey", play_airhockey),
    ("LaneRunner", play_lanerunner),
    ("Sniper", play_sniper),
]

# Pull in the second batch of games (games2.py) - it has no hardware setup
# of its own, so we hand it the shared helpers right after importing it.
import games2
games2.SCREEN_W = SCREEN_W
games2.SCREEN_H = SCREEN_H
games2.read_axes = read_axes
games2.read_dir = read_dir
games2.button = button
games2.wait_release = wait_release
games2.wait_for_press = wait_for_press
games2.centered_text = centered_text
games2.game_over_screen = game_over_screen
GAMES += games2.GAMES2



def menu(display):
    selected = 0
    last_move = time.ticks_ms()
    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 200:
            last_move = now
            if d == 'U': selected = (selected - 1) % len(GAMES)
            elif d == 'D': selected = (selected + 1) % len(GAMES)

        display.fill(0)
        display.text("THE PI DECK", 20, 0, 1)
        display.hline(0, 10, SCREEN_W, 1)
        start = max(0, min(selected - 1, len(GAMES) - 4))
        for i, (name, _) in enumerate(GAMES[start:start + 4]):
            idx = start + i
            y = 14 + i * 12
            if idx == selected:
                display.fill_rect(0, y - 1, SCREEN_W, 10, 1)
                display.text(name, 2, y, 0)
            else:
                display.text("  " + name, 0, y, 1)
        display.show()

        if button():
            wait_release()
            return GAMES[selected][1]
        time.sleep_ms(16)


def main():
    global _btn_was_pressed, _tap_count, _last_tap_time
    display = make_display()
    calibrate_joystick(display)
    init_audio()
    play_boot_animation(display)
    while True:
        game_fn = menu(display)
        try:
            game_fn(display)
        except GoHome:
            # reset double-tap tracking so it starts clean in the menu/next game
            _btn_was_pressed, _tap_count, _last_tap_time = False, 0, 0
            continue
        except Exception as e:
            display.fill(0)
            display.text("ERROR", 0, 0, 1)
            display.text(str(e)[:16], 0, 12, 1)
            display.show()
            time.sleep(2)


if __name__ == "__main__":
    main()