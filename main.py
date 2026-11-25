import tkinter as tk
from tkinter import ttk, messagebox
import math
import random
from database import init_db, save_record, get_top_records

# =========================
# Game settings
# =========================
COLS, ROWS = 10, 20
CELL = 30
BOARD_W, BOARD_H = COLS * CELL, ROWS * CELL
BG = "#211a14"

SHAPES = {
    "I": [[1, 1, 1, 1]],
    "O": [[1, 1], [1, 1]],
    "T": [[0, 1, 0], [1, 1, 1]],
    "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]],
    "J": [[1, 0, 0], [1, 1, 1]],
    "L": [[0, 0, 1], [1, 1, 1]],
}

# Candy/snack names and base colors for each tetromino.
SNACKS = {
    "I": ("막대과자", "#c78a43"),
    "O": ("초코쿠키", "#9a5a32"),
    "T": ("젤리", "#ec4e92"),
    "S": ("캐러멜", "#d99a45"),
    "Z": ("초콜릿", "#6b3d2a"),
    "J": ("사탕", "#49b8dc"),
    "L": ("웨하스", "#e8c77b"),
}

# 회전 후 충돌할 때 시도할 위치 보정값 (dx, dy). dy가 음수면 위로 밀어 올림.
KICKS = [(0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0), (-3, 0), (3, 0),
         (0, -1), (-1, -1), (1, -1)]

BASE_INTERVAL, LEVEL_STEP, MIN_INTERVAL = 800, 65, 90
LINE_POINTS = {1: 100, 2: 300, 3: 500, 4: 800}

# =========================
# 줄 제거 연출 설정 (줄 수가 많을수록 더 화려하게)
# =========================
FRAME_MS = 25          # 연출 1프레임 간격(ms)
POP_FRAMES = 7         # 점수 글자가 팝업으로 떠 있는 프레임 수
FLY_FRAMES = 14        # 점수 글자가 점수창으로 날아가는 프레임 수
RAINBOW = ["#ff4f8b", "#ffd24a", "#7dff8a", "#49d6ff", "#c77dff"]

CLEAR_FX = {
    1: dict(name="SINGLE",    color="#ffe6b3", banner=18, pop=20, per_cell=3,
            speed=1.0, shake=0, stars=0,  ring=False,
            flash=("#fffdf2", "#ffd24a"), badge=("#ffcc33", "#3b1d0a")),
    2: dict(name="DOUBLE!",   color="#ffd24a", banner=24, pop=26, per_cell=4,
            speed=1.2, shake=3, stars=10, ring=False,
            flash=("#fffdf2", "#ffd24a"), badge=("#ffbf24", "#3b1d0a")),
    3: dict(name="TRIPLE!!",  color="#ff9a3c", banner=30, pop=32, per_cell=5,
            speed=1.4, shake=5, stars=18, ring=True,
            flash=("#fffdf2", "#ff9a3c"), badge=("#ff8a1f", "#ffffff")),
    4: dict(name="TETRIS!!!", color="#ff4f8b", banner=34, pop=38, per_cell=6,
            speed=1.7, shake=8, stars=30, ring=True,
            flash=("#ffffff", "#ff7ab0"), badge=("#ff3d7f", "#ffffff")),
}


def rotate_matrix(matrix):
    """시계 방향 회전"""
    return [list(row) for row in zip(*matrix[::-1])]


def rotate_matrix_ccw(matrix):
    """반시계 방향 회전"""
    return [list(row) for row in zip(*matrix)][::-1]


def mix_color(c1, c2, t):
    """c1 → c2 로 t(0~1)만큼 섞은 색 (페이드 아웃에 사용)"""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def ease_out_back(t):
    """살짝 커졌다가 안착하는 '팝' 효과용 이징"""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def star_points(cx, cy, r):
    """4각 반짝이 별 폴리곤 좌표"""
    pts = []
    for i in range(8):
        ang = math.radians(i * 45)
        rad = r if i % 2 == 0 else r * 0.38
        pts += [cx + math.cos(ang) * rad, cy + math.sin(ang) * rad]
    return pts


