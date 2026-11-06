"""
gui.py - Interfaz gráfica (Tkinter + ttk) de OptiSolver Desktop.

Tema oscuro de bajo contraste "suave": fondo gris azulado (no negro puro),
texto casi blanco (relación de contraste > 10:1) y un único color de acento.
No requiere librerías externas: solo Tkinter y el módulo simplex.py.
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from fractions import Fraction
from tkinter import ttk
from typing import List, Optional

from simplex import (InfeasibleError, InvalidProblemError, Problem, SimplexError,
                     SimplexResult, Tableau, UnboundedError, fmt, solve)

# --------------------------------------------------------------------------
# Paleta
# --------------------------------------------------------------------------
BG = "#1e2127"          # fondo de la ventana
SURFACE = "#262b33"     # tarjetas / tablas
SURFACE_ALT = "#2b313a" # filas alternas
SURFACE2 = "#303743"    # campos de entrada, encabezados
HOVER = "#3a4352"
BORDER = "#3b4452"
FG = "#e6e9ef"          # texto principal
MUTED = "#a3adbb"       # texto secundario
ACCENT = "#7fb2f0"      # azul suave
ACCENT_DIM = "#35527a"  # fondo de la fila pivote
ON_ACCENT = "#10151c"   # texto sobre el acento
GREEN, GREEN_BG = "#a8dcb0", "#233a2a"
RED, RED_BG = "#ffb4ba", "#4a2327"
AMBER, AMBER_BG = "#f0d28a", "#4a3d1f"

MAX_DIM = 10

EXAMPLES = {
    "Primal clásico (máx, ≤)": dict(sense="Maximizar", method="primal", c=["3", "5"],
                                    A=[["1", "0"], ["0", "2"], ["3", "2"]], b=["4", "12", "18"],
                                    signs=["≤", "≤", "≤"]),
    "Dual clásico (mín, ≥)": dict(sense="Minimizar", method="dual", c=["2", "3"],
                                  A=[["1", "1"], ["1", "3"]], b=["4", "6"], signs=["≥", "≥"]),
    "Caso no acotado": dict(sense="Maximizar", method="primal", c=["1", "1"],
                            A=[["1", "-1"]], b=["1"], signs=["≤"]),
    "Caso infactible": dict(sense="Minimizar", method="dual", c=["1"],
                            A=[["1"], ["1"]], b=["5", "2"], signs=["≥", "≤"]),
}


def fmt_dec(v: Fraction) -> str:
    return fmt(v) if v.denominator == 1 else f"{fmt(v)} ≈ {float(v):.4f}"


# --------------------------------------------------------------------------
# Marco con scroll (rueda del ratón incluida)
# --------------------------------------------------------------------------
def _autohide(bar: ttk.Scrollbar, show):
    def command(lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            bar.grid_remove()
        else:
            show()
        bar.set(lo, hi)
    return command


class ScrollFrame(ttk.Frame):
    def __init__(self, master, fit_width: bool = True, horizontal: bool = False):
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.configure(yscrollcommand=_autohide(
            self.vbar, lambda: self.vbar.grid(row=0, column=1, sticky="ns")))

        self.hbar = None
        if horizontal:
            self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
            self.hbar.grid(row=1, column=0, sticky="ew")
            self.canvas.configure(xscrollcommand=_autohide(
                self.hbar, lambda: self.hbar.grid(row=1, column=0, sticky="ew")))

        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        if fit_width:
            self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))

    def scroll(self, direction: int) -> None:
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(direction * 3, "units")

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OptiSolver Desktop — Simplex Primal y Dual")
        self.geometry("1320x800")
        self.minsize(1040, 640)
        self.configure(bg=BG)

        families = set(tkfont.families())
        ui = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Noto Sans", "DejaVu Sans")
                   if f in families), "TkDefaultFont")
        mono = next((f for f in ("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")
                     if f in families), "TkFixedFont")
        self.f_ui = (ui, 10)
        self.f_bold = (ui, 10, "bold")
        self.f_title = (ui, 13, "bold")
        self.f_small = (ui, 9)
        self.f_mono = (mono, 11)
        self.f_mono_b = (mono, 11, "bold")

        self._setup_style()

        # Estado de la matriz
        self.n_var = tk.StringVar(value="2")
        self.m_var = tk.StringVar(value="3")
        self.sense_var = tk.StringVar(value="Maximizar")
        self.method_var = tk.StringVar(value="primal")
        self.example_var = tk.StringVar(value="Cargar ejemplo…")
        self.c_vars: List[tk.StringVar] = []
        self.a_vars: List[List[tk.StringVar]] = []
        self.b_vars: List[tk.StringVar] = []
        self.sign_vars: List[tk.StringVar] = []

        self._build_ui()
        self._rebuild_matrix()
        self._show_placeholder()

        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", self._on_wheel)
        self.bind_all("<Button-5>", self._on_wheel)
        self.bind("<Control-Return>", lambda e: self._solve())

    # ------------------------------------------------------------------ estilo
    def _setup_style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=SURFACE2, bordercolor=BORDER,
                    lightcolor=BG, darkcolor=BG, troughcolor=BG, font=self.f_ui, focuscolor=BG)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=SURFACE)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Card.TLabel", background=SURFACE, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED, font=self.f_small)
        s.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED, font=self.f_small)
        s.configure("Title.TLabel", font=self.f_title)
        s.configure("Section.TLabel", foreground=ACCENT, font=self.f_bold)
        s.configure("Head.TLabel", foreground=MUTED, font=self.f_bold, anchor="center")
        s.configure("CardTitle.TLabel", background=SURFACE, foreground=FG, font=self.f_bold)

        s.configure("TButton", background=SURFACE2, foreground=FG, bordercolor=BORDER,
                    padding=(14, 7), relief="flat")
        s.map("TButton", background=[("active", HOVER), ("pressed", HOVER)])
        s.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT, font=self.f_bold,
                    bordercolor=ACCENT)
        s.map("Accent.TButton", background=[("active", "#98c2f5"), ("pressed", "#98c2f5")])

        for name in ("TEntry", "Cell.TEntry"):
            s.configure(name, fieldbackground=SURFACE2, foreground=FG, insertcolor=FG,
                        bordercolor=BORDER, lightcolor=SURFACE2, darkcolor=SURFACE2, padding=4)
            s.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        s.configure("TCombobox", fieldbackground=SURFACE2, background=SURFACE2, foreground=FG,
                    arrowcolor=FG, bordercolor=BORDER, lightcolor=SURFACE2, darkcolor=SURFACE2,
                    selectbackground=SURFACE2, selectforeground=FG, padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE2)],
              selectbackground=[("readonly", SURFACE2)], selectforeground=[("readonly", FG)],
              background=[("active", HOVER)], bordercolor=[("focus", ACCENT)])
        s.configure("TSpinbox", fieldbackground=SURFACE2, background=SURFACE2, foreground=FG,
                    arrowcolor=FG, bordercolor=BORDER, lightcolor=SURFACE2, darkcolor=SURFACE2,
                    insertcolor=FG, padding=4)
        s.map("TSpinbox", bordercolor=[("focus", ACCENT)], background=[("active", HOVER)])
        s.configure("TRadiobutton", background=BG, foreground=FG, indicatorbackground=SURFACE2,
                    indicatorforeground=ACCENT)
        s.map("TRadiobutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT)],
              foreground=[("active", FG)])
        s.configure("TScrollbar", background=SURFACE2, troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, lightcolor=SURFACE2, darkcolor=SURFACE2)
        s.map("TScrollbar", background=[("active", HOVER)])
        s.configure("TSeparator", background=BORDER)

        s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=FG,
                    rowheight=28, bordercolor=SURFACE, borderwidth=0, font=self.f_mono)
        s.configure("Treeview.Heading", background=SURFACE2, foreground=FG, relief="flat",
                    font=self.f_mono_b, padding=(4, 6))
        s.map("Treeview.Heading", background=[("active", HOVER)])
        # Corrige el bug de colores de tags en algunas versiones de Tk 8.6
        def fixed_map(opt):
            return [e for e in s.map("Treeview", query_opt=opt) if e[:2] != ("!disabled", "!selected")]
        s.map("Treeview", foreground=fixed_map("foreground"), background=fixed_map("background"))

        # Lista desplegable de los Combobox (widget tk clásico)
        self.option_add("*TCombobox*Listbox.background", SURFACE2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DIM)
        self.option_add("*TCombobox*Listbox.selectForeground", FG)
        self.option_add("*TCombobox*Listbox.font", self.f_ui)

    # ---------------------------------------------------------------- interfaz
    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ---- Panel izquierdo: configuración + matriz
        left = ttk.Frame(self, padding=(16, 14, 8, 14))
        left.grid(row=0, column=0, sticky="ns")
        left.rowconfigure(4, weight=1)

        ttk.Label(left, text="OptiSolver Desktop", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(left, text="Programación lineal · Simplex Primal y Dual",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 12))

        cfg = ttk.Frame(left)
        cfg.grid(row=2, column=0, sticky="ew")
        ttk.Label(cfg, text="CONFIGURACIÓN", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        ttk.Label(cfg, text="Optimización").grid(row=1, column=0, sticky="w", pady=4)
        cb = ttk.Combobox(cfg, textvariable=self.sense_var, values=("Maximizar", "Minimizar"),
                          state="readonly", width=12)
        cb.grid(row=1, column=1, columnspan=3, sticky="w", padx=(10, 0))

        ttk.Label(cfg, text="Variables (n)").grid(row=2, column=0, sticky="w", pady=4)
        self.n_spin = ttk.Spinbox(cfg, from_=1, to=MAX_DIM, textvariable=self.n_var, width=4,
                                  command=self._rebuild_matrix)
        self.n_spin.grid(row=2, column=1, sticky="w", padx=(10, 18))
        ttk.Label(cfg, text="Restricciones (m)").grid(row=2, column=2, sticky="w")
        self.m_spin = ttk.Spinbox(cfg, from_=1, to=MAX_DIM, textvariable=self.m_var, width=4,
                                  command=self._rebuild_matrix)
        self.m_spin.grid(row=2, column=3, sticky="w", padx=(10, 0))
        for sp in (self.n_spin, self.m_spin):
            sp.bind("<Return>", lambda e: self._rebuild_matrix())
            sp.bind("<FocusOut>", lambda e: self._rebuild_matrix())

        ttk.Label(cfg, text="Algoritmo").grid(row=3, column=0, sticky="w", pady=(8, 0))
        rb = ttk.Frame(cfg)
        rb.grid(row=3, column=1, columnspan=3, sticky="w", padx=(10, 0), pady=(8, 0))
        ttk.Radiobutton(rb, text="Simplex Primal", value="primal", variable=self.method_var).pack(
            side="left", padx=(0, 14))
        ttk.Radiobutton(rb, text="Simplex Dual", value="dual", variable=self.method_var).pack(side="left")
        ttk.Label(cfg, style="Muted.TLabel", wraplength=400, justify="left",
                  text="Primal: requiere lados derechos ≥ 0.\n"
                       "Dual: requiere solución inicial superóptima (p. ej. minimizar con costos ≥ 0)."
                  ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 10))

        ttk.Label(left, text="FUNCIÓN OBJETIVO Y RESTRICCIONES", style="Section.TLabel").grid(
            row=3, column=0, sticky="w")

        self.matrix_scroll = ScrollFrame(left, fit_width=False, horizontal=True)
        self.matrix_scroll.grid(row=4, column=0, sticky="nsew", pady=(6, 10))
        self.matrix_scroll.configure(width=430)

        btns = ttk.Frame(left)
        btns.grid(row=5, column=0, sticky="ew")
        ttk.Button(btns, text="Resolver  (Ctrl+Enter)", style="Accent.TButton",
                   command=self._solve).pack(side="left")
        ttk.Button(btns, text="Limpiar", command=self._clear_all).pack(side="left", padx=8)
        ex = ttk.Combobox(left, textvariable=self.example_var, values=list(EXAMPLES), state="readonly")
        ex.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ex.bind("<<ComboboxSelected>>", self._on_example)

        # ---- Panel derecho: resultados
        right = ttk.Frame(self, padding=(8, 14, 16, 14))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        ttk.Label(right, text="Resultados e iteraciones", style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.banner_holder = ttk.Frame(right)
        self.banner_holder.grid(row=1, column=0, sticky="ew")
        self.summary_holder = ttk.Frame(right)
        self.summary_holder.grid(row=2, column=0, sticky="ew")
        self.results = ScrollFrame(right, fit_width=True)
        self.results.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

    # ------------------------------------------------------------ matriz de datos
    def _read_dims(self) -> Optional[tuple]:
        try:
            n, m = int(self.n_var.get()), int(self.m_var.get())
        except ValueError:
            return None
        return max(1, min(MAX_DIM, n)), max(1, min(MAX_DIM, m))

    def _rebuild_matrix(self) -> None:
        dims = self._read_dims()
        if dims is None:
            return
        n, m = dims
        self.n_var.set(str(n))
        self.m_var.set(str(m))

        old_c = [v.get() for v in self.c_vars]
        old_a = [[v.get() for v in row] for row in self.a_vars]
        old_b = [v.get() for v in self.b_vars]
        old_s = [v.get() for v in self.sign_vars]

        for w in self.matrix_scroll.inner.winfo_children():
            w.destroy()
        inner = self.matrix_scroll.inner

        self.c_vars = [tk.StringVar(value=old_c[j] if j < len(old_c) else "0") for j in range(n)]
        self.a_vars = [[tk.StringVar(value=old_a[i][j] if i < len(old_a) and j < len(old_a[i]) else "0")
                        for j in range(n)] for i in range(m)]
        self.b_vars = [tk.StringVar(value=old_b[i] if i < len(old_b) else "0") for i in range(m)]
        self.sign_vars = [tk.StringVar(value=old_s[i] if i < len(old_s) else "≤") for i in range(m)]

        pad = dict(padx=3, pady=3)
        ttk.Label(inner, text="").grid(row=0, column=0)
        for j in range(n):
            ttk.Label(inner, text=f"x{j + 1}", style="Head.TLabel").grid(row=0, column=j + 1, **pad)
        ttk.Label(inner, text="", width=3).grid(row=0, column=n + 1)
        ttk.Label(inner, text="LD", style="Head.TLabel").grid(row=0, column=n + 2, **pad)

        ttk.Label(inner, text="Z =", style="Section.TLabel", width=5).grid(row=1, column=0, **pad)
        for j in range(n):
            self._cell(inner, self.c_vars[j]).grid(row=1, column=j + 1, **pad)

        for i in range(m):
            ttk.Label(inner, text=f"R{i + 1}", style="Muted.TLabel", width=5,
                      anchor="center").grid(row=i + 2, column=0, **pad)
            for j in range(n):
                self._cell(inner, self.a_vars[i][j]).grid(row=i + 2, column=j + 1, **pad)
            ttk.Combobox(inner, textvariable=self.sign_vars[i], values=("≤", "≥", "="),
                         state="readonly", width=3, justify="center").grid(row=i + 2, column=n + 1, **pad)
            self._cell(inner, self.b_vars[i]).grid(row=i + 2, column=n + 2, **pad)

    def _cell(self, parent, var) -> ttk.Entry:
        e = ttk.Entry(parent, textvariable=var, width=7, justify="center", style="Cell.TEntry",
                      font=self.f_mono)
        e.bind("<FocusIn>", lambda ev: ev.widget.after(10, lambda: ev.widget.selection_range(0, "end")))
        return e

    def _on_example(self, _event=None) -> None:
        ex = EXAMPLES.get(self.example_var.get())
        if not ex:
            return
        self.sense_var.set(ex["sense"])
        self.method_var.set(ex["method"])
        self.n_var.set(str(len(ex["c"])))
        self.m_var.set(str(len(ex["b"])))
        self._rebuild_matrix()
        for j, v in enumerate(ex["c"]):
            self.c_vars[j].set(v)
        for i, row in enumerate(ex["A"]):
            for j, v in enumerate(row):
                self.a_vars[i][j].set(v)
            self.b_vars[i].set(ex["b"][i])
            self.sign_vars[i].set(ex["signs"][i])
        self._clear_results()
        self._show_placeholder()

    def _clear_all(self) -> None:
        for v in self.c_vars + self.b_vars:
            v.set("0")
        for row in self.a_vars:
            for v in row:
                v.set("0")
        for v in self.sign_vars:
            v.set("≤")
        self.example_var.set("Cargar ejemplo…")
        self._clear_results()
        self._show_placeholder()

    # ------------------------------------------------------------------- resolver
    def _read_problem(self) -> Problem:
        return Problem(
            sense="max" if self.sense_var.get() == "Maximizar" else "min",
            c=[v.get() for v in self.c_vars],
            A=[[v.get() for v in row] for row in self.a_vars],
            b=[v.get() for v in self.b_vars],
            signs=[v.get() for v in self.sign_vars],
        )

    def _solve(self) -> None:
        self._clear_results()
        try:
            problem = self._read_problem()
            result = solve(problem, self.method_var.get())
        except UnboundedError as e:
            self._banner("error", "Solución no acotada", str(e))
            self._render_tableaux(e.tableaux, "error")
        except InfeasibleError as e:
            self._banner("error", "Problema infactible", str(e))
            self._render_tableaux(e.tableaux, "error")
        except InvalidProblemError as e:
            self._banner("warn", "Datos o método no válidos", str(e))
            self._render_tableaux(e.tableaux, "error")
        except SimplexError as e:
            self._banner("error", "No se pudo resolver", str(e))
            self._render_tableaux(e.tableaux, "error")
        else:
            self._banner("ok", "Solución óptima encontrada",
                         f"Simplex {result.method.capitalize()} · {result.iterations} iteraciones")
            self._render_summary(result, problem.n_vars)
            self._render_tableaux(result.tableaux, "optimal")
        self.results.to_top()

    # ------------------------------------------------------------------- salida
    def _clear_results(self) -> None:
        for holder in (self.banner_holder, self.summary_holder, self.results.inner):
            for w in holder.winfo_children():
                w.destroy()

    def _show_placeholder(self) -> None:
        ttk.Label(self.results.inner, style="Muted.TLabel", justify="left",
                  text="Ingrese el problema a la izquierda (o cargue un ejemplo) y pulse «Resolver».\n"
                       "Aquí aparecerán la tabla inicial y cada iteración, con el pivote resaltado."
                  ).pack(anchor="w", pady=20, padx=4)

    def _banner(self, kind: str, title: str, text: str) -> None:
        bg, fg, icon = {"error": (RED_BG, RED, "✖"), "warn": (AMBER_BG, AMBER, "⚠"),
                        "ok": (GREEN_BG, GREEN, "✔")}[kind]
        box = tk.Frame(self.banner_holder, bg=bg)
        box.pack(fill="x", pady=(0, 8))
        tk.Frame(box, bg=fg, width=6).pack(side="left", fill="y")
        tk.Label(box, text=icon, bg=bg, fg=fg, font=(self.f_title[0], 18)).pack(
            side="left", padx=(14, 8), pady=10)
        col = tk.Frame(box, bg=bg)
        col.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(col, text=title, bg=bg, fg=fg, font=self.f_title, anchor="w").pack(fill="x")
        msg = tk.Label(col, text=text, bg=bg, fg=fg, font=self.f_ui, anchor="w", justify="left")
        msg.pack(fill="x")
        box.bind("<Configure>", lambda e: msg.configure(wraplength=max(200, e.width - 110)))

    def _render_summary(self, res: SimplexResult, n: int) -> None:
        card = ttk.Frame(self.summary_holder, style="Card.TFrame", padding=(14, 10))
        card.pack(fill="x", pady=(0, 4))
        card.columnconfigure(1, weight=1)

        def row(r, label, value, color=FG):
            ttk.Label(card, text=label, style="CardMuted.TLabel").grid(row=r, column=0, sticky="nw", padx=(0, 16), pady=2)
            tk.Label(card, text=value, bg=SURFACE, fg=color, font=self.f_mono_b, anchor="w",
                     justify="left").grid(row=r, column=1, sticky="w", pady=2)

        row(0, "Variables básicas", ",  ".join(f"{k} = {fmt(v)}" for k, v in res.basic_variables.items()))
        names = ", ".join(f"x{j + 1}" for j in range(n))
        row(1, "Vector óptimo x*", f"({names}) = (" + ", ".join(fmt_dec(v) for v in res.x) + ")")
        row(2, "Valor óptimo Z*", fmt_dec(res.objective), ACCENT)
        if res.alternative_optima:
            row(3, "Aviso", "Existen soluciones óptimas alternativas.", AMBER)

    def _render_tableaux(self, tableaux: List[Tableau], outcome: str) -> None:
        parent = self.results.inner
        if not tableaux:
            return
        last = len(tableaux) - 1
        for k, t in enumerate(tableaux):
            if k == 0 and k == last:
                title = "Tabla inicial" + (" (óptima)" if outcome == "optimal" else " (se detecta el problema)")
            elif k == 0:
                title = "Tabla inicial"
            elif k == last:
                title = f"Iteración {k} — " + ("tabla final (óptima)" if outcome == "optimal"
                                               else "se detecta el problema")
            else:
                title = f"Iteración {k}"
            self._tableau_card(parent, t, title)

    def _tableau_card(self, parent, t: Tableau, title: str) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        card.pack(fill="x", pady=(0, 10), padx=(0, 4))

        head = ttk.Label(card, text="▾  " + title, style="CardTitle.TLabel", cursor="hand2")
        head.pack(anchor="w")
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="x", pady=(6, 0))

        note = ttk.Label(body, text=t.note, style="CardMuted.TLabel", justify="left")
        note.pack(anchor="w", pady=(0, 6))
        body.bind("<Configure>", lambda e: note.configure(wraplength=max(200, e.width - 10)))

        self._tree(body, t)

        if t.pivot or t.leaving or t.entering:
            ttk.Label(body, style="CardMuted.TLabel",
                      text="[ ] elemento pivote    ▼ variable que entra    ◄ variable que sale"
                      ).pack(anchor="w", pady=(6, 0))

        def toggle(_e=None):
            if body.winfo_manager():
                body.pack_forget()
                head.configure(text="▸  " + title)
            else:
                body.pack(fill="x", pady=(6, 0))
                head.configure(text="▾  " + title)
        head.bind("<Button-1>", toggle)

    def _tree(self, parent, t: Tableau) -> None:
        has_ratio_col = t.ratio_axis == "row" and bool(t.ratios)
        has_ratio_row = t.ratio_axis == "col" and bool(t.ratios)
        ncols = 1 + len(t.headers) + (1 if has_ratio_col else 0)
        cols = [f"c{i}" for i in range(ncols)]

        wrap = ttk.Frame(parent, style="Card.TFrame")
        wrap.pack(fill="x")
        wrap.columnconfigure(0, weight=1)
        n_rows = len(t.rows) + 1 + (1 if has_ratio_row else 0)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", height=n_rows, selectmode="none")
        tree.grid(row=0, column=0, sticky="ew")
        xbar = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=_autohide(xbar, lambda: xbar.grid(row=1, column=0, sticky="ew")))

        entering_col = t.pivot[1] if t.pivot else None
        tree.heading(cols[0], text="Base", anchor="center")
        tree.column(cols[0], width=104, anchor="center", stretch=False)
        for j, h in enumerate(t.headers):
            label = "LD" if h == "RHS" else h
            if j == entering_col:
                label += " ▼"
            tree.heading(cols[j + 1], text=label, anchor="center")
            tree.column(cols[j + 1], width=84, anchor="center", stretch=False)
        if has_ratio_col:
            tree.heading(cols[-1], text="θ = LD/a", anchor="center")
            tree.column(cols[-1], width=96, anchor="center", stretch=False)

        tree.tag_configure("odd", background=SURFACE)
        tree.tag_configure("even", background=SURFACE_ALT)
        tree.tag_configure("pivot", background=ACCENT_DIM, foreground=FG)
        tree.tag_configure("zrow", background=SURFACE2, foreground=ACCENT)
        tree.tag_configure("ratio", background=SURFACE, foreground=MUTED)

        pr, pc = t.pivot if t.pivot else (None, None)
        for i, row in enumerate(t.rows):
            vals = [fmt(v) for v in row]
            if i == pr:
                vals[pc] = f"[{vals[pc]}]"
            base = t.basis[i] + ("  ◄" if i == pr or (pr is None and t.leaving == t.basis[i]) else "")
            line = [base] + vals
            if has_ratio_col:
                line.append(fmt(t.ratios[i]) if i in t.ratios else "—")
            tag = "pivot" if i == pr else ("odd" if i % 2 == 0 else "even")
            tree.insert("", "end", values=line, tags=(tag,))

        z_line = ["Z"] + [fmt(v) for v in t.z_row[:-1]] + [fmt(t.objective)]  # LD de Z = valor real de la F.O.
        if has_ratio_col:
            z_line.append("")
        tree.insert("", "end", values=z_line, tags=("zrow",))

        if has_ratio_row:
            r_line = ["θ = z/|a|"] + [fmt(t.ratios[j]) if j in t.ratios else "—" for j in range(len(t.headers) - 1)] + [""]
            tree.insert("", "end", values=r_line, tags=("ratio",))

    # ------------------------------------------------------------------ rueda
    def _on_wheel(self, event) -> None:
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None and not isinstance(w, ScrollFrame):
            w = w.master
        if w is None:
            return
        if getattr(event, "num", None) == 4:
            d = -1
        elif getattr(event, "num", None) == 5:
            d = 1
        else:
            d = -1 if event.delta > 0 else 1
        w.scroll(d)


def run() -> None:
    try:  # nitidez en Windows con pantallas de alta densidad
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()


if __name__ == "__main__":
    run()
