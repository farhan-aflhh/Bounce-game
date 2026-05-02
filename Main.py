"""
Bounce - Android-ready version using Kivy.

Run on desktop to test:
    pip install kivy
    python main.py

Build for Android (on Linux/WSL/macOS):
    pip install buildozer cython
    buildozer init        # only first time, then replace buildozer.spec with the one provided
    buildozer -v android debug

Controls:
  On-screen LEFT/RIGHT buttons : move
  On-screen JUMP button        : jump
  Tap anywhere on game area    : also jumps
  Keyboard (desktop testing)   : arrow keys + space
"""

import math
import random
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, Triangle, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget


# ------------------ Tunables ------------------
GRAVITY      = -1500.0   # px/s^2 (Kivy y is up, so gravity is negative)
MOVE_ACCEL   = 1800.0
MAX_SPEED    = 380.0
FRICTION     = 6.0       # exponential damping per second
JUMP_VEL     = 720.0
BOUNCE_DAMP  = 0.55
BALL_RADIUS  = 26
GROUND_H     = 60
HUD_H        = 70
CONTROLS_H   = 130


# ------------------ Game Objects (data only) ------------------
class Platform:
    __slots__ = ("x", "y", "w", "h")
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
    def rect(self):
        return (self.x, self.y, self.w, self.h)


class Ring:
    __slots__ = ("x", "y", "r", "collected", "t")
    def __init__(self, x, y, r=20):
        self.x, self.y, self.r = x, y, r
        self.collected = False
        self.t = random.random() * 6.28


class Spike:
    __slots__ = ("x", "y", "count", "size")
    def __init__(self, x, y, count=3, size=22):
        self.x, self.y = x, y
        self.count, self.size = count, size
    def rect(self):
        # Bounding rect of the spike row
        return (self.x, self.y, self.count * self.size, self.size)


# ------------------ Levels ------------------
def make_level(n, W, H):
    """Build a level scaled to the playfield size (W x H, with ground at bottom)."""
    plats, rings, spikes = [], [], []
    ground_top = GROUND_H

    # Layouts use relative positions so they adapt to screen size
    if n == 1:
        layout_p = [(0.18, 0.30, 0.18, 0.03),
                    (0.42, 0.45, 0.20, 0.03),
                    (0.68, 0.60, 0.20, 0.03),
                    (0.84, 0.30, 0.14, 0.03)]
        layout_r = [(0.27, 0.36), (0.52, 0.51), (0.78, 0.66), (0.91, 0.36),
                    (0.08, 0.13)]
        layout_s = [(0.50, 3)]
    elif n == 2:
        layout_p = [(0.12, 0.25, 0.14, 0.03),
                    (0.32, 0.40, 0.14, 0.03),
                    (0.52, 0.55, 0.14, 0.03),
                    (0.72, 0.70, 0.14, 0.03),
                    (0.85, 0.32, 0.13, 0.03),
                    (0.02, 0.50, 0.10, 0.03)]
        layout_r = [(0.19, 0.31), (0.39, 0.46), (0.59, 0.61), (0.79, 0.76),
                    (0.07, 0.56), (0.92, 0.38)]
        layout_s = [(0.27, 3), (0.62, 4)]
    else:
        layout_p = [(0.10, 0.22, 0.10, 0.03),
                    (0.26, 0.34, 0.10, 0.03),
                    (0.42, 0.46, 0.10, 0.03),
                    (0.58, 0.58, 0.10, 0.03),
                    (0.74, 0.70, 0.10, 0.03),
                    (0.86, 0.40, 0.12, 0.03),
                    (0.02, 0.78, 0.09, 0.03)]
        layout_r = [(0.15, 0.28), (0.31, 0.40), (0.47, 0.52),
                    (0.63, 0.64), (0.79, 0.76), (0.92, 0.46),
                    (0.06, 0.84)]
        layout_s = [(0.21, 3), (0.38, 3), (0.55, 3), (0.72, 3)]

    for fx, fy, fw, fh in layout_p:
        plats.append(Platform(fx * W, fy * H, fw * W, fh * H))
    for fx, fy in layout_r:
        rings.append(Ring(fx * W, fy * H))
    for fx, count in layout_s:
        spikes.append(Spike(fx * W, ground_top, count=count, size=22))

    # Ground platform always present
    plats.insert(0, Platform(0, 0, W, ground_top))

    start = (60, ground_top + BALL_RADIUS + 4)
    return plats, rings, spikes, start


