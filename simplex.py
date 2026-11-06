"""
simplex.py - Motor Simplex Primal y Dual para OptiSolver Desktop.

Lógica pura: no depende de Tkinter ni de ninguna librería externa.
Usa fractions.Fraction para que las tablas sean exactas (sin 0.33333...).

Uso rápido
----------
    from simplex import Problem, solve

    p = Problem(sense="max", c=[3, 5],
                A=[[1, 0], [0, 2], [3, 2]],
                b=[4, 12, 18],
                signs=["<=", "<=", "<="])
    res = solve(p, method="primal")
    for t in res.tableaux:          # una tabla por iteración
        ...
    print(res.x, res.objective)

Si el problema es no acotado o infactible se lanza UnboundedError /
InfeasibleError. Ambas llevan el atributo `.tableaux` con las tablas
generadas hasta ese momento, para poder mostrarlas junto a la alerta.

Convención interna (forma estándar)
-----------------------------------
* Todo se convierte a MAXIMIZAR (si es minimizar, c se multiplica por -1).
* Las restricciones >= se multiplican por -1 para quedar como <=.
* Las restricciones = se parten en dos (<= y >=).
* Cada fila recibe una variable de holgura; la base inicial son las holguras.
* Renglón Z:  Z - c1*x1 - ... = 0, es decir se guardan los valores -cj.
  Óptimo (primal) cuando todos los valores del renglón Z son >= 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple, Union

Number = Union[int, float, str, Fraction]

MAX_ITERATIONS = 500  # protección contra ciclos


# --------------------------------------------------------------------------
# Excepciones
# --------------------------------------------------------------------------
class SimplexError(Exception):
    """Error base. `tableaux` guarda las tablas generadas antes del fallo."""

    def __init__(self, message: str, tableaux: Optional[List["Tableau"]] = None):
        super().__init__(message)
        self.tableaux: List[Tableau] = tableaux or []


class InvalidProblemError(SimplexError):
    """Datos mal formados o problema no apto para el método elegido."""


class UnboundedError(SimplexError):
    """Solución no acotada (la función objetivo crece sin límite)."""


class InfeasibleError(SimplexError):
    """Problema sin región factible."""


class IterationLimitError(SimplexError):
    """Se superó el máximo de iteraciones (posible ciclado)."""


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def to_fraction(value: Number) -> Fraction:
    """Convierte int/float/str ('1/3', '0.5', '2,5') a Fraction exacta."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):
        raise InvalidProblemError(f"Valor no numérico: {value!r}")
    if isinstance(value, float):
        return Fraction(str(value))
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            raise InvalidProblemError("Hay una celda vacía.")
        try:
            return Fraction(text)
        except (ValueError, ZeroDivisionError):
            raise InvalidProblemError(f"Valor no numérico: {value!r}")
    try:
        return Fraction(value)
    except (TypeError, ValueError):
        raise InvalidProblemError(f"Valor no numérico: {value!r}")


def fmt(value: Fraction) -> str:
    """'5', '-1/3'. Útil para mostrar en la interfaz."""
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


