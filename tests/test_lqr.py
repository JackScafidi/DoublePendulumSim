import numpy as np

from dpc.controllers.registry import build as build_controller
from dpc.controllers.registry import discover
from dpc.linearize import linearize_accel
from dpc.model import ModelConfig, build
from dpc.params import Params

M = build(ModelConfig())
P = Params()
UP = np.zeros(6)

GAIN_NAMES = ("k_x", "k_th1", "k_th2", "k_dx", "k_w1", "k_w2")
"""Canonical state order: [x, th1, th2, xdot, w1, w2]."""


def _shipped_K() -> np.ndarray:
    """The gains the controller actually ships, read from its PARAMS defaults
    rather than copied here -- a second copy of the constants would agree with
    itself forever."""
    entry = {e.key: e for e in discover()}["lqr"]
    c = build_controller(entry, {})
    return np.array([getattr(c, n) for n in GAIN_NAMES])


def test_shipped_gains_stabilise_the_current_plant():
    """The point of this test is the plant moving, not the gains moving.

    K is designed offline against one set of masses, lengths and drive limits
    and then pasted in as constants. Change a mass in params.py and the
    controller keeps running, keeps looking plausible, and is quietly designed
    for a machine that no longer exists. Nothing else in the suite notices.

    Deliberately not a comparison against a freshly solved K: re-tuning the
    weights is a legitimate thing to do, and a test that has to be edited to
    agree with the code every time is not testing anything. Any K that holds
    this plant passes.
    """
    A, B = linearize_accel(M, UP, 0.0, P)
    ev = np.linalg.eigvals(A - B @ _shipped_K().reshape(1, 6))
    assert np.max(np.real(ev)) < 0.0


def test_gain_names_match_the_state_order():
    """PARAMS is read positionally above, so its order is load-bearing."""
    entry = {e.key: e for e in discover()}["lqr"]
    assert tuple(p.name for p in entry.params)[:6] == GAIN_NAMES
