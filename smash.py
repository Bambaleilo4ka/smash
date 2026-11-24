#!/usr/bin/env python3
"""smash - человечек разбивает экран кувалдой, а потом протирает тряпочкой.

Использование:
    smash              просто показать анимацию
    smash ls -l        показать анимацию, потом выполнить команду
"""
import math
import os
import random
import shutil
import subprocess
import sys
import time

FRAME = 1 / 25  # 25 кадров в секунду
W, H = 22, 12   # размер спрайта

SPRITE_TEXT = r"""
@idle
   _____
  /     \
 | o   o |
 |   ^   |
  \_____/
  ___|___
 /   |   \
 |   |   |
     |
    / \
   /   \
  _|   |_
@walk_a
   _____
  /     \
 | o   o |
 |   ^   |
  \_____/
  ___|___
 /   |   \
 |   |   |
     |
    / \
   /   \
  _|   |_
@walk_b
   _____
  /     \
 | o   o |
 |   ^   |
  \_____/
  ___|___
 /   |   \
 |   |   |
     |
     |\
     | \
    _|  \_
@walk_h_a
   _____      _____
  /     \     |###|
 | o   o |    |###|
 |   ^   |    |###|
  \_____/     '-.-'
  ___|___     /
 /   |   \   /
 |   |   |__/
     |
    / \
   /   \
  _|   |_
@walk_h_b
   _____      _____
  /     \     |###|
 | o   o |    |###|
 |   ^   |    |###|
  \_____/     '-.-'
  ___|___     /
 /   |   \   /
 |   |   |__/
     |
     |\
     | \
    _|  \_
@raise
   _____      _____
  /     \     |###|
 | o   o |    |###|
 |   ^   |    |###|
  \_____/     '-.-'
  ___|___\      |
 /   |    \     |
 |   |     \____|
     |
    / \
   /   \
  _|   |_
@smash
   _____
  /     \
 | > _ < |
 |   O   |
  \_____/
  ___|___
 /   |   \_____
 |   |   |     \
     |          \
    / \        [###]
   /   \       [###]
  _|   |_      [###]
@cloth_a
   _____
  /     \
 | ^   ^ |
 |   v   |
  \_____/
  ___|___
 /   |   \_____
 |   |   |  ~~~~~~
     |      ~~~~~~~
    / \      ~~~~~
   /   \
  _|   |_
@cloth_b
   _____
  /     \
 | ^   ^ |
 |   v   |
  \_____/     ~~~~~~
  ___|___ ____~~~~~~
 /   |   \  ~~~~~~
 |   |   |
     |
    / \
   /   \
  _|   |_
"""

MIRROR_TABLE = str.maketrans("/\\()[]<>{}", "\\/)(][><}{")


def load_sprites():
    normal, mirrored = {}, {}
    name = None
    for line in SPRITE_TEXT.split("\n"):
        if line.startswith("@"):
            name = line[1:].strip()
            normal[name] = []
        elif name is not None:
            normal[name].append(line)
    for key in list(normal):
        lines = normal[key][:H]
        lines += [""] * (H - len(lines))
        lines = [l.ljust(W)[:W] for l in lines]
        normal[key] = lines
        mirrored[key] = [l[::-1].translate(MIRROR_TABLE) for l in lines]
    return normal, mirrored


SPRITES, SPRITES_M = load_sprites()

CRACK_COLORS = ["97", "37", "96"]
DEAD_COLORS = ["91", "92", "93", "94", "95", "96", "97", "1;30"]


def char_color(ch):
    if ch == "#":
        return "91"
    if ch == "~":
        return "96"
    return "97"


class Stage:
    def __init__(self):
        size = shutil.get_terminal_size()
        self.cols, self.rows = size.columns, size.lines
        self.damage = {}
        self.sparks = []
        self.sprite = None
        self.x = 0
        self.y = 0
        self.mirror = False
        self.bubble = None
        self.flash = False
        self.shake = 0
        self.t_next = time.time()

    def show(self):
        cols, rows = self.cols, self.rows
        dx = random.randint(-self.shake, self.shake) if self.shake else 0
        dy = random.randint(-1, 1) if self.shake > 1 else 0
        grid = [[(" ", "0")] * cols for _ in range(rows)]

        def put(x, y, ch, sgr):
            x += dx
            y += dy
            if 0 <= x < cols and 0 <= y < rows:
                grid[y][x] = (ch, sgr)

        for (x, y), (ch, sgr) in self.damage.items():
            put(x, y, ch, sgr)

        for sp in self.sparks:
            put(sp[0], sp[1], sp[2], "1;93")
            sp[3] -= 1
        self.sparks = [s for s in self.sparks if s[3] > 0]

        if self.sprite:
            lines = (SPRITES_M if self.mirror else SPRITES)[self.sprite]
            for r, line in enumerate(lines):
                for c, ch in enumerate(line):
                    if ch != " ":
                        put(self.x + c, self.y + r, ch, char_color(ch))
            if self.bubble:
                text = "( " + self.bubble + " )"
                for i, ch in enumerate(text):
                    put(self.x + 2 + i, self.y - 2, ch, "1;93")

        out = ["\x1b[H"]
        rows_out = []
        for row in grid:
            last = None
            parts = []
            for ch, sgr in row:
                if self.flash:
                    sgr = sgr + ";100"
                if sgr != last:
                    parts.append("\x1b[0m" if sgr == "0" else "\x1b[0;%sm" % sgr)
                    last = sgr
                parts.append(ch)
            rows_out.append("".join(parts))
        out.append("\n".join(rows_out))
        out.append("\x1b[0m")
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def tick(self, n=1):
        for _ in range(n):
            self.show()
            self.t_next += FRAME
            delay = self.t_next - time.time()
            if delay > 0:
                time.sleep(delay)
            else:
                self.t_next = time.time()


