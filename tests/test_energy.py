"""Energy conservation.

With every friction coefficient at zero and no applied force, the system is
genuinely conservative -- not approximately so. Total energy must therefore
stay flat to within the integrator's truncation error, which makes this the
sharpest single check on the derivation.

It does not localise a fault: it says something is wrong, not what. That job
belongs to test_degenerate.py.
"""

import numpy as np
import pytest

from dpc.model import ModelConfig, build
from dpc.params import Friction, Nominal, Params
from dpc.simulate import simulate

M = build(ModelConfig())

LONG_RAIL = Nominal(rail_len=1e3)
"""A rail no case here can reach the end of.

The end stops are a constraint on the state rather than a term in the equations
of motion, and hitting one is inelastic: it removes energy on purpose. Cases
that send the cart travelling -- a tilted rail, or a start with the cart
already moving -- would otherwise stop against a wall, and this file is about
the derivation, not about the wall. tests/test_rail.py owns the stops.
"""

IDEAL = Params(nominal=LONG_RAIL)
DAMPED = Params(nominal=LONG_RAIL,
                fric=Friction(b_cart=0.5, b1=0.02, b2=0.02))


def _energy_series(p, s0, dt=5e-4, t_end=6.0):
    tr = simulate(M, s0, lambda t, s: 0.0, t_end=t_end, dt=dt, p=p)
    return np.array([M.energy(s, p) for s in tr.s])


@pytest.mark.parametrize("s0", [
    np.array([0.0, 3.0, 3.1, 0.0, 0.0, 0.0]),      # released near hanging
    np.array([0.0, 0.4, -0.6, 0.0, 0.0, 0.0]),     # released near upright
    np.array([0.1, 1.2, -2.0, 0.5, 1.0, -1.5]),    # violent and chaotic
])
def test_energy_is_conserved_without_friction_or_force(s0):
    e = _energy_series(IDEAL, s0)
    drift = abs(e - e[0]).max() / max(abs(e[0]), 1e-12)
    assert drift < 1e-6, f"relative energy drift {drift:.2e}"


def test_energy_drift_shrinks_with_a_smaller_step():
    """Confirms the residual drift is truncation error rather than a modelling
    fault: a fault would not care about the step size."""
    s0 = np.array([0.1, 1.2, -2.0, 0.5, 1.0, -1.5])
    coarse = _energy_series(IDEAL, s0, dt=2e-3, t_end=3.0)
    fine = _energy_series(IDEAL, s0, dt=1e-3, t_end=3.0)
    assert abs(fine - fine[0]).max() < abs(coarse - coarse[0]).max()


def test_friction_removes_energy_monotonically():
    s0 = np.array([0.0, 2.0, 2.2, 0.0, 0.0, 0.0])
    e = _energy_series(DAMPED, s0, dt=1e-3, t_end=4.0)
    assert e[-1] < e[0]
    assert np.all(np.diff(e) < 1e-9)


def test_a_tilted_rail_still_conserves_energy():
    """Tilt changes where the energy sits, not whether it is conserved."""
    p = Params(nominal=LONG_RAIL, phi=0.26)
    e = _energy_series(p, np.array([0.0, 2.0, 2.2, 0.0, 0.0, 0.0]), t_end=3.0)
    drift = abs(e - e[0]).max() / abs(e[0])
    assert drift < 1e-6, f"relative energy drift {drift:.2e}"


def test_applied_force_changes_energy():
    """A control force does work, so energy must not be conserved under it --
    otherwise the force is not actually reaching the plant."""
    s0 = np.array([0.0, 0.1, 0.1, 0.0, 0.0, 0.0])
    tr = simulate(M, s0, lambda t, s: 1.0, t_end=0.5, dt=1e-3, p=IDEAL)
    assert M.energy(tr.s[-1], IDEAL) > M.energy(tr.s[0], IDEAL)