# --------------------------------------------------------------------------
# Modelos de datos
# --------------------------------------------------------------------------
@dataclass
class Problem:
    """Problema de PL tal como lo captura el usuario.

    sense : "max" | "min"
    c     : coeficientes de la función objetivo (n)
    A     : matriz de restricciones (m x n)
    b     : lados derechos (m)
    signs : "<=", ">=" o "=" por restricción (m)
    """

    sense: str
    c: Sequence[Number]
    A: Sequence[Sequence[Number]]
    b: Sequence[Number]
    signs: Optional[Sequence[str]] = None

    def __post_init__(self) -> None:
        self.sense = str(self.sense).strip().lower()
        if self.sense in ("maximizar", "maximize"):
            self.sense = "max"
        if self.sense in ("minimizar", "minimize"):
            self.sense = "min"
        if self.sense not in ("max", "min"):
            raise InvalidProblemError("El tipo de optimización debe ser 'max' o 'min'.")

        self.c = [to_fraction(v) for v in self.c]
        self.A = [[to_fraction(v) for v in row] for row in self.A]
        self.b = [to_fraction(v) for v in self.b]
        n, m = len(self.c), len(self.A)

        if n == 0 or m == 0:
            raise InvalidProblemError("Se requiere al menos 1 variable y 1 restricción.")
        if any(len(row) != n for row in self.A):
            raise InvalidProblemError("Cada restricción debe tener un coeficiente por variable.")
        if len(self.b) != m:
            raise InvalidProblemError("Debe haber un lado derecho por restricción.")

        if self.signs is None:
            self.signs = ["<="] * m
        self.signs = [str(s).strip().replace("≤", "<=").replace("≥", ">=") for s in self.signs]
        if len(self.signs) != m:
            raise InvalidProblemError("Debe haber un signo por restricción.")
        if any(s not in ("<=", ">=", "=") for s in self.signs):
            raise InvalidProblemError("Los signos válidos son '<=', '>=' y '='.")

    @property
    def n_vars(self) -> int:
        return len(self.c)


@dataclass
class Tableau:
    """Foto de una tabla del Simplex (lista para dibujarse en la GUI)."""

    iteration: int
    headers: List[str]                 # x1..xn, s1..sm, "RHS"
    basis: List[str]                   # variable básica de cada fila
    rows: List[List[Fraction]]         # filas de restricciones (incluye RHS)
    z_row: List[Fraction]              # renglón Z (incluye valor de Z en RHS)
    objective: Fraction                # valor de la F.O. en el sentido original
    pivot: Optional[Tuple[int, int]] = None   # (fila, columna) del pivote
    entering: Optional[str] = None
    leaving: Optional[str] = None
    ratios: Dict[int, Fraction] = field(default_factory=dict)  # índice -> cociente
    ratio_axis: str = ""               # "row" (primal) o "col" (dual)
    note: str = ""                     # explicación en español

    def as_float_rows(self) -> List[List[float]]:
        return [[float(v) for v in r] for r in self.rows + [self.z_row]]


@dataclass
class SimplexResult:
    status: str                        # "optimal"
    method: str                        # "primal" | "dual"
    tableaux: List[Tableau]
    x: List[Fraction]                  # valores de las variables de decisión
    objective: Fraction                # valor óptimo (sentido original)
    basic_variables: Dict[str, Fraction]
    alternative_optima: bool           # hay variable no básica con costo reducido 0
    iterations: int

    def summary(self) -> str:
        lines = [f"Estado: {self.status} (Simplex {self.method}, {self.iterations} iteraciones)"]
        lines.append("Variables básicas: " + ", ".join(f"{k} = {fmt(v)}" for k, v in self.basic_variables.items()))
        lines.append("x* = (" + ", ".join(fmt(v) for v in self.x) + ")")
        lines.append(f"Z* = {fmt(self.objective)}")
        if self.alternative_optima:
            lines.append("Aviso: existen soluciones óptimas alternativas.")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Motor interno
