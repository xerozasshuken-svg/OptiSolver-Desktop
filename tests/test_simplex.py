"""Pruebas del motor Simplex. Ejecutar con:  python -m pytest  (o  python tests/test_simplex.py)"""
import os
import random
import sys
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simplex import (InfeasibleError, InvalidProblemError, Problem,  # noqa: E402
                     UnboundedError, solve)


def test_primal_clasico():
    p = Problem("max", [3, 5], [[1, 0], [0, 2], [3, 2]], [4, 12, 18])
    r = solve(p, "primal")
    assert r.x == [2, 6] and r.objective == 36
    assert len(r.tableaux) == 3  # inicial + 1 pivoteo + final -> 2 iteraciones
    assert r.iterations == 2


def test_dual_minimizar_con_mayor_igual():
    p = Problem("min", [2, 3], [[1, 1], [1, 3]], [4, 6], [">=", ">="])
    r = solve(p, "dual")
    assert r.x == [3, 1] and r.objective == 9


def test_dual_con_fracciones_exactas():
    p = Problem("min", [1, 1], [[3, 1], [1, 2]], [4, 3], [">=", ">="])
    r = solve(p, "dual")
    assert r.x == [Fraction(1), Fraction(1)] and r.objective == 2


def test_no_acotado():
    p = Problem("max", [1, 1], [[1, -1]], [1])
    try:
        solve(p, "primal")
    except UnboundedError as e:
        assert e.tableaux  # trae las tablas previas
    else:
        raise AssertionError("Debió lanzar UnboundedError")


def test_infactible_dual():
    p = Problem("min", [1], [[1], [1]], [5, 2], [">=", "<="])
    try:
        solve(p, "dual")
    except InfeasibleError as e:
        assert e.tableaux
    else:
        raise AssertionError("Debió lanzar InfeasibleError")


def test_primal_rechaza_rhs_negativo():
    p = Problem("min", [2, 3], [[1, 1]], [4], [">="])
    try:
        solve(p, "primal")
    except InvalidProblemError:
        pass
    else:
        raise AssertionError("Debió lanzar InvalidProblemError")


def test_dual_rechaza_z_no_superoptimo():
    p = Problem("max", [3, 5], [[1, 0]], [4])
    try:
        solve(p, "dual")
    except InvalidProblemError:
        pass
    else:
        raise AssertionError("Debió lanzar InvalidProblemError")


def test_entrada_texto():
    p = Problem("max", ["3", "5"], [["1", "0"], ["0", "2"], ["3", "2"]], ["4", "12", "18"])
    assert solve(p).objective == 36


def test_contra_scipy():
    try:
        from scipy.optimize import linprog
    except ImportError:
        print("scipy no instalado: prueba omitida")
        return
    rng = random.Random(7)
    ok = 0
    for _ in range(200):
        n, m = rng.randint(2, 4), rng.randint(2, 4)
        c = [rng.randint(1, 9) for _ in range(n)]
        A = [[rng.randint(1, 9) for _ in range(n)] for _ in range(m)]
        b = [rng.randint(5, 40) for _ in range(m)]
        # max c x, Ax <= b, x >= 0  (siempre acotado y factible)
        mine = solve(Problem("max", c, A, b), "primal")
        ref = linprog([-v for v in c], A_ub=A, b_ub=b, bounds=(0, None))
        assert abs(float(mine.objective) + ref.fun) < 1e-7
        # min c x, Ax >= b  (dual)
        mine = solve(Problem("min", c, A, b, [">="] * m), "dual")
        ref = linprog(c, A_ub=[[-a for a in row] for row in A], b_ub=[-v for v in b], bounds=(0, None))
        assert abs(float(mine.objective) - ref.fun) < 1e-7
        ok += 1
    print(f"{ok} problemas aleatorios coinciden con SciPy")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK ", name)