TOTAL_LEVELS = 3


# ------------------ Game widget ------------------
class GameArea(Widget):
    def __init__(self, hud_label, **kwargs):
        super().__init__(**kwargs)
        self.hud_label = hud_label

        # ball state
        self.bx = 60.0
        self.by = 100.0
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.spin = 0.0

        # input
        self.move_dir = 0     # -1 left, 0 none, +1 right
        self.want_jump = False

        # game state
        self.level_num = 1
        self.lives = 3
        self.score = 0
        self.state = "playing"   # playing | level_clear | gameover | win
        self.clear_timer = 0.0

        # Build first level once we know our size
        self.platforms = []
        self.rings = []
        self.spikes = []

        self.bind(size=self._on_size, pos=self._on_size)
        Clock.schedule_interval(self.update, 1 / 60.0)

        # Keyboard for desktop testing
        Window.bind(on_key_down=self._on_key_down, on_key_up=self._on_key_up)

    # ---------- input from buttons ----------
    def press_left(self):  self.move_dir = -1
    def press_right(self): self.move_dir = +1
    def release_move(self): self.move_dir = 0
    def press_jump(self):  self.want_jump = True

    def _on_key_down(self, window, key, *args):
        if key in (276, 97):    # left, a
            self.move_dir = -1
        elif key in (275, 100): # right, d
            self.move_dir = +1
        elif key in (32, 273, 119):  # space, up, w
            self.want_jump = True
        elif key == 114:        # r
            if self.state in ("gameover", "win"):
                self.reset_game()

    def _on_key_up(self, window, key, *args):
        if key in (276, 97, 275, 100):
            self.move_dir = 0

    def on_touch_down(self, touch):
        # Tap on game area (not buttons) triggers a jump
        if self.collide_point(*touch.pos):
            self.want_jump = True
            return True
        return super().on_touch_down(touch)

    # ---------- layout ----------
    def _on_size(self, *_):
        self._build_level()

    def _build_level(self):
        if self.width <= 0 or self.height <= 0:
            return
        self.platforms, self.rings, self.spikes, start = make_level(
            self.level_num, self.width, self.height
        )
        self.bx, self.by = start
        self.vx = self.vy = 0.0
        self.on_ground = True

    def reset_game(self):
        self.level_num = 1
        self.lives = 3
        self.score = 0
        self.state = "playing"
        self._build_level()

    # ---------- physics ----------
    def update(self, dt):
        if dt > 1 / 20.0:
            dt = 1 / 20.0  # clamp big steps

        if self.state == "level_clear":
            self.clear_timer -= dt
            if self.clear_timer <= 0:
                self.level_num += 1
                if self.level_num > TOTAL_LEVELS:
                    self.state = "win"
                else:
                    self.state = "playing"
                    self._build_level()
            self._draw()
            self._update_hud()
            return

        if self.state != "playing":
            self._draw()
            self._update_hud()
            return

        # Horizontal input
        if self.move_dir != 0:
            self.vx += self.move_dir * MOVE_ACCEL * dt
        else:
            # exponential friction toward 0
            self.vx *= max(0.0, 1.0 - FRICTION * dt)

        # Clamp horizontal speed
        if self.vx >  MAX_SPEED: self.vx =  MAX_SPEED
        if self.vx < -MAX_SPEED: self.vx = -MAX_SPEED

        # Jump
        if self.want_jump and self.on_ground:
            self.vy = JUMP_VEL
            self.on_ground = False
        self.want_jump = False

        # Gravity
        self.vy += GRAVITY * dt

        # Move X + collide
        self.bx += self.vx * dt
        self._collide_axis("x")

        # Move Y + collide
        prev_vy = self.vy
        self.by += self.vy * dt
        landed = self._collide_axis("y")

        # Natural bounce on hard landings
        if landed and abs(prev_vy) > 350:
            self.vy = abs(prev_vy) * BOUNCE_DAMP

        # Bounds left/right
        if self.bx < BALL_RADIUS:
            self.bx = BALL_RADIUS; self.vx = 0
        if self.bx > self.width - BALL_RADIUS:
            self.bx = self.width - BALL_RADIUS; self.vx = 0

        # Spin visual
        self.spin += self.vx * dt * 0.04

        # Ring collection
        for r in self.rings:
            if r.collected: continue
            r.t += dt * 4
            dx = self.bx - r.x
            dy = self.by - r.y
            if dx * dx + dy * dy < (BALL_RADIUS + r.r) ** 2:
                r.collected = True
                self.score += 10

        # Spike check
        for sp in self.spikes:
            sx, sy, sw, sh = sp.rect()
            # tighter hitbox
            if (self.bx + BALL_RADIUS > sx + 4 and
                self.bx - BALL_RADIUS < sx + sw - 4 and
                self.by - BALL_RADIUS < sy + sh and
                self.by + BALL_RADIUS > sy):
                self._die()
                self._draw(); self._update_hud()
                return

        # Fell off screen?
        if self.by < -50:
            self._die()

        # Level complete?
        if all(r.collected for r in self.rings) and self.state == "playing":
            if self.level_num >= TOTAL_LEVELS:
                self.state = "win"
            else:
                self.state = "level_clear"
                self.clear_timer = 1.2

        self._draw()
        self._update_hud()

    def _die(self):
        self.lives -= 1
        if self.lives <= 0:
            self.state = "gameover"
        else:
            self._build_level()

    def _collide_axis(self, axis):
        """Resolve collisions on one axis. Returns True if landed on top."""
        landed = False
        bx, by = self.bx, self.by
        r = BALL_RADIUS
        for p in self.platforms:
            px, py, pw, ph = p.rect()
            # AABB vs ball bounding box
            if (bx + r > px and bx - r < px + pw and
                by + r > py and by - r < py + ph):
                if axis == "x":
                    if self.vx > 0:
                        self.bx = px - r
                    elif self.vx < 0:
                        self.bx = px + pw + r
                    self.vx = 0
                    bx = self.bx
                else:
                    if self.vy < 0:  # falling
                        self.by = py + ph + r
                        self.vy = 0
                        landed = True
                        self.on_ground = True
                    elif self.vy > 0:  # jumping into ceiling
                        self.by = py - r
                        self.vy = 0
                    by = self.by
        if axis == "y" and not landed:
            # Probe just below to keep on_ground accurate
            self.on_ground = self._probe_ground()
        return landed

    def _probe_ground(self):
        bx, by = self.bx, self.by - 2
        r = BALL_RADIUS
        for p in self.platforms:
            px, py, pw, ph = p.rect()
            if (bx + r - 2 > px and bx - r + 2 < px + pw and
                by - r < py + ph and by + r > py):
                return True
        return False

    # ---------- drawing ----------
    def _draw(self):
        self.canvas.clear()
        with self.canvas:
            # Sky
            Color(0.53, 0.81, 0.98)
            Rectangle(pos=self.pos, size=self.size)
            Color(0.78, 0.90, 1.0)
            Rectangle(pos=self.pos, size=(self.width, self.height * 0.5))

            # Ground
            Color(0.23, 0.51, 0.23)
            Rectangle(pos=(self.x, self.y), size=(self.width, GROUND_H))
            Color(0.35, 0.66, 0.35)
            Rectangle(pos=(self.x, self.y + GROUND_H - 4), size=(self.width, 4))

            # Platforms (skip ground at index 0)
            for p in self.platforms[1:]:
                Color(0.43, 0.29, 0.18)
                Rectangle(pos=(self.x + p.x, self.y + p.y), size=(p.w, p.h))
                Color(0.59, 0.39, 0.24)
                Rectangle(pos=(self.x + p.x, self.y + p.y + p.h - 3),
                          size=(p.w, 3))

            # Rings
            for r in self.rings:
                if r.collected: continue
                bob = math.sin(r.t) * 3
                cx = self.x + r.x
                cy = self.y + r.y + bob
                Color(0.78, 0.59, 0.12)
                Ellipse(pos=(cx - r.r - 1, cy - r.r - 1),
                        size=(2 * r.r + 2, 2 * r.r + 2))
                Color(1.0, 0.82, 0.24)
                Ellipse(pos=(cx - r.r, cy - r.r), size=(2 * r.r, 2 * r.r))
                Color(1.0, 0.94, 0.63)
                Ellipse(pos=(cx - r.r + 4, cy - r.r + 4),
                        size=(2 * r.r - 8, 2 * r.r - 8))
                Color(0.78, 0.90, 1.0)
                Ellipse(pos=(cx - r.r + 7, cy - r.r + 7),
                        size=(2 * r.r - 14, 2 * r.r - 14))

            # Spikes
            for sp in self.spikes:
                for i in range(sp.count):
                    bx = self.x + sp.x + i * sp.size
                    by = self.y + sp.y
                    Color(0.23, 0.23, 0.27)
                    Triangle(points=(bx, by,
                                     bx + sp.size, by,
                                     bx + sp.size / 2, by + sp.size))

            # Ball
            cx = self.x + self.bx
            cy = self.y + self.by
            Color(0, 0, 0, 0.25)
            Ellipse(pos=(cx - BALL_RADIUS, cy - BALL_RADIUS - 4),
                    size=(2 * BALL_RADIUS, 6))
            Color(0.55, 0.08, 0.08)
            Ellipse(pos=(cx - BALL_RADIUS - 1, cy - BALL_RADIUS - 1),
                    size=(2 * BALL_RADIUS + 2, 2 * BALL_RADIUS + 2))
            Color(0.86, 0.16, 0.16)
            Ellipse(pos=(cx - BALL_RADIUS, cy - BALL_RADIUS),
                    size=(2 * BALL_RADIUS, 2 * BALL_RADIUS))
            # spinning hole detail
            ox = math.cos(self.spin) * (BALL_RADIUS - 9)
            oy = math.sin(self.spin) * (BALL_RADIUS - 9)
            Color(0.55, 0.08, 0.08)
            Ellipse(pos=(cx + ox - 5, cy + oy - 5), size=(10, 10))
            # highlight
            Color(1.0, 0.72, 0.72)
            Ellipse(pos=(cx - 8, cy + 4), size=(7, 7))

    def _update_hud(self):
        if self.state == "gameover":
            self.hud_label.text = (
                f"[b]Game Over[/b]  Score: {self.score}   Tap RESTART"
            )
        elif self.state == "win":
            self.hud_label.text = (
                f"[b]You Won![/b]  Score: {self.score}   Tap RESTART"
            )
        elif self.state == "level_clear":
            self.hud_label.text = f"[b]Level {self.level_num} cleared![/b]"
        else:
            self.hud_label.text = (
                f"Level {self.level_num}/{TOTAL_LEVELS}   "
                f"Score: {self.score}   Lives: {self.lives}"
            )


