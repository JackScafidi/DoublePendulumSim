import numpy as np
import pytest

from dpc.estimate import RateEstimator

DT = 1e-3


def test_first_call_reports_zero_rates():
    """One sample cannot imply a rate. Reporting a huge one from the initial
    zero would kick any controller on its first tick."""
    e = RateEstimator(tau=0.0)
    assert e.update(1.0, 2.0, DT) == (0.0, 0.0)


def test_unfiltered_estimator_is_an_exact_backward_difference():
    e = RateEstimator(tau=0.0)
    e.update(0.0, 0.0, DT)
    w1, w2 = e.update(0.003, -0.005, DT)
    assert w1 == pytest.approx(3.0)
    assert w2 == pytest.approx(-5.0)


def test_it_converges_to_the_true_rate_of_a_ramp():
    e = RateEstimator(tau=5e-3)
    th = 0.0
    for _ in range(200):
        th += 2.0 * DT
        w1, _ = e.update(th, 0.0, DT)
    assert w1 == pytest.approx(2.0, rel=1e-3)


def test_filter_lags_by_its_time_constant():
    """A first-order filter reaches 63.2% of a step in one tau. This is the
    price of differencing a noisy signal, and it is characterised here rather
    than left to be discovered on hardware."""
    tau = 10e-3
    e = RateEstimator(tau=tau)
    e.update(0.0, 0.0, DT)
    th = 0.0
    for _ in range(int(round(tau / DT))):
        th += 1.0 * DT
        w1, _ = e.update(th, 0.0, DT)
    assert w1 == pytest.approx(1.0 - np.exp(-1.0), rel=1e-6)


def test_reset_restores_the_unprimed_state():
    e = RateEstimator(tau=0.0)
    e.update(0.0, 0.0, DT)
    e.update(0.01, 0.01, DT)
    e.reset()
    assert e.update(5.0, 5.0, DT) == (0.0, 0.0)


def test_the_two_channels_are_independent():
    e = RateEstimator(tau=0.0)
    e.update(0.0, 0.0, DT)
    w1, w2 = e.update(0.001, 0.0, DT)
    assert w1 == pytest.approx(1.0)
    assert w2 == pytest.approx(0.0)