class TetrisApp:
    def __init__(self, root):
        self.root = root
        root.title("과자 테트리스")
        root.configure(bg="#201912")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.running = False
        self.paused = False
        self.after_id = None
        self.player_name = ""
        self.canvas = None
        self.next_canvas = None
        self.ranking_win = None
        self.bag = []
        self.current = None
        self._key_bindings = []

        # 줄 제거 연출 상태
        self.animating = False
        self.fx = None
        self.hidden_rows = set()
        self.anim_after_id = None
        self.roll_after_id = None
        self.roll_active = False
        self.shown_score = 0
        self.score = 0
        self.build_start_screen()

    # ------------------------------------------------------------------
    # 화면 공통
    # ------------------------------------------------------------------
    def clear_screen(self):
        # 랭킹 창 같은 Toplevel은 건드리지 않는다.
        for widget in self.root.winfo_children():
            if not isinstance(widget, tk.Toplevel):
                widget.destroy()
        self.canvas = None
        self.next_canvas = None

    def cancel_timer(self):
        """중력(낙하) 타이머만 취소"""
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None

    def cancel_effects(self):
        """줄 제거 연출 / 점수 롤링 타이머 취소"""
        for attr in ("anim_after_id", "roll_after_id"):
            after_id = getattr(self, attr)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        self.roll_active = False

    def on_close(self):
        """창 닫기: 예약된 타이머를 정리하고 종료."""
        self.running = False
        self.cancel_timer()
        self.cancel_effects()
        self.root.destroy()

    def can_act(self):
        """플레이어 입력을 받을 수 있는 상태인지"""
        return self.running and not self.paused and not self.animating

    # ------------------------------------------------------------------
    # 키 바인딩 (게임 중에만 활성화)
    # ------------------------------------------------------------------
    def bind_game_keys(self):
        self.unbind_game_keys()
        bindings = {
            "<Left>": lambda e: self.move(-1, 0),
            "<Right>": lambda e: self.move(1, 0),
            "<Down>": lambda e: self.soft_drop(),
            "<Up>": lambda e: self.rotate(True),
            "<x>": lambda e: self.rotate(True),
            "<X>": lambda e: self.rotate(True),
            "<z>": lambda e: self.rotate(False),
            "<Z>": lambda e: self.rotate(False),
            "<space>": lambda e: self.hard_drop(),
            "<p>": lambda e: self.toggle_pause(),
            "<P>": lambda e: self.toggle_pause(),
            "<Escape>": lambda e: self.toggle_pause(),
        }
        for seq, handler in bindings.items():
            self.root.bind(seq, handler)
            self._key_bindings.append(seq)

    def unbind_game_keys(self):
        for seq in self._key_bindings:
            self.root.unbind(seq)
        self._key_bindings = []

    # ------------------------------------------------------------------
    # 시작 화면 / 게임 화면
    # ------------------------------------------------------------------
    def build_start_screen(self):
        self.clear_screen()
        frame = tk.Frame(self.root, bg="#201912", padx=34, pady=28)
        frame.pack()
        tk.Label(frame, text="🍪 과자 테트리스 🍫", font=("맑은 고딕", 24, "bold"),
                 fg="#ffe6b3", bg="#201912").pack(pady=(0, 8))
        tk.Label(frame, text="과자 블록을 쌓고 최고 점수에 도전하세요!",
                 font=("맑은 고딕", 10), fg="#d7b98b", bg="#201912").pack(pady=(0, 20))
        tk.Label(frame, text="플레이어 이름", font=("맑은 고딕", 11),
                 fg="#f4e4c1", bg="#201912").pack()
        self.name_entry = tk.Entry(frame, font=("맑은 고딕", 13), justify="center",
                                   width=18, bg="#3b2b20", fg="white",
                                   insertbackground="white", relief="flat")
        self.name_entry.pack(pady=9, ipady=7)
        self.name_entry.insert(0, self.player_name or "Player")
        self.name_entry.bind("<Return>", lambda e: self.start_game())
        tk.Button(frame, text="게임 시작", font=("맑은 고딕", 12, "bold"),
                  bg="#b96c2b", fg="white", activebackground="#96511e",
                  activeforeground="white", relief="flat", padx=24, pady=9,
                  command=self.start_game).pack(pady=(8, 10))
        tk.Button(frame, text="랭킹 보기", font=("맑은 고딕", 10),
                  bg="#60432c", fg="white", activebackground="#765638",
                  activeforeground="white", relief="flat", padx=16, pady=6,
                  command=self.show_ranking).pack()
        tk.Label(frame,
                 text="← → 이동   ↑/X 회전   Z 반대 회전   ↓ 빠른 하강\n"
                      "Space 즉시 하강   P/Esc 일시정지",
                 font=("맑은 고딕", 9), fg="#c7a980", bg="#201912",
                 justify="center").pack(pady=(22, 0))
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def build_game_screen(self):
        self.clear_screen()
        outer = tk.Frame(self.root, bg="#201912", padx=18, pady=18)
        outer.pack()
        self.fx_parent = outer  # 점수 글자가 날아다닐 때 쓰는 부모
        self.canvas = tk.Canvas(outer, width=BOARD_W, height=BOARD_H,
                                bg=BG, highlightthickness=2,
                                highlightbackground="#765638")
        self.canvas.grid(row=0, column=0, rowspan=2)
        self.draw_grid()  # 격자는 한 번만 그린다.

        side = tk.Frame(outer, bg="#201912", padx=16)
        side.grid(row=0, column=1, sticky="n")
        tk.Label(side, text="SNACK TETRIS", font=("맑은 고딕", 16, "bold"),
                 fg="#ffe6b3", bg="#201912").pack(anchor="w", pady=(0, 12))
        self.score_label = self.make_stat(side, "SCORE", "0")
        self.level_label = self.make_stat(side, "LEVEL", "1")
        self.lines_label = self.make_stat(side, "LINES", "0")
        tk.Label(side, text="NEXT SNACK", font=("맑은 고딕", 10, "bold"),
                 fg="#f4e4c1", bg="#201912").pack(anchor="w", pady=(14, 5))
        self.next_canvas = tk.Canvas(side, width=120, height=100, bg=BG,
                                     highlightthickness=1, highlightbackground="#765638")
        self.next_canvas.pack()
        tk.Button(side, text="일시정지 (P)", command=self.toggle_pause,
                  bg="#60432c", fg="white", relief="flat", pady=6,
                  takefocus=False).pack(fill="x", pady=(14, 4))
        tk.Button(side, text="게임 종료", command=self.quit_game,
                  bg="#8b3a22", fg="white", relief="flat", pady=6,
                  takefocus=False).pack(fill="x")
        tk.Label(side, text=f"PLAYER: {self.player_name}", font=("맑은 고딕", 9),
                 fg="#c7a980", bg="#201912").pack(anchor="w", pady=(12, 0))
        self.bind_game_keys()
        self.root.focus_set()

    def make_stat(self, parent, title, value):
        box = tk.Frame(parent, bg="#3b2b20", padx=10, pady=7)
        box.pack(fill="x", pady=3)
        tk.Label(box, text=title, font=("맑은 고딕", 8, "bold"),
                 fg="#d7b98b", bg="#3b2b20").pack(anchor="w")
        label = tk.Label(box, text=value, font=("맑은 고딕", 16, "bold"),
                         fg="#fff2d8", bg="#3b2b20")
        label.pack(anchor="w")
        return label

    # ------------------------------------------------------------------
    # 게임 흐름
    # ------------------------------------------------------------------
    def start_game(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("이름 입력", "플레이어 이름을 입력해주세요.")
            return
        self.cancel_timer()
        self.cancel_effects()
        self.player_name = name[:20]
        self.board = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.score, self.lines, self.level = 0, 0, 1
        self.shown_score = 0
        self.animating, self.fx, self.hidden_rows = False, None, set()
        self.bag = []
        self.running, self.paused = True, False
        self.build_game_screen()
        self.next_piece = self.make_piece()
        self.current = None
        self.spawn_piece()
        self.draw()
        self.schedule_tick()

    def next_key_from_bag(self):
        """7-bag 방식: 7종을 한 번씩 섞어 내보내 같은 블록이 몰리는 것을 방지."""
        if not self.bag:
            self.bag = list(SHAPES.keys())
            random.shuffle(self.bag)
        return self.bag.pop()

    def make_piece(self):
        key = self.next_key_from_bag()
        snack_name, color = SNACKS[key]
        return {"key": key, "name": snack_name,
                "matrix": [row[:] for row in SHAPES[key]], "color": color}

    def spawn_piece(self):
        self.current = self.next_piece
        self.next_piece = self.make_piece()
        matrix = self.current["matrix"]
        self.piece_x = (COLS - len(matrix[0])) // 2
        self.piece_y = 0
        if self.collides(self.piece_x, self.piece_y, matrix):
            self.game_over()
            return
        self.draw_next()

    def collides(self, x, y, matrix):
        for r, row in enumerate(matrix):
            for c, cell in enumerate(row):
                if not cell:
                    continue
                nx, ny = x + c, y + r
                if nx < 0 or nx >= COLS or ny >= ROWS:
                    return True
                if ny >= 0 and self.board[ny][nx] is not None:
                    return True
        return False

    def move(self, dx, dy):
        if not self.can_act():
            return
        if not self.collides(self.piece_x + dx, self.piece_y + dy, self.current["matrix"]):
            self.piece_x += dx
            self.piece_y += dy
            self.draw()

    def rotate(self, clockwise=True):
        if not self.can_act() or self.current["key"] == "O":
            return
        matrix = self.current["matrix"]
        rotated = rotate_matrix(matrix) if clockwise else rotate_matrix_ccw(matrix)
        for dx, dy in KICKS:
            if not self.collides(self.piece_x + dx, self.piece_y + dy, rotated):
                self.piece_x += dx
                self.piece_y += dy
                self.current["matrix"] = rotated
                self.draw()
                return

    def soft_drop(self):
        """한 칸 내리기. 바닥에 닿아 있으면 고정하지 않고 중력 타이머(tick)에 맡긴다.
        (키 반복 입력으로 블록이 연쇄적으로 즉시 고정되는 문제 방지)"""
        if not self.can_act():
            return
        if not self.collides(self.piece_x, self.piece_y + 1, self.current["matrix"]):
            self.piece_y += 1
            self.score += 1
            self.update_stats()
            self.draw()

    def hard_drop(self):
        if not self.can_act():
            return
        distance = 0
        while not self.collides(self.piece_x, self.piece_y + 1, self.current["matrix"]):
            self.piece_y += 1
            distance += 1
        self.score += distance * 2
        self.update_stats()
        self.lock_piece()
        if self.running and not self.animating:
            self.draw()
            self.schedule_tick()  # 새 블록이 바로 떨어지지 않도록 타이머 재시작

    def lock_piece(self):
        key = self.current["key"]
        for r, row in enumerate(self.current["matrix"]):
            for c, cell in enumerate(row):
                if cell:
                    by, bx = self.piece_y + r, self.piece_x + c
                    if 0 <= by < ROWS and 0 <= bx < COLS:
                        self.board[by][bx] = key
        full_rows = [r for r in range(ROWS) if all(self.board[r])]
        if full_rows:
            self.start_clear_animation(full_rows)   # 연출이 끝나면 다음 블록 등장
        else:
            self.spawn_piece()

    def update_stats(self):
        # 점수 롤링 중에는 롤링 애니메이션이 점수 라벨을 직접 갱신한다.
        if not self.roll_active:
            self.shown_score = self.score
            self.score_label.config(text=f"{self.score:,}")
        self.level_label.config(text=str(self.level))
        self.lines_label.config(text=str(self.lines))

    # ------------------------------------------------------------------
    # 줄 제거 연출
    #   1) 완성된 줄이 번쩍임 → 2) 블록이 과자 조각으로 폭발
    #   3) 점수 글자가 팝업 → 4) 점수창으로 날아가 점수에 합산(롤링)
    #   줄 수가 많을수록 배너/파편/흔들림/충격파/글자 크기가 커진다.
    # ------------------------------------------------------------------
    def start_clear_animation(self, rows):
        n = len(rows)
        self.animating = True
        self.cancel_timer()
        self.current = None
        points = LINE_POINTS.get(n, n * 200) * self.level
        self.fx = {
            "f": 0, "n": n, "rows": rows, "points": points,
            "cfg": CLEAR_FX[min(n, 4)],
            "flash_len": 5 + n,
            "burst_len": max(18 + 4 * n, POP_FRAMES + FLY_FRAMES + 1),
            "flash": [], "particles": [], "ring": None,
            "banner": None, "popup": None, "badge": None,
            "arrived": False, "off": (0.0, 0.0), "mid_y": BOARD_H / 2,
        }
        self.draw()
        self.anim_frame()

    def anim_frame(self):
        self.anim_after_id = None
        fx = self.fx
        if not self.running or fx is None or self.canvas is None:
            return
        f = fx["f"]
        if f < fx["flash_len"]:
            self.fx_flash(f)
        else:
            b = f - fx["flash_len"]
            if b == 0:
                self.fx_begin_burst()
            self.fx_update_burst(b)
            if b >= fx["burst_len"] and fx["arrived"]:
                self.finish_clear()
                return
        fx["f"] += 1
        self.anim_after_id = self.root.after(FRAME_MS, self.anim_frame)

    # --- 1단계: 번쩍임 -------------------------------------------------
    def fx_flash(self, f):
        fx, cv = self.fx, self.canvas
        if f == 0:
            fx["flash"] = [
                cv.create_rectangle(0, r * CELL, BOARD_W, (r + 1) * CELL,
                                    fill=fx["cfg"]["flash"][0], outline="", tags="fx")
                for r in fx["rows"]]
        color = fx["cfg"]["flash"][(f // 2) % 2]
        for item in fx["flash"]:
            cv.itemconfig(item, fill=color)

    # --- 2단계: 폭발 시작 ------------------------------------------------
    def fx_begin_burst(self):
        fx, cv, cfg, n = self.fx, self.canvas, self.fx["cfg"], self.fx["n"]
        for item in fx["flash"]:
            cv.delete(item)
        fx["flash"] = []
        self.hidden_rows = set(fx["rows"])   # 해당 줄의 블록은 파편으로 대체
        self.draw()

        # 파편: 블록 한 칸마다 여러 개의 과자 조각으로 부서진다.
        for r in fx["rows"]:
            for c in range(COLS):
                key = self.board[r][c]
                base = SNACKS[key][1]
                cx, cy = c * CELL + CELL / 2, r * CELL + CELL / 2
                palette = [base, self.lighten_color(base, 40), self.darken_color(base, 20),
                           "#ffe08a", "#fff2d8"]
                for _ in range(cfg["per_cell"]):
                    s = random.uniform(2.5, 4.5 + n * 0.6)
                    px = cx + random.uniform(-CELL / 3, CELL / 3)
                    py = cy + random.uniform(-CELL / 3, CELL / 3)
                    color = random.choice(palette)
                    maker = cv.create_rectangle if random.random() < 0.6 else cv.create_oval
                    item = maker(px - s, py - s, px + s, py + s,
                                 fill=color, outline="", tags="fx")
                    vx = random.uniform(-1, 1) * (3 + n) * cfg["speed"] + (cx - BOARD_W / 2) / 45
                    vy = random.uniform(-9, -2) * (0.8 + 0.12 * n)
                    fx["particles"].append({"id": item, "vx": vx, "vy": vy, "g": 0.75,
                                            "life": random.randint(18, 28 + 3 * n),
                                            "fade": 10, "color": color})

        # 반짝이 별 (2줄 이상)
        mid_y = sum(r * CELL + CELL / 2 for r in fx["rows"]) / len(fx["rows"])
        for _ in range(cfg["stars"]):
            sx = random.uniform(10, BOARD_W - 10)
            sy = mid_y + random.uniform(-CELL * n / 2 - 10, CELL * n / 2 + 10)
            color = random.choice(["#fff2d8", "#ffe08a", "#ffffff", "#ff9fcf"])
            item = self.canvas.create_polygon(*star_points(sx, sy, random.uniform(5, 11)),
                                              fill=color, outline="", tags="fx")
            fx["particles"].append({"id": item, "vx": random.uniform(-2.5, 2.5) * cfg["speed"],
                                    "vy": random.uniform(-6, 1), "g": 0.25,
                                    "life": random.randint(20, 36), "fade": 12, "color": color})

        # 충격파 (3줄 이상)
        fx["mid_y"] = max(70, min(BOARD_H - 70, mid_y))
        if cfg["ring"]:
            fx["ring"] = cv.create_oval(BOARD_W / 2 - 10, mid_y - 10, BOARD_W / 2 + 10, mid_y + 10,
                                        outline="#ffe08a", width=5, tags="fx")

        # 배너(SINGLE ~ TETRIS!!!)와 점수 팝업
        gap = (cfg["banner"] + cfg["pop"]) * 0.67 + 6
        banner_y = max(40, fx["mid_y"] - gap / 2)
        popup_y = min(BOARD_H - 40, fx["mid_y"] + gap / 2)
        font = ("맑은 고딕", 6, "bold")
        fx["banner"] = (
            cv.create_text(BOARD_W / 2 + 2, banner_y + 2, text=cfg["name"], font=font,
                           fill="#120c08", tags="fx"),
            cv.create_text(BOARD_W / 2, banner_y, text=cfg["name"], font=font,
                           fill=cfg["color"], tags="fx"))
        fx["popup"] = (
            cv.create_text(BOARD_W / 2 + 2, popup_y + 2, text=f"+{fx['points']:,}", font=font,
                           fill="#120c08", tags="fx"),
            cv.create_text(BOARD_W / 2, popup_y, text=f"+{fx['points']:,}", font=font,
                           fill="#ffe27a", tags="fx"))

    # --- 2~4단계: 폭발 진행 / 점수 글자 비행 / 합산 ------------------------
    def fx_update_burst(self, b):
        fx, cv, cfg, n = self.fx, self.canvas, self.fx["cfg"], self.fx["n"]

        # 파편 이동 + 페이드
        for p in fx["particles"][:]:
            p["vy"] += p["g"]
            cv.move(p["id"], p["vx"], p["vy"])
            p["life"] -= 1
            if p["life"] <= 0:
                cv.delete(p["id"])
                fx["particles"].remove(p)
            elif p["life"] < p["fade"]:
                cv.itemconfig(p["id"], fill=mix_color(p["color"], BG, 1 - p["life"] / p["fade"]))

        # 충격파
        if fx["ring"] is not None:
            if b > 22:
                cv.delete(fx["ring"])
                fx["ring"] = None
            else:
                rad = 14 + b * 15
                y = fx["mid_y"]
                cv.coords(fx["ring"], BOARD_W / 2 - rad, y - rad, BOARD_W / 2 + rad, y + rad)
                cv.itemconfig(fx["ring"], width=max(1, 6 - b // 4),
                              outline=mix_color("#ffe08a", BG, b / 22))

        # 배너: 팝 효과 → 유지 → 페이드 (TETRIS는 무지개색)
        if fx["banner"]:
            if b <= 8:
                size = max(6, int(cfg["banner"] * ease_out_back(min(1.0, b / 6))))
                for item in fx["banner"]:
                    cv.itemconfig(item, font=("맑은 고딕", size, "bold"))
            if n >= 4:
                color = RAINBOW[(b // 2) % len(RAINBOW)]
            elif n == 3:
                color = ("#ff9a3c", "#ffd24a")[(b // 3) % 2]
            else:
                color = cfg["color"]
            fade_start = fx["burst_len"] - 8
            if b >= fade_start:
                color = mix_color(color, BG, (b - fade_start) / 8)
            cv.itemconfig(fx["banner"][1], fill=color)

        # 점수 팝업 → 일정 시간 뒤 '날아가는 점수 뱃지'로 교체
        if fx["popup"]:
            if b < POP_FRAMES:
                size = max(6, int(cfg["pop"] * ease_out_back(min(1.0, b / 6))))
                for item in fx["popup"]:
                    cv.itemconfig(item, font=("맑은 고딕", size, "bold"))
            else:
                self.fx_launch_badge()
        elif fx["badge"] and not fx["arrived"]:
            self.fx_move_badge(b)

        # 화면 흔들림 (큰 콤보일수록 강하게)
        if cfg["shake"]:
            if b < 12:
                k = cfg["shake"] * (1 - b / 12)
                nx, ny = random.uniform(-k, k), random.uniform(-k, k)
            else:
                nx, ny = 0.0, 0.0
            ox, oy = fx["off"]
            if (nx, ny) != (ox, oy):
                cv.move("all", nx - ox, ny - oy)
                fx["off"] = (nx, ny)

    def fx_launch_badge(self):
        """캔버스 위 점수 글자를 같은 자리의 뱃지 위젯으로 바꿔 점수창으로 날려 보낸다."""
        fx, cv, cfg = self.fx, self.canvas, self.fx["cfg"]
        px, py = cv.coords(fx["popup"][1])[:2]
        parent = self.fx_parent
        ox = cv.winfo_rootx() - parent.winfo_rootx() + 2
        oy = cv.winfo_rooty() - parent.winfo_rooty() + 2
        sx, sy = ox + px, oy + py
        lbl = self.score_label
        tx = lbl.winfo_rootx() - parent.winfo_rootx() + lbl.winfo_width() / 2
        ty = lbl.winfo_rooty() - parent.winfo_rooty() + lbl.winfo_height() / 2
        bg, fg = cfg["badge"]
        badge = tk.Label(parent, text=f"+{fx['points']:,}", bg=bg, fg=fg,
                         font=("맑은 고딕", cfg["pop"], "bold"), padx=8, pady=1)
        badge.place(x=sx, y=sy, anchor="center")
        badge.lift()
        for item in fx["popup"]:
            cv.delete(item)
        fx["popup"] = None
        fx["badge"] = {"label": badge, "s": (sx, sy), "t": (tx, ty),
                       "c": ((sx + tx) / 2, min(sy, ty) - 70), "start": POP_FRAMES}

    def fx_move_badge(self, b):
        fx = self.fx
        info = fx["badge"]
        t = (b - info["start"]) / FLY_FRAMES
        if t >= 1:
            self.fx_arrive()
            return
        e = max(0.0, t) ** 2                       # 점점 빨라지며 점수창으로 빨려 들어감
        (sx, sy), (cx, cy), (tx, ty) = info["s"], info["c"], info["t"]
        x = (1 - e) ** 2 * sx + 2 * (1 - e) * e * cx + e ** 2 * tx
        y = (1 - e) ** 2 * sy + 2 * (1 - e) * e * cy + e ** 2 * ty
        info["label"].place(x=x, y=y, anchor="center")

    def fx_arrive(self):
        """점수 글자가 점수창에 도착 → 실제 점수에 더하고 숫자 롤링 시작"""
        fx = self.fx
        fx["badge"]["label"].destroy()
        fx["badge"] = None
        fx["arrived"] = True
        self.score += fx["points"]
        self.start_score_roll(fx["cfg"]["badge"])

    # --- 점수 롤링 -----------------------------------------------------
    def start_score_roll(self, colors):
        self.roll_active = True
        self.roll_colors = colors
        self.score_label.config(bg=colors[0], fg=colors[1],
                                font=("맑은 고딕", 20, "bold"))
        if self.roll_after_id is None:
            self.roll_step()

    def roll_step(self):
        self.roll_after_id = None
        if self.score_label is None or self.canvas is None:
            return
        diff = self.score - self.shown_score
        if diff <= 0:
            self.roll_active = False
            self.score_label.config(text=f"{self.score:,}", bg="#3b2b20", fg="#fff2d8",
                                    font=("맑은 고딕", 16, "bold"))
            return
        self.shown_score += max(1, int(diff * 0.25))
        self.score_label.config(text=f"{self.shown_score:,}")
        self.roll_after_id = self.root.after(30, self.roll_step)

    # --- 연출 종료 -------------------------------------------------------
    def finish_clear(self):
        fx = self.fx
        rows, n = set(fx["rows"]), fx["n"]
        ox, oy = fx["off"]
        if ox or oy:
            self.canvas.move("all", -ox, -oy)      # 흔들림 원위치
        self.canvas.delete("fx")
        kept = [row for i, row in enumerate(self.board) if i not in rows]
        self.board = [[None for _ in range(COLS)] for _ in range(n)] + kept
        self.hidden_rows = set()
        self.lines += n
        self.level = self.lines // 10 + 1
        self.animating = False
        self.fx = None
        self.update_stats()
        self.spawn_piece()
        if self.running:
            self.draw()
            self.schedule_tick()

    # ------------------------------------------------------------------
    # 그리기
    # ------------------------------------------------------------------
    def draw_snack_cell(self, canvas, x1, y1, size, key, inset=2, tag="snack"):
        """Draw a snack-like tile using Canvas primitives only (no external images)."""
        name, color = SNACKS[key]
        x2, y2 = x1 + size, y1 + size
        left, top, right, bottom = x1 + inset, y1 + inset, x2 - inset, y2 - inset

        # Rounded, layered base
        canvas.create_rectangle(left + 1, top + 1, right - 1, bottom - 1,
                                fill="#17110d", outline="", tags=tag)
        canvas.create_rectangle(left, top, right, bottom,
                                fill=color, outline="#f7e3c2", width=1, tags=tag)
        canvas.create_rectangle(left + 3, top + 3, right - 3, top + 7,
                                fill=self.lighten_color(color, 35), outline="", tags=tag)
        canvas.create_rectangle(left + 3, bottom - 5, right - 3, bottom - 2,
                                fill=self.darken_color(color, 25), outline="", tags=tag)

        # Snack-specific surface decorations
        cx, cy = (left + right) / 2, (top + bottom) / 2
        if key in ("O", "Z"):
            # Cookie/chocolate chips
            for dx, dy in ((-6, -4), (5, -5), (-2, 5), (7, 4)):
                canvas.create_oval(cx + dx - 2, cy + dy - 2, cx + dx + 2, cy + dy + 2,
                                   fill="#4b281c", outline="#d9a16c", width=1, tags=tag)
        elif key == "T":
            # Jelly sparkle
            canvas.create_oval(left + 5, top + 5, left + 10, top + 10,
                               fill="#ffd8eb", outline="", tags=tag)
            canvas.create_oval(right - 10, bottom - 10, right - 5, bottom - 5,
                               fill="#ffd8eb", outline="", tags=tag)
        elif key == "I":
            # Stick biscuit grooves
            for offset in (8, 14, 20):
                if size > 24:
                    canvas.create_line(left + offset, top + 7, left + offset, bottom - 7,
                                       fill="#8d5a2d", width=1, tags=tag)
        elif key == "S":
            # Caramel swirl
            canvas.create_arc(left + 5, top + 5, right - 5, bottom - 5,
                              start=25, extent=290, style="arc", outline="#fff0c8",
                              width=2, tags=tag)
        elif key == "J":
            # Candy stripes
            canvas.create_line(left + 5, bottom - 6, right - 6, top + 6,
                               fill="#d9f7ff", width=2, tags=tag)
        elif key == "L":
            # Wafer crosshatch
            canvas.create_line(left + 5, cy, right - 5, cy,
                               fill="#b88a45", width=1, tags=tag)
            canvas.create_line(cx, top + 5, cx, bottom - 5,
                               fill="#b88a45", width=1, tags=tag)

    @staticmethod
    def lighten_color(hex_color, amount=30):
        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        rgb = tuple(min(255, v + amount) for v in rgb)
        return "#%02x%02x%02x" % rgb

    @staticmethod
    def darken_color(hex_color, amount=30):
        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        rgb = tuple(max(0, v - amount) for v in rgb)
        return "#%02x%02x%02x" % rgb

    def draw_grid(self):
        for r in range(ROWS):
            for c in range(COLS):
                x1, y1 = c * CELL, r * CELL
                self.canvas.create_rectangle(x1, y1, x1 + CELL, y1 + CELL,
                                             fill=BG, outline="#3a2b20",
                                             width=1, tags="grid")

    def draw_next(self):
        if self.next_canvas is None:
            return
        self.next_canvas.delete("all")
        matrix = self.next_piece["matrix"]
        cell = 20
        width, height = len(matrix[0]) * cell, len(matrix) * cell
        ox, oy = (120 - width) // 2, (100 - height) // 2
        key = self.next_piece["key"]
        for r, row in enumerate(matrix):
            for c, val in enumerate(row):
                if val:
                    self.draw_snack_cell(self.next_canvas, ox + c * cell, oy + r * cell,
                                         cell, key, inset=1)

    def draw(self):
        """움직이는 요소(쌓인 블록, 고스트, 현재 블록)만 다시 그린다. 격자는 유지."""
        if self.canvas is None:
            return
        self.canvas.delete("dyn")
        for r in range(ROWS):
            if r in self.hidden_rows:      # 폭발 연출 중인 줄은 그리지 않는다
                continue
            for c in range(COLS):
                cell = self.board[r][c]
                if cell:
                    self.draw_snack_cell(self.canvas, c * CELL, r * CELL, CELL,
                                         cell, inset=2, tag="dyn")
        if self.running and self.current:
            matrix = self.current["matrix"]
            ghost_y = self.piece_y
            while not self.collides(self.piece_x, ghost_y + 1, matrix):
                ghost_y += 1
            # Ghost outline (현재 위치와 같으면 생략)
            if ghost_y != self.piece_y:
                for r, row in enumerate(matrix):
                    for c, val in enumerate(row):
                        if val:
                            gx, gy = self.piece_x + c, ghost_y + r
                            if gy >= 0:
                                x1, y1 = gx * CELL, gy * CELL
                                self.canvas.create_rectangle(
                                    x1 + 3, y1 + 3, x1 + CELL - 3, y1 + CELL - 3,
                                    fill="", outline="#9b8060", width=1, tags="dyn")
            for r, row in enumerate(matrix):
                for c, val in enumerate(row):
                    if val:
                        x, y = self.piece_x + c, self.piece_y + r
                        if y >= 0:
                            self.draw_snack_cell(self.canvas, x * CELL, y * CELL, CELL,
                                                 self.current["key"], inset=2, tag="dyn")
        # 연출 요소(파편/배너)는 항상 블록 위에 보이도록
        self.canvas.tag_raise("fx")

    # ------------------------------------------------------------------
    # 타이머 / 일시정지 / 종료
    # ------------------------------------------------------------------
    def schedule_tick(self):
        self.cancel_timer()
        if not self.running or self.paused or self.animating:
            return
        interval = max(MIN_INTERVAL, BASE_INTERVAL - (self.level - 1) * LEVEL_STEP)
        self.after_id = self.root.after(interval, self.tick)

    def tick(self):
        self.after_id = None
        if not self.can_act():
            return
        if not self.collides(self.piece_x, self.piece_y + 1, self.current["matrix"]):
            self.piece_y += 1
        else:
            self.lock_piece()
        if self.running and not self.animating:
            self.draw()
            self.schedule_tick()

    def toggle_pause(self):
        if not self.running or self.canvas is None or self.animating:
            return
        self.paused = not self.paused
        if self.paused:
            self.cancel_timer()
            # 일시정지 중 보드를 보고 계획 세우는 것을 막기 위해 가린다.
            self.canvas.create_rectangle(0, 0, BOARD_W, BOARD_H, fill=BG,
                                         outline="", tags="pause")
            self.canvas.create_text(BOARD_W // 2, BOARD_H // 2 - 10, text="PAUSED",
                                    fill="#fff2d8", font=("맑은 고딕", 24, "bold"),
                                    tags="pause")
            self.canvas.create_text(BOARD_W // 2, BOARD_H // 2 + 28,
                                    text="P 또는 Esc 로 계속하기",
                                    fill="#c7a980", font=("맑은 고딕", 10),
                                    tags="pause")
        else:
            self.canvas.delete("pause")
            self.draw()
            self.schedule_tick()

    def game_over(self):
        if not self.running:
            return
        self.running = False
        self.cancel_timer()
        self.cancel_effects()
        self.unbind_game_keys()
        try:
            save_record(self.player_name, self.score, self.lines, self.level)
        except Exception as exc:
            messagebox.showerror("DB 저장 오류", f"게임 기록을 저장하지 못했습니다.\n{exc}")
        self.show_game_over_screen()

    def show_game_over_screen(self):
        self.clear_screen()
        frame = tk.Frame(self.root, bg="#201912", padx=28, pady=22)
        frame.pack()
        tk.Label(frame, text="GAME OVER", font=("맑은 고딕", 36, "bold"),
                 fg="#ffcc88", bg="#201912").pack(pady=(0, 8))
        tk.Label(frame, text=f"{self.player_name}님의 점수: {self.score:,}",
                 font=("맑은 고딕", 13, "bold"), fg="#fff2d8", bg="#201912").pack(pady=4)
        tk.Label(frame, text=f"제거한 줄: {self.lines}  |  레벨: {self.level}",
                 font=("맑은 고딕", 10), fg="#d7b98b", bg="#201912").pack(pady=(0, 12))

        tk.Button(frame, text="다시 하기", command=self.build_start_screen,
                  bg="#b96c2b", fg="white", relief="flat", padx=20, pady=7).pack(pady=(8, 4))
        tk.Button(frame, text="랭킹 보기", command=self.show_ranking,
                  bg="#60432c", fg="white", relief="flat", padx=16, pady=6).pack(pady=4)
        tk.Button(frame, text="종료", command=self.on_close,
                  bg="#493427", fg="white", relief="flat", padx=16, pady=6).pack(pady=4)

    def quit_game(self):
        if not self.running or self.animating:
            return
        # 확인창이 떠 있는 동안 게임이 진행되지 않도록 잠시 멈춘다.
        was_paused = self.paused
        if not was_paused:
            self.toggle_pause()
        if messagebox.askyesno("게임 종료", "현재 게임을 종료하고 기록을 저장할까요?"):
            self.game_over()
        elif not was_paused:
            self.toggle_pause()

    def show_ranking(self):
        # 이미 열려 있으면 새로 만들지 않고 앞으로 가져온다.
        if self.ranking_win is not None and self.ranking_win.winfo_exists():
            self.ranking_win.lift()
            self.ranking_win.focus_set()
            return
        try:
            records = get_top_records(10)
        except Exception as exc:
            messagebox.showerror("DB 읽기 오류", f"랭킹을 불러오지 못했습니다.\n{exc}")
            return
        win = tk.Toplevel(self.root)
        self.ranking_win = win
        win.title("TOP 10 랭킹")
        win.configure(bg="#201912")
        win.resizable(False, False)
        win.transient(self.root)
        columns = ("rank", "name", "score", "lines", "level", "date")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=10)
        headings = {"rank": "순위", "name": "이름", "score": "점수",
                    "lines": "줄", "level": "레벨", "date": "날짜"}
        widths = {"rank": 45, "name": 110, "score": 80, "lines": 55, "level": 55, "date": 150}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="center")
        for idx, record in enumerate(records, 1):
            tree.insert("", "end", values=(idx, record["player_name"], record["score"],
                                           record["lines"], record["level"],
                                           record["played_at"]))
        tree.pack(padx=12, pady=12)
        if not records:
            tk.Label(win, text="아직 기록이 없습니다.", bg="#201912",
                     fg="white").pack(pady=(0, 12))
        tk.Button(win, text="닫기", command=win.destroy).pack(pady=(0, 12))


if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = TetrisApp(root)
    root.mainloop()