# ------------------ Root layout ------------------
class Root(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)

        # HUD
        self.hud = Label(
            text="Bounce", markup=True, size_hint_y=None, height=HUD_H,
            font_size="20sp", color=(0.1, 0.1, 0.2, 1)
        )
        self.add_widget(self.hud)

        # Game area
        self.game = GameArea(self.hud)
        self.add_widget(self.game)

        # Controls strip
        controls = BoxLayout(orientation="horizontal",
                             size_hint_y=None, height=CONTROLS_H,
                             padding=10, spacing=10)

        left_btn = Button(text="◀", font_size="36sp")
        right_btn = Button(text="▶", font_size="36sp")
        jump_btn = Button(text="JUMP", font_size="22sp")
        restart_btn = Button(text="RESTART", font_size="18sp", size_hint_x=0.6)

        left_btn.bind(on_press=lambda *_: self.game.press_left(),
                      on_release=lambda *_: self.game.release_move())
        right_btn.bind(on_press=lambda *_: self.game.press_right(),
                       on_release=lambda *_: self.game.release_move())
        jump_btn.bind(on_press=lambda *_: self.game.press_jump())
        restart_btn.bind(on_press=lambda *_: self.game.reset_game())

        controls.add_widget(left_btn)
        controls.add_widget(right_btn)
        controls.add_widget(jump_btn)
        controls.add_widget(restart_btn)
        self.add_widget(controls)


class BounceApp(App):
    title = "Bounce"
    def build(self):
        return Root()


if __name__ == "__main__":
    BounceApp().run()
