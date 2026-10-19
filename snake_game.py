#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""贪吃蛇 · Snake

一个只依赖 Python 标准库（tkinter）的小游戏。

运行:
    python snake_game.py

操作:
    方向键 / WASD   移动
    空格 / 回车     开始、暂停、继续
    R               重新开始
    Esc             退出
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
except Exception:  # 某些精简版 Python 不带 tkinter
    tk = None
    tkfont = None


# ---------------------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------------------

COLS = 20
ROWS = 20
CELL = 26
PAD = 14
HUD_H = 76

BOARD_W = COLS * CELL
BOARD_H = ROWS * CELL
WIDTH = BOARD_W + PAD * 2
HEIGHT = HUD_H + PAD + BOARD_H + PAD

BONUS_DURATION = 7.0  # 金苹果存在时间（秒）
BONUS_SCORE = 50

SCORE_FILE = Path(__file__).resolve().with_name("snake_highscore.json")

# 配色
BG = "#0b1220"
BOARD_A = "#111d33"
BOARD_B = "#14223c"
BOARD_EDGE = "#20365a"
CARD_BG = "#101b30"
CARD_LINE = "#1e3457"
TEXT = "#eaf2ff"
MUTED = "#7890b3"
ACCENT = "#5ef2a0"
ACCENT_DIM = "#2f8f63"
GOLD = "#ffd166"
RED = "#ff5d73"
APPLE_LEAF = "#49d17f"
HEAD_COLOR = "#7bf7ad"
TAIL_COLOR = "#1f7a54"

DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
DIRECTION_SET = set(DIRECTIONS.values())


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def mix_hex(color_a: str, color_b: str, t: float) -> str:
    """在两个 #RRGGBB 颜色之间线性插值。"""
    t = max(0.0, min(1.0, t))
    a = tuple(int(color_a[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(x + (y - x) * t) for x, y in zip(a, b))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def load_high_score(path) -> int:
    """读取最高分；文件不存在或损坏时返回 0。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return max(0, int(data.get("high_score", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def save_high_score(path, score: int) -> None:
    """保存最高分，失败时静默忽略（例如目录只读）。"""
    if path is None:
        return
    try:
        Path(path).write_text(
            json.dumps({"high_score": int(score)}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# 游戏核心逻辑（不依赖界面，方便自检）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepResult:
    dead: bool = False
    ate: bool = False
    bonus: bool = False
    bonus_expired: bool = False


class SnakeModel:
    """纯逻辑的贪吃蛇模型，坐标原点在棋盘左上角。"""

    def __init__(self, cols: int = COLS, rows: int = ROWS, rng=None, clock=None):
        self.cols = cols
        self.rows = rows
        self.rng = rng or random.Random()
        self.clock = clock or time.monotonic
        self.reset()

    def reset(self) -> None:
        cx, cy = self.cols // 2, self.rows // 2
        self.snake = [(cx, cy), (cx - 1, cy), (cx - 2, cy)]
        self.direction = (1, 0)
        self._turns = deque()
        self.score = 0
        self.apples = 0
        self.level = 1
        self.food = None
        self.bonus = None
        self.bonus_expires = 0.0
        self.alive = True
        self.steps = 0
        self.food = self._random_free_cell()

    def _random_free_cell(self):
        blocked = set(self.snake)
        if self.food is not None:
            blocked.add(self.food)
        if self.bonus is not None:
            blocked.add(self.bonus)
        free = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if (x, y) not in blocked
        ]
        return self.rng.choice(free) if free else None

    def turn(self, direction) -> bool:
        """把转向加入队列。禁止 180 度回头和重复方向。"""
        direction = tuple(direction)
        if direction not in DIRECTION_SET:
            return False
        if len(self._turns) >= 3:
            return False
        base = self._turns[-1] if self._turns else self.direction
        if direction == base:
            return False
        if direction[0] == -base[0] and direction[1] == -base[1]:
            return False
        self._turns.append(direction)
        return True

    def step(self) -> StepResult:
        if not self.alive:
            return StepResult(dead=True)

        bonus_expired = False
        if self.bonus is not None and self.clock() >= self.bonus_expires:
            self.bonus = None
            bonus_expired = True

        if self._turns:
            self.direction = self._turns.popleft()

        dx, dy = self.direction
        hx, hy = self.snake[0]
        nx, ny = hx + dx, hy + dy

        if not (0 <= nx < self.cols and 0 <= ny < self.rows):
            self.alive = False
            return StepResult(dead=True, bonus_expired=bonus_expired)

        eat_food = (nx, ny) == self.food
        eat_bonus = self.bonus is not None and (nx, ny) == self.bonus
        grow = eat_food or eat_bonus

        # 不吃东西时尾巴会移开，所以尾格不算碰撞
        body = self.snake if grow else self.snake[:-1]
        if (nx, ny) in body:
            self.alive = False
            return StepResult(dead=True, bonus_expired=bonus_expired)

        self.snake.insert(0, (nx, ny))
        if not grow:
            self.snake.pop()
        self.steps += 1

        if eat_food:
            self.apples += 1
            self.score += 10
            self.level = 1 + self.apples // 5
            self.food = self._random_free_cell()

            # 每吃 5 个苹果出现一次金苹果，限时加分
            if self.apples % 5 == 0 and self.bonus is None:
                self.bonus = self._random_free_cell()
                if self.bonus is not None:
                    self.bonus_expires = self.clock() + BONUS_DURATION
            return StepResult(ate=True, bonus_expired=bonus_expired)

        if eat_bonus:
            self.bonus = None
            self.bonus_expires = 0.0
            self.score += BONUS_SCORE
            return StepResult(bonus=True, bonus_expired=bonus_expired)

        return StepResult(bonus_expired=bonus_expired)

    def tick_delay_ms(self) -> int:
        """速度随等级提升，但保留一个下限。"""
        return max(65, 150 - (self.level - 1) * 10)


# ---------------------------------------------------------------------------
# 图形界面
# ---------------------------------------------------------------------------


class SnakeApp:
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    OVER = "over"

    def __init__(self, root, high_score_path=SCORE_FILE, model=None):
        self.root = root
        self.model = model or SnakeModel()
        self.high_score_path = high_score_path
        self.high_score = load_high_score(high_score_path)
        self.new_record = False

        self.state = self.READY
        self._tick_id = None
        self._anim_id = None
        self._pulse_id = None
        self._last_action = 0.0
        self._pulse_on = True
        self._paused_at = None
        self._space_down = False
        self._r_down = False
        self.hint_id = None
        self.particles = []
        self.fx_rng = random.Random()

        self.root.withdraw()
        self.family = self._pick_font()
        self._build_window()
        self._build_board()
        self._build_hud()
        self._bind_keys()
        self._render()
        self._start_pulse()
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass
        self.canvas.focus_set()

    # ----- 初始化辅助 -------------------------------------------------

    def _pick_font(self) -> str:
        preferred = (
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "PingFang SC",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "SimHei",
            "Arial",
        )
        try:
            families = set(tkfont.families(self.root))
        except Exception:
            families = set()
        for name in preferred:
            if name in families:
                return name
        try:
            return tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:
            return "TkDefaultFont"

    def _font(self, size, bold=False):
        if bold:
            return (self.family, size, "bold")
        return (self.family, size)

    def _build_window(self) -> None:
        self.root.title("贪吃蛇 · Snake")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(
            self.root,
            width=WIDTH,
            height=HEIGHT,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()

        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - WIDTH) // 2)
        y = max(0, (screen_h - HEIGHT) // 2 - 24)
        self.root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _build_board(self) -> None:
        self.bx = PAD
        self.by = HUD_H + PAD

        # 棋盘细边框
        self.canvas.create_rectangle(
            self.bx - 2,
            self.by - 2,
            self.bx + BOARD_W + 2,
            self.by + BOARD_H + 2,
            fill=BOARD_EDGE,
            outline="",
        )

        # 静态棋盘格
        for row in range(ROWS):
            for col in range(COLS):
                color = BOARD_A if (row + col) % 2 == 0 else BOARD_B
                x1 = self.bx + col * CELL
                y1 = self.by + row * CELL
                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x1 + CELL,
                    y1 + CELL,
                    fill=color,
                    outline="",
                )

    def _build_hud(self) -> None:
        card_gap = 10
        card_w = (WIDTH - PAD * 2 - card_gap * 2) // 3
        card_h = 54
        y1, y2 = 10, 10 + card_h

        cards = (
            ("分数", str(self.model.score), ACCENT),
            ("最高分", str(max(self.high_score, self.model.score)), GOLD),
            ("等级", str(self.model.level), TEXT),
        )
        self._hud_values = []

        for index, (label, value, color) in enumerate(cards):
            x1 = PAD + index * (card_w + card_gap)
            x2 = x1 + card_w
            self._round_rect(
                x1,
                y1,
                x2,
                y2,
                13,
                fill=CARD_BG,
                outline=CARD_LINE,
                width=1,
            )
            self.canvas.create_text(
                x1 + 15,
                y1 + 16,
                text=label,
                anchor="w",
                fill=MUTED,
                font=self._font(10),
            )
            item = self.canvas.create_text(
                x1 + 15,
                y1 + 38,
                text=value,
                anchor="w",
                fill=color,
                font=self._font(15, True),
            )
            self._hud_values.append(item)

    def _bind_keys(self) -> None:
        for key, direction in (
            ("<Up>", (0, -1)),
            ("<KeyPress-w>", (0, -1)),
            ("<KeyPress-W>", (0, -1)),
            ("<Down>", (0, 1)),
            ("<KeyPress-s>", (0, 1)),
            ("<KeyPress-S>", (0, 1)),
            ("<Left>", (-1, 0)),
            ("<KeyPress-a>", (-1, 0)),
            ("<KeyPress-A>", (-1, 0)),
            ("<Right>", (1, 0)),
            ("<KeyPress-d>", (1, 0)),
            ("<KeyPress-D>", (1, 0)),
        ):
            self.root.bind(key, lambda _event, d=direction: self._on_direction(d))

        self.root.bind("<KeyPress-space>", self._on_space)
        self.root.bind("<KeyRelease-space>", self._on_space_release)
        self.root.bind("<KeyPress-Return>", self._on_space)
        self.root.bind("<KeyRelease-Return>", self._on_space_release)
        self.root.bind("<KeyPress-r>", self._on_restart)
        self.root.bind("<KeyPress-R>", self._on_restart)
        self.root.bind("<KeyRelease-r>", self._on_restart_release)
        self.root.bind("<KeyRelease-R>", self._on_restart_release)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.bind("<Escape>", lambda _event: self._close())
        self.canvas.bind("<Button-1>", lambda _event: self.canvas.focus_set())
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ----- 状态切换 ---------------------------------------------------

    def _on_direction(self, direction):
        if self.state == self.RUNNING:
            self.model.turn(direction)
        return "break"

    def _on_space(self, _event=None):
        if self._space_down:
            return "break"
        self._space_down = True

        now = time.monotonic()
        if now - self._last_action < 0.12:
            return "break"
        self._last_action = now

        if self.state == self.READY:
            self._start()
        elif self.state == self.RUNNING:
            self._pause()
        elif self.state == self.PAUSED:
            self._resume()
        else:
            self._restart()
        return "break"

    def _on_space_release(self, _event=None):
        self._space_down = False
        return "break"

    def _on_restart(self, _event=None):
        if self._r_down:
            return "break"
        self._r_down = True

        now = time.monotonic()
        if now - self._last_action < 0.12:
            return "break"
        self._last_action = now
        self._restart()
        return "break"

    def _on_restart_release(self, _event=None):
        self._r_down = False
        return "break"

    def _on_focus_out(self, _event=None):
        self._space_down = False
        self._r_down = False

    def _start(self) -> None:
        self.state = self.RUNNING
        self._paused_at = None
        self._render()
        self._schedule_tick()

    def _pause(self) -> None:
        if self.state != self.RUNNING:
            return
        self.state = self.PAUSED
        self._paused_at = time.monotonic()
        self._cancel_tick()
        self._clear_effects()
        self._render()

    def _resume(self) -> None:
        if self.state != self.PAUSED:
            return
        if self._paused_at is not None:
            paused_for = max(0.0, time.monotonic() - self._paused_at)
            if self.model.bonus is not None:
                self.model.bonus_expires += paused_for
            self._paused_at = None
        self.state = self.RUNNING
        self._render()
        self._schedule_tick()

    def _restart(self) -> None:
        self._cancel_tick()
        self._clear_effects()
        self._paused_at = None
        self.model.reset()
        self.new_record = False
        self.state = self.RUNNING
        self._render()
        self._schedule_tick()

    def _game_over(self) -> None:
        self._cancel_tick()
        self._clear_effects()
        self._paused_at = None
        self.state = self.OVER
        self.new_record = self.model.score > self.high_score and self.model.score > 0
        if self.model.score > self.high_score:
            self.high_score = self.model.score
            save_high_score(self.high_score_path, self.high_score)
        self._render()

    def _close(self) -> None:
        self._cancel_tick()
        self._clear_effects()
        if self._pulse_id is not None:
            try:
                self.root.after_cancel(self._pulse_id)
            except tk.TclError:
                pass
            self._pulse_id = None
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ----- 游戏循环 ---------------------------------------------------

    def _schedule_tick(self) -> None:
        self._cancel_tick()
        if self.state == self.RUNNING:
            self._tick_id = self.root.after(self.model.tick_delay_ms(), self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_id is not None:
            try:
                self.root.after_cancel(self._tick_id)
            except tk.TclError:
                pass
            self._tick_id = None

    def _tick(self) -> None:
        self._tick_id = None
        if self.state != self.RUNNING:
            return

        previous_level = self.model.level
        result = self.model.step()
        if result.dead:
            self._game_over()
            return

        self._render()
        if result.ate or result.bonus:
            self._spawn_burst(self.model.snake[0], golden=result.bonus)
        if self.model.level > previous_level:
            self._spawn_burst(self.model.snake[0], golden=True)

        self._schedule_tick()

    def _start_pulse(self) -> None:
        def pulse():
            if self.hint_id is not None:
                color = ACCENT if self._pulse_on else "#b7ffd4"
                try:
                    self.canvas.itemconfigure(self.hint_id, fill=color)
                except tk.TclError:
                    pass
                self._pulse_on = not self._pulse_on
            self._pulse_id = self.root.after(480, pulse)

        self._pulse_id = self.root.after(480, pulse)

    # ----- 绘制 -------------------------------------------------------

    def _round_rect(self, x1, y1, x2, y2, radius, **kwargs):
        r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        points = (
            x1 + r,
            y1,
            x2 - r,
            y1,
            x2,
            y1,
            x2,
            y1 + r,
            x2,
            y2 - r,
            x2,
            y2,
            x2 - r,
            y2,
            x1 + r,
            y2,
            x1,
            y2,
            x1,
            y2 - r,
            x1,
            y1 + r,
            x1,
            y1,
        )
        return self.canvas.create_polygon(
            points, smooth=True, splinesteps=18, **kwargs
        )

    def _cell_center(self, cell):
        x, y = cell
        return (
            self.bx + x * CELL + CELL / 2,
            self.by + y * CELL + CELL / 2,
        )

    def _render(self) -> None:
        self.canvas.delete("dyn")
        self._draw_food()
        self._draw_snake()
        self._draw_overlay()
        self._update_hud()

    def _update_hud(self) -> None:
        self.canvas.itemconfigure(self._hud_values[0], text=str(self.model.score))
        self.canvas.itemconfigure(
            self._hud_values[1],
            text=str(max(self.high_score, self.model.score)),
        )
        self.canvas.itemconfigure(self._hud_values[2], text=str(self.model.level))

    def _draw_food(self) -> None:
        if self.model.food is not None:
            self._draw_apple(self.model.food, golden=False)
        if self.model.bonus is not None:
            self._draw_apple(self.model.bonus, golden=True)
            self._draw_bonus_timer(self.model.bonus)

    def _draw_apple(self, cell, golden=False) -> None:
        cx, cy = self._cell_center(cell)
        r = CELL * 0.30
        body = GOLD if golden else RED
        edge = "#9c6b08" if golden else "#b52d45"
        shine = "#fff3c4" if golden else "#ffc2cb"

        # 阴影
        self.canvas.create_oval(
            cx - r + 1,
            cy - r + 2,
            cx + r + 1,
            cy + r + 2,
            fill="#08111f",
            outline="",
            tags="dyn",
        )
        # 果身
        self.canvas.create_oval(
            cx - r,
            cy - r,
            cx + r,
            cy + r * 0.92,
            fill=body,
            outline=edge,
            width=1,
            tags="dyn",
        )
        # 高光
        self.canvas.create_oval(
            cx - r * 0.52,
            cy - r * 0.56,
            cx - r * 0.10,
            cy - r * 0.18,
            fill=shine,
            outline="",
            tags="dyn",
        )
        # 果梗
        self.canvas.create_line(
            cx,
            cy - r * 0.82,
            cx + 1.5,
            cy - r * 1.28,
            fill="#8b5a2b",
            width=2,
            capstyle="round",
            tags="dyn",
        )
        # 叶子
        self.canvas.create_oval(
            cx + 1,
            cy - r * 1.42,
            cx + r * 0.78,
            cy - r * 0.98,
            fill=APPLE_LEAF if not golden else "#ffe08a",
            outline="",
            tags="dyn",
        )

    def _draw_bonus_timer(self, cell) -> None:
        cx, cy = self._cell_center(cell)
        # 暂停时冻结倒计时显示
        if self.state == self.PAUSED and self._paused_at is not None:
            now = self._paused_at
        else:
            now = time.monotonic()
        remaining = max(0.0, self.model.bonus_expires - now)
        fraction = min(1.0, remaining / BONUS_DURATION)
        extent = -max(2, int(359 * fraction))

        pulse = (math.sin(now * 5.5) + 1.0) / 2.0
        glow_r = 12.0 + pulse * 2.5
        self.canvas.create_oval(
            cx - glow_r,
            cy - glow_r,
            cx + glow_r,
            cy + glow_r,
            outline="#6b4e0f",
            width=1,
            tags="dyn",
        )
        self.canvas.create_arc(
            cx - 11,
            cy - 11,
            cx + 11,
            cy + 11,
            start=90,
            extent=extent,
            style="arc",
            outline=GOLD,
            width=2,
            tags="dyn",
        )

    def _draw_snake(self) -> None:
        snake = self.model.snake
        count = len(snake)
        alive = self.model.alive

        for index in range(count - 1, -1, -1):
            x, y = snake[index]
            t = index / max(1, count - 1)
            color = mix_hex(HEAD_COLOR, TAIL_COLOR, t)
            if not alive:
                color = mix_hex(color, "#4a5b70", 0.65)

            inset = 1.2 if index == 0 else 2.2
            x1 = self.bx + x * CELL + inset
            y1 = self.by + y * CELL + inset
            x2 = self.bx + (x + 1) * CELL - inset
            y2 = self.by + (y + 1) * CELL - inset
            radius = 7.5 if index == 0 else 6.0
            self._round_rect(
                x1,
                y1,
                x2,
                y2,
                radius,
                fill=color,
                outline="",
                tags="dyn",
            )

            if index == 0:
                self._draw_eyes(x, y)

    def _draw_eyes(self, x, y) -> None:
        cx, cy = self._cell_center((x, y))
        dx, dy = self.model.direction
        px, py = -dy, dx
        eye_forward = 4.5
        eye_side = 5.0
        eye_r = 2.7

        for side in (-1, 1):
            ex = cx + dx * eye_forward + px * eye_side * side
            ey = cy + dy * eye_forward + py * eye_side * side
            if not self.model.alive:
                self.canvas.create_line(
                    ex - 2.2,
                    ey - 2.2,
                    ex + 2.2,
                    ey + 2.2,
                    fill="#12231b",
                    width=1.6,
                    tags="dyn",
                )
                self.canvas.create_line(
                    ex - 2.2,
                    ey + 2.2,
                    ex + 2.2,
                    ey - 2.2,
                    fill="#12231b",
                    width=1.6,
                    tags="dyn",
                )
            else:
                self.canvas.create_oval(
                    ex - eye_r,
                    ey - eye_r,
                    ex + eye_r,
                    ey + eye_r,
                    fill="#f7fff9",
                    outline="",
                    tags="dyn",
                )
                pupil_x = ex + dx * 0.9
                pupil_y = ey + dy * 0.9
                self.canvas.create_oval(
                    pupil_x - 1.25,
                    pupil_y - 1.25,
                    pupil_x + 1.25,
                    pupil_y + 1.25,
                    fill="#0b2e1f",
                    outline="",
                    tags="dyn",
                )

    def _draw_overlay(self) -> None:
        self.canvas.delete("overlay")
        self.hint_id = None
        if self.state == self.RUNNING:
            return

        panel_w, panel_h = 404, 246
        px1 = (WIDTH - panel_w) // 2
        py1 = (HEIGHT - panel_h) // 2 + 6
        px2, py2 = px1 + panel_w, py1 + panel_h
        cx = WIDTH // 2

        self.canvas.create_rectangle(
            0,
            0,
            WIDTH,
            HEIGHT,
            fill="#040a14",
            stipple="gray50",
            outline="",
            tags="overlay",
        )
        self._round_rect(
            px1 + 4,
            py1 + 5,
            px2 + 4,
            py2 + 5,
            20,
            fill="#050b15",
            outline="",
            tags="overlay",
        )
        self._round_rect(
            px1,
            py1,
            px2,
            py2,
            20,
            fill="#0d1930",
            outline="#28456b",
            width=1,
            tags="overlay",
        )

        if self.state == self.READY:
            title, title_color = "贪 吃 蛇", ACCENT
            message, message_color = "吃掉苹果，别撞墙，也别咬到自己", TEXT
            hint = "按 空格 开始"
            small = "方向键 / WASD 移动    ·    R 重新开始"
        elif self.state == self.PAUSED:
            title, title_color = "已暂停", GOLD
            message = f"当前分数 {self.model.score}    ·    等级 {self.model.level}"
            message_color = TEXT
            hint = "按 空格 继续"
            small = "R 重新开始    ·    Esc 退出"
        else:
            title, title_color = "游戏结束", RED
            if self.new_record:
                message, message_color = "★ 新纪录 ★", GOLD
            else:
                message, message_color = f"本局得分 {self.model.score}", TEXT
            hint = "按 空格 或 R 再来一局"
            small = f"最高分 {self.high_score}"

        self.canvas.create_text(
            cx,
            py1 + 27,
            text="S N A K E",
            fill=MUTED,
            font=self._font(8, True),
            tags="overlay",
        )
        self.canvas.create_text(
            cx,
            py1 + 61,
            text=title,
            fill=title_color,
            font=self._font(25, True),
            tags="overlay",
        )
        self.canvas.create_line(
            cx - 24,
            py1 + 86,
            cx + 24,
            py1 + 86,
            fill=ACCENT_DIM,
            width=2,
            capstyle="round",
            tags="overlay",
        )
        self.canvas.create_text(
            cx,
            py1 + 114,
            text=message,
            fill=message_color,
            font=self._font(11),
            tags="overlay",
        )
        self.hint_id = self.canvas.create_text(
            cx,
            py1 + 158,
            text=hint,
            fill=ACCENT,
            font=self._font(13, True),
            tags="overlay",
        )
        self.canvas.create_text(
            cx,
            py1 + 198,
            text=small,
            fill=MUTED,
            font=self._font(10),
            tags="overlay",
        )

    # ----- 粒子特效 ---------------------------------------------------

    def _spawn_burst(self, cell, golden=False) -> None:
        cx, cy = self._cell_center(cell)
        if golden:
            palette = ("#ffe08a", GOLD, "#fff6d0")
        else:
            palette = (RED, "#ff9aa8", GOLD)

        for _ in range(14):
            angle = self.fx_rng.uniform(0, math.tau)
            speed = self.fx_rng.uniform(1.0, 3.2)
            life = self.fx_rng.randint(14, 24)
            self.particles.append(
                {
                    "x": cx,
                    "y": cy,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed - 0.7,
                    "drag": 0.96,
                    "gravity": 0.22,
                    "life": life,
                    "max_life": life,
                    "size": self.fx_rng.uniform(1.6, 3.2),
                    "color": self.fx_rng.choice(palette),
                }
            )

        if self._anim_id is None:
            self._anim_id = self.root.after(20, self._animate)

    def _animate(self) -> None:
        self._anim_id = None
        self.canvas.delete("fx")
        alive = []

        for particle in self.particles:
            particle["x"] += particle["vx"]
            particle["y"] += particle["vy"]
            particle["vy"] += particle["gravity"]
            particle["vx"] *= particle["drag"]
            particle["life"] -= 1
            if particle["life"] <= 0:
                continue
            fraction = particle["life"] / particle["max_life"]
            radius = max(0.6, particle["size"] * fraction)
            self.canvas.create_oval(
                particle["x"] - radius,
                particle["y"] - radius,
                particle["x"] + radius,
                particle["y"] + radius,
                fill=particle["color"],
                outline="",
                tags="fx",
            )
            alive.append(particle)

        self.particles = alive
        if alive:
            self._anim_id = self.root.after(25, self._animate)
        else:
            self.canvas.delete("fx")

    def _clear_effects(self) -> None:
        self.particles.clear()
        self.canvas.delete("fx")
        if self._anim_id is not None:
            try:
                self.root.after_cancel(self._anim_id)
            except tk.TclError:
                pass
            self._anim_id = None


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _run_selftest() -> int:
    def test_initial_state():
        model = SnakeModel(10, 10, rng=random.Random(1), clock=FakeClock())
        assert len(model.snake) == 3, "初始长度应为 3"
        assert model.direction == (1, 0), "初始方向应向右"
        assert model.alive is True
        assert model.food is not None
        assert model.food not in model.snake, "食物不能刷在蛇身上"
        assert model.score == 0 and model.level == 1

    def test_reverse_is_rejected():
        model = SnakeModel(10, 10, rng=random.Random(2))
        assert model.turn((-1, 0)) is False, "不能直接 180 度回头"
        assert model.turn((0, -1)) is True, "垂直转向应被接受"
        model.step()
        assert model.direction == (0, -1), "转向应在下一次移动生效"

    def test_wall_collision():
        model = SnakeModel(10, 10, rng=random.Random(3))
        model.snake = [(9, 5), (8, 5), (7, 5)]
        model.direction = (1, 0)
        model._turns.clear()
        model.food = (0, 0)
        result = model.step()
        assert result.dead is True and model.alive is False, "撞墙应结束游戏"

    def test_self_collision():
        model = SnakeModel(10, 10, rng=random.Random(4))
        model.snake = [(5, 5), (5, 6), (6, 6), (6, 5), (6, 4)]
        model.direction = (1, 0)
        model._turns.clear()
        model.food = (0, 0)
        result = model.step()
        assert result.dead is True, "撞到自己应结束游戏"

    def test_eating_food():
        model = SnakeModel(10, 10, rng=random.Random(5))
        head = model.snake[0]
        ahead = (head[0] + 1, head[1])
        model.food = ahead
        model.bonus = None
        before = len(model.snake)
        result = model.step()
        assert result.ate is True, "吃到食物应返回 ate"
        assert model.score == 10
        assert len(model.snake) == before + 1, "吃到食物应增长一格"
        assert model.food not in model.snake, "新食物不能刷在蛇身上"

    def test_bonus_spawn_and_expire():
        clock = FakeClock()
        model = SnakeModel(10, 10, rng=random.Random(6), clock=clock)
        head = model.snake[0]
        model.apples = 4
        model.food = (head[0] + 1, head[1])
        model.bonus = None
        model.step()
        assert model.apples == 5
        assert model.bonus is not None, "第 5 个苹果后应出现金苹果"
        assert model.bonus not in model.snake
        assert model.bonus != model.food

        clock.advance(BONUS_DURATION + 0.1)
        result = model.step()
        assert result.bonus_expired is True, "超时后应返回 expired"
        assert model.bonus is None, "金苹果超时后应消失"

    def test_eating_bonus():
        model = SnakeModel(10, 10, rng=random.Random(7), clock=FakeClock())
        head = model.snake[0]
        model.food = (0, 0)
        model.bonus = (head[0] + 1, head[1])
        model.bonus_expires = model.clock() + 5
        result = model.step()
        assert result.bonus is True
        assert model.score == BONUS_SCORE
        assert model.bonus is None

    def test_food_never_on_snake():
        for seed in range(20):
            model = SnakeModel(12, 12, rng=random.Random(seed))
            for _ in range(30):
                if model.food is None:
                    break
                assert model.food not in model.snake
                if model.bonus is not None:
                    assert model.bonus not in model.snake
                    assert model.bonus != model.food
                result = model.step()
                if result.dead:
                    break

    def test_highscore_io():
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "score.json"
            assert load_high_score(path) == 0
            save_high_score(path, 1234)
            assert load_high_score(path) == 1234
            path.write_text("not json", encoding="utf-8")
            assert load_high_score(path) == 0

    tests = [
        ("初始状态", test_initial_state),
        ("禁止 180 度回头", test_reverse_is_rejected),
        ("撞墙判定", test_wall_collision),
        ("自撞判定", test_self_collision),
        ("吃苹果与增长", test_eating_food),
        ("金苹果生成与过期", test_bonus_spawn_and_expire),
        ("吃金苹果加分", test_eating_bonus),
        ("食物不会刷在蛇身上", test_food_never_on_snake),
        ("最高分读写", test_highscore_io),
    ]

    print("贪吃蛇逻辑自检")
    print("-" * 36)
    failed = 0
    for name, test in tests:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {name}: {exc}")
        else:
            print(f"[ OK ] {name}")

    total = len(tests)
    print("-" * 36)
    print(f"{total - failed}/{total} 项通过")
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="贪吃蛇 · Snake（Python 小游戏）")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="只运行游戏逻辑自检，不打开窗口",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return _run_selftest()

    if tk is None:
        print("未找到 tkinter。Windows 官方 Python 通常自带；Linux 可安装 python3-tk。")
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"无法创建游戏窗口：{exc}")
        return 1

    SnakeApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
