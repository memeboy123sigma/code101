"""
THE PI DECK - games pack 2 (14 additional games, 45 total).

This file does NOT initialise any hardware. main.py imports it and injects
the shared helpers (SCREEN_W, read_axes, button, etc.) right after import so
the joystick and display are initialised only once.

Flash this file alongside main.py and sh1106.py.
"""
import math, time, random

# ---- injected by main.py after import - placeholders so this file can be
# read/linted on its own, but these are overwritten before any game runs ----
SCREEN_W, SCREEN_H = 128, 64
read_axes = None
read_dir = None
button = None
wait_release = None
wait_for_press = None
centered_text = None
game_over_screen = None


# ============================================================= CENTIPEDE --
def play_centipede(display):
    mushrooms = set()
    for _ in range(14):
        mushrooms.add((random.randint(0, SCREEN_W // 4 - 1) * 4, random.randint(2, 10) * 4))
    segs = [SCREEN_W - 4 - i * 5 for i in range(6)]
    segs_y = 4
    direction = -1
    player_x = SCREEN_W // 2
    bullet = None
    score = 0
    last_shot = 0

    while True:
        x, _ = read_axes()
        player_x = max(2, min(SCREEN_W - 2, player_x + int(x * 3)))
        now = time.ticks_ms()
        if button() and bullet is None and time.ticks_diff(now, last_shot) > 200:
            bullet = [player_x, SCREEN_H - 6]
            last_shot = now
        if bullet:
            bullet[1] -= 4
            if bullet[1] < 0: bullet = None

        segs = [sx + direction for sx in segs]
        if segs and (segs[0] <= 2 or segs[0] >= SCREEN_W - 2):
            direction = -direction
            segs_y = min(SCREEN_H - 6, segs_y + 4)

        if bullet:
            key = (bullet[0] // 4 * 4, bullet[1] // 4 * 4)
            if key in mushrooms:
                mushrooms.discard(key)
                bullet = None
        if bullet:
            for i, sx in enumerate(segs):
                if abs(sx - bullet[0]) < 3 and abs(segs_y - bullet[1]) < 3:
                    segs.pop(i)
                    score += 1
                    bullet = None
                    break

        if segs_y >= SCREEN_H - 10:
            for sx in segs:
                if abs(sx - player_x) < 4:
                    game_over_screen(display, "GAME OVER", score)
                    return score

        display.fill(0)
        for mx, my in mushrooms:
            display.fill_rect(mx, my, 3, 3, 1)
        for sx in segs:
            display.fill_rect(int(sx) - 2, segs_y - 2, 4, 4, 1)
        display.fill_rect(player_x - 3, SCREEN_H - 3, 6, 2, 1)
        if bullet:
            display.pixel(bullet[0], bullet[1], 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        if not segs:
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(30)


# ================================================================ SHMUP --
def play_shmup(display):
    player_x = SCREEN_W // 2
    bullets = []
    enemies = [[20 + c * 14, 10 + r * 10, 0.0, 0.0, False] for r in range(2) for c in range(6)]
    score, last_shot, t = 0, 0, 0

    while True:
        x, _ = read_axes()
        player_x = max(2, min(SCREEN_W - 2, player_x + int(x * 3)))
        now = time.ticks_ms()
        if button() and time.ticks_diff(now, last_shot) > 250:
            last_shot = now
            bullets.append([player_x, SCREEN_H - 6])
        for b in bullets: b[1] -= 4
        bullets[:] = [b for b in bullets if b[1] > 0]

        t += 1
        for e in enemies:
            if not e[4] and random.random() < 0.001:
                e[4] = True
                e[2] = (player_x - e[0]) / 60.0
                e[3] = 1.0
            if e[4]:
                e[0] += e[2]; e[1] += e[3]
                if e[1] > SCREEN_H:
                    e[1], e[4], e[0] = 5, False, random.randint(10, SCREEN_W - 10)
            else:
                e[0] += math.sin(t * 0.05) * 0.5

        for b in bullets[:]:
            for e in enemies[:]:
                if abs(e[0] - b[0]) < 5 and abs(e[1] - b[1]) < 4:
                    enemies.remove(e)
                    if b in bullets: bullets.remove(b)
                    score += 1
                    break

        for e in enemies:
            if abs(e[0] - player_x) < 4 and e[1] > SCREEN_H - 6:
                game_over_screen(display, "GAME OVER", score)
                return score

        display.fill(0)
        display.fill_rect(player_x - 3, SCREEN_H - 3, 6, 2, 1)
        for e in enemies:
            display.fill_rect(int(e[0]) - 3, int(e[1]) - 2, 6, 4, 1)
        for b in bullets:
            display.pixel(b[0], b[1], 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        if not enemies:
            game_over_screen(display, "YOU WIN", score)
            return score
        time.sleep_ms(25)


# ========================================================= MISSILE CMD --
def play_missilecmd(display):
    alive_cities = {20, 50, 80, 110}
    cursor_x = SCREEN_W // 2
    missiles, interceptors = [], []
    score, spawn_timer, last_shot = 0, 0, 0

    while alive_cities:
        x, _ = read_axes()
        cursor_x = max(0, min(SCREEN_W, cursor_x + int(x * 3)))
        spawn_timer -= 1
        if spawn_timer <= 0:
            tx = random.choice(list(alive_cities))
            missiles.append([random.randint(0, SCREEN_W), 0, tx])
            spawn_timer = random.randint(40, 80)

        now = time.ticks_ms()
        if button() and time.ticks_diff(now, last_shot) > 200:
            last_shot = now
            interceptors.append([SCREEN_W // 2, SCREEN_H - 2, cursor_x, 15])

        for m in missiles:
            dx = m[2] - m[0]
            m[0] += dx * 0.02
            m[1] += 1

        for ic in interceptors[:]:
            dx, dy = ic[2] - ic[0], ic[3] - ic[1]
            d = math.sqrt(dx * dx + dy * dy) or 1
            ic[0] += dx / d * 3; ic[1] += dy / d * 3
            if d < 3:
                interceptors.remove(ic)
                for m in missiles[:]:
                    if abs(m[0] - ic[0]) < 8 and abs(m[1] - ic[1]) < 8:
                        missiles.remove(m); score += 1

        for m in missiles[:]:
            if m[1] >= SCREEN_H - 4:
                missiles.remove(m)
                if alive_cities:
                    hit_city = min(alive_cities, key=lambda c: abs(c - m[0]))
                    if abs(hit_city - m[0]) < 8:
                        alive_cities.discard(hit_city)

        display.fill(0)
        for c in alive_cities:
            display.fill_rect(c - 4, SCREEN_H - 4, 8, 4, 1)
        for m in missiles:
            display.pixel(int(m[0]), int(m[1]), 1)
        for ic in interceptors:
            display.pixel(int(ic[0]), int(ic[1]), 1)
        display.vline(cursor_x, 0, 6, 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(25)

    game_over_screen(display, "CITIES LOST", score)
    return score


# ================================================================ PINBALL --
def play_pinball(display):
    ball = [SCREEN_W - 10, 10]
    vel = [-1.0, 0.0]
    GRAVITY = 0.15
    score, lives = 0, 3
    bumpers = [(30, 20), (60, 30), (90, 20)]
    FLIPPER_Y = SCREEN_H - 6
    flipper_x = SCREEN_W // 2

    while True:
        vel[1] += GRAVITY
        ball[0] += vel[0]; ball[1] += vel[1]
        if ball[0] <= 2 or ball[0] >= SCREEN_W - 2: vel[0] = -vel[0]
        if ball[1] <= 2: vel[1] = abs(vel[1])

        for bx, by in bumpers:
            if abs(ball[0] - bx) < 4 and abs(ball[1] - by) < 4:
                vel[1] = -abs(vel[1]) - 1
                vel[0] += (ball[0] - bx) * 0.3
                score += 10

        flipper_up = button()
        if abs(ball[1] - FLIPPER_Y) < 4 and abs(ball[0] - flipper_x) < 16:
            if flipper_up:
                vel[1] = -4
                vel[0] += random.uniform(-0.5, 0.5)
            else:
                vel[1] = abs(vel[1]) * 0.3

        if ball[1] > SCREEN_H:
            lives -= 1
            if lives <= 0:
                game_over_screen(display, "GAME OVER", score)
                return score
            ball, vel = [SCREEN_W - 10, 10], [-1.0, 0.0]

        display.fill(0)
        for bx, by in bumpers:
            display.rect(bx - 3, by - 3, 6, 6, 1)
        fw = 32 if flipper_up else 28
        display.fill_rect(flipper_x - fw // 2, FLIPPER_Y, fw, 2, 1)
        display.fill_rect(int(ball[0]) - 1, int(ball[1]) - 1, 2, 2, 1)
        display.text("S:{} L:{}".format(score, lives), 0, 0, 1)
        display.show()
        time.sleep_ms(20)


# ============================================================= BOMBERMAN --
def play_bomberman(display):
    COLS, ROWS, CELL = 12, 7, 9
    ox = (SCREEN_W - COLS * CELL) // 2
    grid = [[1 if (x % 2 == 0 and y % 2 == 0) else (2 if random.random() < 0.4 else 0)
             for x in range(COLS)] for y in range(ROWS)]
    px, py = 1, 1
    grid[py][px] = 0
    bombs = []
    enemy = [COLS - 2, ROWS - 2]
    grid[enemy[1]][enemy[0]] = 0
    score = 0
    last_move = time.ticks_ms()

    def explode(bx, by):
        nonlocal score
        cells = [(bx, by)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = bx + dx, by + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS:
                if grid[ny][nx] == 2:
                    grid[ny][nx] = 0
                    score += 1
                if grid[ny][nx] == 0:
                    cells.append((nx, ny))
        return cells

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
            if 0 <= nx < COLS and 0 <= ny < ROWS and grid[ny][nx] == 0:
                px, py = nx, ny
        if button() and not any(b[0] == px and b[1] == py for b in bombs):
            bombs.append([px, py, 30])

        blast_cells = []
        for b in bombs[:]:
            b[2] -= 1
            if b[2] <= 0:
                blast_cells += explode(b[0], b[1])
                bombs.remove(b)

        for cx, cy in blast_cells:
            if cx == enemy[0] and cy == enemy[1]:
                game_over_screen(display, "YOU WIN", score)
                return score
            if cx == px and cy == py:
                game_over_screen(display, "GAME OVER", score)
                return score

        if random.random() < 0.1:
            edx, edy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            nx, ny = enemy[0] + edx, enemy[1] + edy
            if 0 <= nx < COLS and 0 <= ny < ROWS and grid[ny][nx] == 0:
                enemy[0], enemy[1] = nx, ny
        if enemy[0] == px and enemy[1] == py:
            game_over_screen(display, "GAME OVER", score)
            return score

        display.fill(0)
        for y in range(ROWS):
            for x in range(COLS):
                if grid[y][x] == 1:
                    display.fill_rect(ox + x * CELL, y * CELL, CELL - 1, CELL - 1, 1)
                elif grid[y][x] == 2:
                    display.rect(ox + x * CELL, y * CELL, CELL - 1, CELL - 1, 1)
        for b in bombs:
            display.fill_rect(ox + b[0] * CELL + 2, b[1] * CELL + 2, CELL - 5, CELL - 5, 1)
        display.fill_rect(ox + enemy[0] * CELL + 1, enemy[1] * CELL + 1, CELL - 3, CELL - 3, 1)
        display.rect(ox + px * CELL, py * CELL, CELL - 1, CELL - 1, 1)
        display.text("S:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# =============================================================== SOKOBAN --
def play_sokoban(display):
    level = [
        "########",
        "#......#",
        "#.$..X.#",
        "#..@...#",
        "#...$.X#",
        "#......#",
        "########",
    ]
    grid = [list(row) for row in level]
    ROWS, COLS, CELL = len(grid), len(grid[0]), 9
    ox = (SCREEN_W - COLS * CELL) // 2
    px = py = 0
    targets = set()
    for y in range(ROWS):
        for x in range(COLS):
            if grid[y][x] == '@':
                px, py = x, y
                grid[y][x] = '.'
            elif grid[y][x] == 'X':
                targets.add((x, y))
    boxes = set()
    for y in range(ROWS):
        for x in range(COLS):
            if grid[y][x] == '$':
                boxes.add((x, y))
                grid[y][x] = '.'

    last_move = time.ticks_ms()
    while True:
        d = read_dir()
        now = time.ticks_ms()
        if d and time.ticks_diff(now, last_move) > 180:
            last_move = now
            dx, dy = 0, 0
            if d == 'U': dy = -1
            elif d == 'D': dy = 1
            elif d == 'L': dx = -1
            elif d == 'R': dx = 1
            nx, ny = px + dx, py + dy
            if grid[ny][nx] != '#':
                if (nx, ny) in boxes:
                    bx, by = nx + dx, ny + dy
                    if grid[by][bx] != '#' and (bx, by) not in boxes:
                        boxes.discard((nx, ny))
                        boxes.add((bx, by))
                        px, py = nx, ny
                else:
                    px, py = nx, ny

        display.fill(0)
        for y in range(ROWS):
            for x in range(COLS):
                if grid[y][x] == '#':
                    display.fill_rect(ox + x * CELL, y * CELL, CELL - 1, CELL - 1, 1)
        for tx, ty in targets:
            display.rect(ox + tx * CELL + 2, ty * CELL + 2, CELL - 5, CELL - 5, 1)
        for bx, by in boxes:
            display.rect(ox + bx * CELL + 1, by * CELL + 1, CELL - 3, CELL - 3, 1)
        display.fill_rect(ox + px * CELL + 3, py * CELL + 3, CELL - 7, CELL - 7, 1)
        display.show()
        if boxes == targets:
            game_over_screen(display, "SOLVED!")
            return 1
        time.sleep_ms(16)


# ============================================================= LIGHTSOUT --
def play_lightsout(display):
    SIZE, CELL = 5, 10
    ox, oy = (SCREEN_W - SIZE * CELL) // 2, 4
    grid = [[0] * SIZE for _ in range(SIZE)]

    def toggle(x, y):
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < SIZE and 0 <= ny < SIZE:
                grid[ny][nx] ^= 1

    for _ in range(15):
        toggle(random.randrange(SIZE), random.randrange(SIZE))

    cursor = [0, 0]
    while True:
        d = read_dir()
        if d == 'L': cursor[0] = (cursor[0] - 1) % SIZE
        elif d == 'R': cursor[0] = (cursor[0] + 1) % SIZE
        elif d == 'U': cursor[1] = (cursor[1] - 1) % SIZE
        elif d == 'D': cursor[1] = (cursor[1] + 1) % SIZE
        if button():
            toggle(cursor[0], cursor[1])
            wait_release()

        display.fill(0)
        for y in range(SIZE):
            for x in range(SIZE):
                cx, cy = ox + x * CELL, oy + y * CELL
                display.rect(cx, cy, CELL - 1, CELL - 1, 1)
                if grid[y][x]:
                    display.fill_rect(cx + 2, cy + 2, CELL - 5, CELL - 5, 1)
        ccx, ccy = ox + cursor[0] * CELL, oy + cursor[1] * CELL
        display.rect(ccx + 1, ccy + 1, CELL - 3, CELL - 3, 1)
        display.show()
        if all(not c for row in grid for c in row):
            game_over_screen(display, "SOLVED!")
            return 1
        time.sleep_ms(16)


# ================================================================ SUDOKU --
def play_sudoku(display):
    solution = [[1, 2, 3, 4], [3, 4, 1, 2], [2, 1, 4, 3], [4, 3, 2, 1]]
    puzzle = [row[:] for row in solution]
    fixed = [[True] * 4 for _ in range(4)]
    cells = [(r, c) for r in range(4) for c in range(4)]
    random.shuffle(cells)
    for r, c in cells[:8]:
        puzzle[r][c] = 0
        fixed[r][c] = False

    cur = [0, 0]
    CELL = 14
    ox, oy = (SCREEN_W - 4 * CELL) // 2, (SCREEN_H - 4 * CELL) // 2
    while True:
        d = read_dir()
        if d == 'L': cur[0] = (cur[0] - 1) % 4
        elif d == 'R': cur[0] = (cur[0] + 1) % 4
        elif d == 'U': cur[1] = (cur[1] - 1) % 4
        elif d == 'D': cur[1] = (cur[1] + 1) % 4
        if button() and not fixed[cur[1]][cur[0]]:
            puzzle[cur[1]][cur[0]] = (puzzle[cur[1]][cur[0]] % 4) + 1
            wait_release()

        display.fill(0)
        for r in range(4):
            for c in range(4):
                cx, cy = ox + c * CELL, oy + r * CELL
                display.rect(cx, cy, CELL - 1, CELL - 1, 1)
                v = puzzle[r][c]
                if v: display.text(str(v), cx + 4, cy + 3, 1)
        ccx, ccy = ox + cur[0] * CELL, oy + cur[1] * CELL
        display.rect(ccx + 1, ccy + 1, CELL - 3, CELL - 3, 1)
        display.show()
        if puzzle == solution:
            game_over_screen(display, "SOLVED!")
            return 1
        time.sleep_ms(16)


# ============================================================= ICECLIMB --
def play_iceclimb(display):
    platforms = []
    y = 0
    for _ in range(20):
        platforms.append([random.randint(10, SCREEN_W - 10), y])
        y += 14
    player_x = float(SCREEN_W // 2)
    player_y = float(SCREEN_H - 10)
    vy = 0.0
    GRAVITY = 0.3
    camera_y = 0.0
    score = 0

    while True:
        tx, _ = read_axes()
        player_x = max(2, min(SCREEN_W - 2, player_x + tx * 2))
        vy += GRAVITY
        player_y += vy
        for plat in platforms:
            if abs(player_y - plat[1]) < 4 and abs(player_x - plat[0]) < 12 and vy > 0:
                player_y = plat[1]
                vy = -5

        if player_y < camera_y + 20:
            camera_y = player_y - 20
            score = max(score, int(-camera_y))
            while platforms[-1][1] > camera_y - 20:
                platforms.append([random.randint(10, SCREEN_W - 10), platforms[-1][1] - 14])

        if player_y - camera_y > SCREEN_H + 10:
            game_over_screen(display, "FELL!", score)
            return score

        display.fill(0)
        for plat in platforms:
            sy = int(plat[1] - camera_y)
            if 0 <= sy < SCREEN_H:
                display.hline(max(0, plat[0] - 10), sy, 20, 1)
        display.fill_rect(int(player_x) - 2, int(player_y - camera_y) - 4, 4, 4, 1)
        display.text("H:{}".format(score), 0, 0, 1)
        display.show()
        time.sleep_ms(16)


# =============================================================== CHECKERS --
def play_checkers(display):
    SIZE, CELL = 6, 10
    ox, oy = (SCREEN_W - SIZE * CELL) // 2, (SCREEN_H - SIZE * CELL) // 2
    board = [[0] * SIZE for _ in range(SIZE)]
    for r in range(2):
        for c in range(SIZE):
            if (r + c) % 2 == 1: board[r][c] = 2
    for r in range(SIZE - 2, SIZE):
        for c in range(SIZE):
            if (r + c) % 2 == 1: board[r][c] = 1
    cur = [0, SIZE - 1]
    selected = None

    def is_player(v): return v in (1, 3)
    def is_cpu(v): return v in (2, 4)

    def moves_for(r, c, v):
        dirs = [(-1, -1), (-1, 1)] if v == 1 else [(1, -1), (1, 1)] if v == 2 else \
               [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        result = []
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < SIZE and 0 <= nc < SIZE and board[nr][nc] == 0:
                result.append((nr, nc, None))
            jr, jc = r + 2 * dr, c + 2 * dc
            if 0 <= jr < SIZE and 0 <= jc < SIZE and 0 <= nr < SIZE and 0 <= nc < SIZE \
                    and board[nr][nc] != 0 and board[jr][jc] == 0:
                if (v in (1, 3) and is_cpu(board[nr][nc])) or (v in (2, 4) and is_player(board[nr][nc])):
                    result.append((jr, jc, (nr, nc)))
        return result

    def cpu_turn():
        all_moves = []
        for r in range(SIZE):
            for c in range(SIZE):
                if is_cpu(board[r][c]):
                    for mv in moves_for(r, c, board[r][c]):
                        all_moves.append((r, c, mv))
        if not all_moves: return
        captures = [m for m in all_moves if m[2][2]]
        r, c, (nr, nc, cap) = random.choice(captures or all_moves)
        board[nr][nc] = board[r][c]
        board[r][c] = 0
        if cap: board[cap[0]][cap[1]] = 0
        if nr == SIZE - 1: board[nr][nc] = 4

    while True:
        d = read_dir()
        if d == 'L': cur[0] = max(0, cur[0] - 1)
        elif d == 'R': cur[0] = min(SIZE - 1, cur[0] + 1)
        elif d == 'U': cur[1] = max(0, cur[1] - 1)
        elif d == 'D': cur[1] = min(SIZE - 1, cur[1] + 1)
        if button():
            wait_release()
            r, c = cur[1], cur[0]
            if selected is None:
                if is_player(board[r][c]):
                    selected = (r, c)
            else:
                sr, sc = selected
                valid = moves_for(sr, sc, board[sr][sc])
                match = [mv for mv in valid if mv[0] == r and mv[1] == c]
                if match:
                    nr, nc, cap = match[0]
                    board[nr][nc] = board[sr][sc]
                    board[sr][sc] = 0
                    if cap: board[cap[0]][cap[1]] = 0
                    if nr == 0: board[nr][nc] = 3
                    selected = None
                    cpu_turn()
                else:
                    selected = None

        display.fill(0)
        for r in range(SIZE):
            for c in range(SIZE):
                cx, cy = ox + c * CELL, oy + r * CELL
                if (r + c) % 2 == 1:
                    display.rect(cx, cy, CELL - 1, CELL - 1, 1)
                v = board[r][c]
                if v:
                    display.fill_rect(cx + 2, cy + 2, CELL - 5, CELL - 5, 1)
                    if v in (3, 4):
                        display.rect(cx + 3, cy + 3, CELL - 7, CELL - 7, 0)
        if selected:
            scx, scy = ox + selected[1] * CELL, oy + selected[0] * CELL
            display.rect(scx, scy, CELL - 1, CELL - 1, 1)
        ccx, ccy = ox + cur[0] * CELL, oy + cur[1] * CELL
        display.rect(ccx + 1, ccy + 1, CELL - 3, CELL - 3, 1)
        display.show()

        if not any(is_cpu(v) for row in board for v in row):
            game_over_screen(display, "YOU WIN"); return 1
        if not any(is_player(v) for row in board for v in row):
            game_over_screen(display, "CPU WINS"); return 0
        time.sleep_ms(16)


# ================================================================ OTHELLO --
def play_othello(display):
    SIZE, CELL = 6, 10
    ox, oy = (SCREEN_W - SIZE * CELL) // 2, (SCREEN_H - SIZE * CELL) // 2
    board = [[0] * SIZE for _ in range(SIZE)]
    mid = SIZE // 2
    board[mid - 1][mid - 1] = 2; board[mid][mid] = 2
    board[mid - 1][mid] = 1; board[mid][mid - 1] = 1
    cur = [mid, mid]
    DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def flips_for(r, c, player):
        if board[r][c] != 0: return []
        opp = 2 if player == 1 else 1
        all_flips = []
        for dr, dc in DIRS:
            line = []
            nr, nc = r + dr, c + dc
            while 0 <= nr < SIZE and 0 <= nc < SIZE and board[nr][nc] == opp:
                line.append((nr, nc)); nr += dr; nc += dc
            if line and 0 <= nr < SIZE and 0 <= nc < SIZE and board[nr][nc] == player:
                all_flips += line
        return all_flips

    def valid_moves(player):
        return [(r, c) for r in range(SIZE) for c in range(SIZE) if flips_for(r, c, player)]

    def cpu_turn():
        moves = valid_moves(2)
        if not moves: return
        r, c = max(moves, key=lambda m: len(flips_for(m[0], m[1], 2)))
        board[r][c] = 2
        for fr, fc in flips_for(r, c, 2): board[fr][fc] = 2

    while True:
        d = read_dir()
        if d == 'L': cur[1] = max(0, cur[1] - 1)
        elif d == 'R': cur[1] = min(SIZE - 1, cur[1] + 1)
        elif d == 'U': cur[0] = max(0, cur[0] - 1)
        elif d == 'D': cur[0] = min(SIZE - 1, cur[0] + 1)
        if button():
            wait_release()
            r, c = cur[0], cur[1]
            flips = flips_for(r, c, 1)
            if flips:
                board[r][c] = 1
                for fr, fc in flips: board[fr][fc] = 1
                if valid_moves(2):
                    cpu_turn()

        display.fill(0)
        for r in range(SIZE):
            for c in range(SIZE):
                cx, cy = ox + c * CELL, oy + r * CELL
                display.rect(cx, cy, CELL - 1, CELL - 1, 1)
                if board[r][c] == 1:
                    display.fill_rect(cx + 2, cy + 2, CELL - 5, CELL - 5, 1)
                elif board[r][c] == 2:
                    display.rect(cx + 2, cy + 2, CELL - 5, CELL - 5, 1)
        ccx, ccy = ox + cur[1] * CELL, oy + cur[0] * CELL
        display.rect(ccx + 1, ccy + 1, CELL - 3, CELL - 3, 1)
        display.show()

        if not valid_moves(1) and not valid_moves(2):
            p1 = sum(row.count(1) for row in board)
            p2 = sum(row.count(2) for row in board)
            game_over_screen(display, "YOU WIN" if p1 > p2 else "CPU WINS" if p2 > p1 else "DRAW")
            return p1
        time.sleep_ms(16)


# ================================================================ YAHTZEE --
def play_yahtzee(display):
    rounds, total = 3, 0
    for rnd in range(rounds):
        dice = [random.randint(1, 6) for _ in range(5)]
        kept = [False] * 5
        cursor = 0
        rolls_left = 2
        last_input = time.ticks_ms()
        while True:
            d = read_dir()
            now = time.ticks_ms()
            if d and time.ticks_diff(now, last_input) > 200:
                last_input = now
                if d == 'L': cursor = (cursor - 1) % 5
                elif d == 'R': cursor = (cursor + 1) % 5
                elif d == 'U' and rolls_left > 0:
                    rolls_left -= 1
                    for i in range(5):
                        if not kept[i]:
                            dice[i] = random.randint(1, 6)
            if button():
                kept[cursor] = not kept[cursor]
                wait_release()

            display.fill(0)
            display.text("Rnd{}/{} Rolls:{}".format(rnd + 1, rounds, rolls_left), 0, 0, 1)
            for i, v in enumerate(dice):
                x = 6 + i * 24
                display.rect(x, 20, 18, 18, 1)
                display.text(str(v), x + 6, 26, 1)
                if kept[i]:
                    display.text("K", x + 6, 40, 1)
                if i == cursor:
                    display.rect(x - 1, 19, 20, 20, 1)
            centered_text(display, "U:reroll BTN:keep", 56)
            display.show()
            if rolls_left == 0:
                time.sleep(1)
                break
            time.sleep_ms(16)
        total += sum(dice)
    game_over_screen(display, "Total:{}".format(total))
    return total


# ================================================================ HANGMAN --
def play_hangman(display):
    words = ["PYTHON", "PICO", "ARCADE", "JOYSTICK", "MAZE", "ROBOT", "LASER", "CIRCUIT"]
    word = random.choice(words)
    guessed = set()
    wrong, MAX_WRONG = 0, 6
    letter_idx = 0
    ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    while True:
        d = read_dir()
        if d == 'L': letter_idx = (letter_idx - 1) % 26
        elif d == 'R': letter_idx = (letter_idx + 1) % 26
        elif d == 'U': letter_idx = (letter_idx - 5) % 26
        elif d == 'D': letter_idx = (letter_idx + 5) % 26
        if button():
            wait_release()
            letter = ALPHA[letter_idx]
            if letter not in guessed:
                guessed.add(letter)
                if letter not in word:
                    wrong += 1

        display.fill(0)
        display.text("Wrong:{}/{}".format(wrong, MAX_WRONG), 0, 0, 1)
        shown = "".join(c if c in guessed else "_" for c in word)
        centered_text(display, shown, 20)
        centered_text(display, "< {} >".format(ALPHA[letter_idx]), 36)
        display.show()
        if all(c in guessed for c in word):
            game_over_screen(display, "YOU WIN")
            return 1
        if wrong >= MAX_WRONG:
            game_over_screen(display, "OUT! " + word)
            return 0
        time.sleep_ms(16)


# ================================================================= MATCH3 --
def play_match3(display):
    COLS, ROWS, CELL = 6, 6, 10
    ox, oy = (SCREEN_W - COLS * CELL) // 2, (SCREEN_H - ROWS * CELL) // 2
    grid = [[random.randint(0, 3) for _ in range(COLS)] for _ in range(ROWS)]
    cursor = [0, 0]
    selected = None
    moves_left, score = 15, 0

    def find_matches():
        matches = set()
        for r in range(ROWS):
            run = 1
            for c in range(1, COLS + 1):
                if c < COLS and grid[r][c] == grid[r][c - 1]:
                    run += 1
                else:
                    if run >= 3:
                        for k in range(c - run, c): matches.add((r, k))
                    run = 1
        for c in range(COLS):
            run = 1
            for r in range(1, ROWS + 1):
                if r < ROWS and grid[r][c] == grid[r - 1][c]:
                    run += 1
                else:
                    if run >= 3:
                        for k in range(r - run, r): matches.add((k, c))
                    run = 1
        return matches

    def resolve():
        nonlocal score
        while True:
            m = find_matches()
            if not m: break
            score += len(m)
            for r, c in m: grid[r][c] = -1
            for c in range(COLS):
                col_vals = [grid[r][c] for r in range(ROWS) if grid[r][c] != -1]
                missing = ROWS - len(col_vals)
                newcol = [random.randint(0, 3) for _ in range(missing)] + col_vals
                for r in range(ROWS): grid[r][c] = newcol[r]

    while moves_left > 0:
        d = read_dir()
        if d == 'L': cursor[1] = max(0, cursor[1] - 1)
        elif d == 'R': cursor[1] = min(COLS - 1, cursor[1] + 1)
        elif d == 'U': cursor[0] = max(0, cursor[0] - 1)
        elif d == 'D': cursor[0] = min(ROWS - 1, cursor[0] + 1)
        if button():
            wait_release()
            if selected is None:
                selected = list(cursor)
            else:
                sr, sc = selected
                cr, cc = cursor
                if abs(sr - cr) + abs(sc - cc) == 1:
                    grid[sr][sc], grid[cr][cc] = grid[cr][cc], grid[sr][sc]
                    if find_matches():
                        resolve()
                        moves_left -= 1
                    else:
                        grid[sr][sc], grid[cr][cc] = grid[cr][cc], grid[sr][sc]
                selected = None

        display.fill(0)
        for r in range(ROWS):
            for c in range(COLS):
                cx, cy = ox + c * CELL, oy + r * CELL
                display.rect(cx, cy, CELL - 1, CELL - 1, 1)
                v = grid[r][c]
                if v == 0: display.pixel(cx + 5, cy + 5, 1)
                elif v == 1: display.fill_rect(cx + 3, cy + 3, 4, 4, 1)
                elif v == 2: display.hline(cx + 2, cy + 5, 6, 1)
                elif v == 3: display.vline(cx + 5, cy + 2, 6, 1)
        ccx, ccy = ox + cursor[1] * CELL, oy + cursor[0] * CELL
        display.rect(ccx + 1, ccy + 1, CELL - 3, CELL - 3, 1)
        if selected:
            scx, scy = ox + selected[1] * CELL, oy + selected[0] * CELL
            display.rect(scx, scy, CELL - 1, CELL - 1, 1)
        display.text("S:{} M:{}".format(score, moves_left), 0, 0, 1)
        display.show()
        time.sleep_ms(16)

    game_over_screen(display, "OUT OF MOVES", score)
    return score


GAMES2 = [
    ("Centipede", play_centipede),
    ("Shmup", play_shmup),
    ("MissileCmd", play_missilecmd),
    ("Pinball", play_pinball),
    ("Bomberman", play_bomberman),
    ("Sokoban", play_sokoban),
    ("LightsOut", play_lightsout),
    ("Sudoku", play_sudoku),
    ("IceClimb", play_iceclimb),
    ("Checkers", play_checkers),
    ("Othello", play_othello),
    ("Yahtzee", play_yahtzee),
    ("Hangman", play_hangman),
    ("Match3", play_match3),
]