# --------------------------------------------------------------------------
class _Engine:
    """Tabla mutable (m+1) x (N+1). Última fila = Z, última columna = RHS."""

    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        self.sense = problem.sense
        n = problem.n_vars

        # 1) Forma estándar: todo en <=, objetivo en maximizar
        rows: List[Tuple[List[Fraction], Fraction]] = []
        for coef, rhs, sign in zip(problem.A, problem.b, problem.signs):
            if sign == "<=":
                rows.append((list(coef), rhs))
            elif sign == ">=":
                rows.append(([-a for a in coef], -rhs))
            else:  # "=" -> dos desigualdades
                rows.append((list(coef), rhs))
                rows.append(([-a for a in coef], -rhs))

        c_max = list(problem.c) if self.sense == "max" else [-v for v in problem.c]
        m = len(rows)
        self.n, self.m = n, m
        self.N = n + m

        self.headers = [f"x{j + 1}" for j in range(n)] + [f"s{i + 1}" for i in range(m)] + ["RHS"]
        self.basis_idx = [n + i for i in range(m)]  # índices de columna de la base

        # 2) Tabla inicial
        self.T: List[List[Fraction]] = []
        for i, (coef, rhs) in enumerate(rows):
            slack = [Fraction(1) if k == i else Fraction(0) for k in range(m)]
            self.T.append(coef + slack + [rhs])
        self.T.append([-v for v in c_max] + [Fraction(0)] * m + [Fraction(0)])

        self.tableaux: List[Tableau] = []

    # ---- acceso rápido
    @property
    def z(self) -> List[Fraction]:
        return self.T[-1]

    def objective_value(self) -> Fraction:
        z = self.z[-1]
        return z if self.sense == "max" else -z

    def snapshot(self, **kw) -> Tableau:
        t = Tableau(
            iteration=len(self.tableaux),
            headers=list(self.headers),
            basis=[self.headers[j] for j in self.basis_idx],
            rows=[row[:] for row in self.T[:-1]],
            z_row=self.T[-1][:],
            objective=self.objective_value(),
            **kw,
        )
        self.tableaux.append(t)
        return t

    def pivot(self, r: int, c: int) -> None:
        """Operación Gauss-Jordan sobre el elemento (r, c)."""
        p = self.T[r][c]
        self.T[r] = [v / p for v in self.T[r]]
        for i in range(len(self.T)):
            if i != r and self.T[i][c] != 0:
                f = self.T[i][c]
                self.T[i] = [a - f * b for a, b in zip(self.T[i], self.T[r])]
        self.basis_idx[r] = c

    # ---- Simplex PRIMAL ---------------------------------------------------
    def run_primal(self) -> None:
        if any(self.T[i][-1] < 0 for i in range(self.m)):
            self.snapshot(note="Tabla inicial: hay lados derechos negativos.")
            raise InvalidProblemError(
                "El Simplex Primal requiere lados derechos >= 0 (solución inicial factible). "
                "Con restricciones >= o RHS negativos use el Simplex Dual.",
                self.tableaux,
            )

        while True:
            if len(self.tableaux) > MAX_ITERATIONS:
                raise IterationLimitError("Se superó el máximo de iteraciones.", self.tableaux)

            # Criterio de entrada: valor más negativo del renglón Z
            col, most_neg = None, Fraction(0)
            for j in range(self.N):
                if self.z[j] < most_neg:
                    most_neg, col = self.z[j], j

            if col is None:
                self.snapshot(note="Óptimo: no hay valores negativos en el renglón Z.")
                return

            # Criterio de salida: cociente mínimo (solo a_ij > 0)
            ratios: Dict[int, Fraction] = {}
            row = None
            for i in range(self.m):
                a = self.T[i][col]
                if a > 0:
                    q = self.T[i][-1] / a
                    ratios[i] = q
                    if (row is None or q < ratios[row]
                            or (q == ratios[row] and self.basis_idx[i] < self.basis_idx[row])):
                        row = i

            entering = self.headers[col]
            if row is None:
                self.snapshot(
                    entering=entering, ratios=ratios, ratio_axis="row",
                    note=f"Entra {entering} pero su columna no tiene elementos positivos: no acotado.",
                )
                raise UnboundedError(
                    f"Solución no acotada: al aumentar {entering} la función objetivo "
                    "crece indefinidamente sin que ninguna restricción lo limite.",
                    self.tableaux,
                )

            leaving = self.headers[self.basis_idx[row]]
            self.snapshot(
                pivot=(row, col), entering=entering, leaving=leaving,
                ratios=ratios, ratio_axis="row",
                note=f"Entra {entering} (valor más negativo en Z: {fmt(most_neg)}); "
                     f"sale {leaving} (cociente mínimo {fmt(ratios[row])}).",
            )
            self.pivot(row, col)

    # ---- Simplex DUAL -----------------------------------------------------
    def run_dual(self) -> None:
        if any(self.z[j] < 0 for j in range(self.N)):
            self.snapshot(note="Tabla inicial: el renglón Z tiene valores negativos.")
            raise InvalidProblemError(
                "El Simplex Dual requiere una solución inicial superóptima: todos los valores "
                "del renglón Z deben ser >= 0 (por ejemplo, minimizar con costos >= 0). "
                "Use el Simplex Primal si los lados derechos son >= 0.",
                self.tableaux,
            )

        while True:
            if len(self.tableaux) > MAX_ITERATIONS:
                raise IterationLimitError("Se superó el máximo de iteraciones.", self.tableaux)

            # Criterio de salida: RHS más negativo
            row, most_neg = None, Fraction(0)
            for i in range(self.m):
                if self.T[i][-1] < most_neg:
                    most_neg, row = self.T[i][-1], i

            if row is None:
                self.snapshot(note="Óptimo: todos los lados derechos son >= 0 (solución factible).")
                return

            leaving = self.headers[self.basis_idx[row]]

            # Criterio de entrada: min |z_j / a_rj| con a_rj < 0
            ratios: Dict[int, Fraction] = {}
            col = None
            for j in range(self.N):
                a = self.T[row][j]
                if a < 0:
                    q = self.z[j] / (-a)
                    ratios[j] = q
                    if col is None or q < ratios[col]:
                        col = j

            if col is None:
                self.snapshot(
                    leaving=leaving, ratios=ratios, ratio_axis="col",
                    note=f"Sale {leaving} (RHS {fmt(most_neg)}) pero su renglón no tiene "
                         "elementos negativos: infactible.",
                )
                raise InfeasibleError(
                    f"Problema infactible: la fila de {leaving} tiene lado derecho negativo "
                    "y ningún coeficiente negativo, por lo que no existe solución factible.",
                    self.tableaux,
                )

            entering = self.headers[col]
            self.snapshot(
                pivot=(row, col), entering=entering, leaving=leaving,
                ratios=ratios, ratio_axis="col",
                note=f"Sale {leaving} (RHS más negativo: {fmt(most_neg)}); "
                     f"entra {entering} (cociente mínimo {fmt(ratios[col])}).",
            )
            self.pivot(row, col)

    # ---- Resultado --------------------------------------------------------
    def build_result(self, method: str) -> SimplexResult:
        basic: Dict[str, Fraction] = {}
        values = [Fraction(0)] * self.N
        for i, j in enumerate(self.basis_idx):
            values[j] = self.T[i][-1]
            basic[self.headers[j]] = self.T[i][-1]
        basis_set = set(self.basis_idx)
        alt = any(self.z[j] == 0 for j in range(self.N) if j not in basis_set)
        return SimplexResult(
            status="optimal",
            method=method,
            tableaux=self.tableaux,
            x=values[: self.n],
            objective=self.objective_value(),
            basic_variables=basic,
            alternative_optima=alt,
            iterations=len(self.tableaux) - 1,
        )


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------
def solve(problem: Problem, method: str = "primal") -> SimplexResult:
    """Resuelve `problem` con 'primal' o 'dual'.

    Lanza UnboundedError, InfeasibleError, InvalidProblemError o
    IterationLimitError (todas heredan de SimplexError y traen `.tableaux`).
    """
    method = method.strip().lower()
    engine = _Engine(problem)
    if method == "primal":
        engine.run_primal()
    elif method == "dual":
        engine.run_dual()
    else:
        raise InvalidProblemError("El método debe ser 'primal' o 'dual'.")
    return engine.build_result(method)


def print_tableau(t: Tableau) -> None:
    """Impresión en consola (útil para depurar sin GUI)."""
    w = 8
    print(f"\n--- Iteración {t.iteration} ---  {t.note}")
    print("Base".ljust(w) + "".join(h.rjust(w) for h in t.headers))
    for name, row in zip(t.basis, t.rows):
        print(name.ljust(w) + "".join(fmt(v).rjust(w) for v in row))
    print("Z".ljust(w) + "".join(fmt(v).rjust(w) for v in t.z_row))


if __name__ == "__main__":
    demo = Problem("max", [3, 5], [[1, 0], [0, 2], [3, 2]], [4, 12, 18])
    res = solve(demo, "primal")
    for tb in res.tableaux:
        print_tableau(tb)
    print("\n" + res.summary())