def crack_char(ang):
    vx, vy = math.cos(ang) * 2, math.sin(ang)
    if abs(vy) > 2 * abs(vx):
        return "|"
    if abs(vx) > 2 * abs(vy):
        return "-"
    return "\\" if vx * vy > 0 else "/"


def build_damage(cx, cy, power):
    """Возвращает {номер_кадра: [(x, y, символ, цвет), ...]}"""
    q = {}

    def add(f, cell):
        q.setdefault(f, []).append(cell)

    def ray(x, y, ang, length, f0, depth):
        for i in range(1, length + 1):
            ang += random.uniform(-0.4, 0.4)
            x += math.cos(ang) * 2
            y += math.sin(ang)
            add(f0 + i, (round(x), round(y), crack_char(ang), random.choice(CRACK_COLORS)))
            if depth < 2 and i > 3 and random.random() < 0.07:
                turn = random.choice((-1, 1)) * random.uniform(0.6, 1.1)
                ray(x, y, ang + turn, length // 2, f0 + i, depth + 1)

    nrays = int(7 + 5 * power)
    maxlen = int(10 + 8 * power)
    for _ in range(nrays):
        ray(cx, cy, random.uniform(0, 2 * math.pi),
            random.randint(maxlen // 2, maxlen), 0, 0)
    add(0, (cx, cy, "*", "1;91"))

    frames = max(q) + 1
    radius = 8 + 6 * power
    for _ in range(int(25 + 30 * power)):
        a = random.uniform(0, 2 * math.pi)
        d = (random.random() ** 0.7) * radius
        add(random.randint(0, frames - 1),
            (round(cx + math.cos(a) * d * 2), round(cy + math.sin(a) * d),
             random.choice("█▓▒░▀▄▌▐"), random.choice(DEAD_COLORS)))
    return q


def walk_to(st, tx, ty, poses, step=1):
    i = 0
    while st.x != tx or st.y != ty:
        if st.x != tx:
            st.x += max(-step, min(step, tx - st.x))
        if st.y != ty and i % 2 == 0:
            st.y += 1 if ty > st.y else -1
        st.sprite = poses[(i // 3) % 2]
        i += 1
        st.tick()


def hit(st, power):
    st.sprite = "raise"
    st.tick(12)
    st.sprite = "smash"
    cx, cy = st.x + 17, st.y + 11
    st.flash = True
    st.shake = 2
    st.tick()
    st.flash = False
    queue = build_damage(cx, cy, power)
    total = max(queue) + 1
    for f in range(total + 8):
        for x, y, ch, sgr in queue.get(f, []):
            st.damage[(x, y)] = (ch, sgr)
        st.shake = 2 if f < 8 else (1 if f < 14 else 0)
        st.tick()
    st.shake = 0
    st.tick(10)


def animate():
    st = Stage()
    cols, rows = st.cols, st.rows
    if cols < 50 or rows < 16:
        return
    st.x = -W
    st.y = (rows - H) // 2

    for k in range(3):
        tx = min(cols - 20, int(cols * (0.12 + 0.28 * k)))
        ty = random.randint(1, max(1, rows - H - 2))
        walk_to(st, tx, ty, ("walk_h_a", "walk_h_b"))
        hit(st, 0.8 + 0.5 * k)

    # "Упс..." и бросает кувалду
    st.sprite = "idle"
    st.bubble = "Упс..."
    st.tick(28)
    st.bubble = None

    # бежит к правому краю с тряпкой
    walk_to(st, cols - 10, (rows - H) // 2, ("walk_a", "walk_b"), step=2)

    # разворот и протирание справа налево
    st.mirror = True
    i = 0
    while st.x > -W:
        st.x -= 1
        st.sprite = "cloth_a" if (i // 2) % 2 == 0 else "cloth_b"
        lo, hi = st.x - 1, st.x + 9
        st.damage = {k: v for k, v in st.damage.items() if not (lo <= k[0] <= hi)}
        for _ in range(2):
            st.sparks.append([lo, random.randrange(rows), random.choice("*+'"), 4])
        i += 1
        st.tick()
    st.sparks = []
    st.tick(8)


def play():
    out = sys.stdout
    out.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    out.flush()
    try:
        animate()
    finally:
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()


def main():
    args = sys.argv[1:]
    if sys.stdout.isatty():
        try:
            play()
        except KeyboardInterrupt:
            pass
    if args:
        try:
            sys.exit(subprocess.call(args))
        except FileNotFoundError:
            print("smash: команда не найдена: %s" % args[0], file=sys.stderr)
            sys.exit(127)


if __name__ == "__main__":
    main()
