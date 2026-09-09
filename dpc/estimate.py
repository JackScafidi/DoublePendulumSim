"""Reconstructing what the hardware does not measure.

The encoders give angles; a controller needs angular rates. Differencing is the
crudest way to get them and it amplifies quantisation noise, so the difference
is low-passed. This is deliberately the simplest thing that works -- it is the
seat an observer takes later, once there is a plant worth observing.

Lives on the controller's side of the wire, because on the target it runs on
the MCU alongside the control law.
"""

import math


class RateEstimator:
    """Backward difference of each angle with a first-order low-pass.

    The two channels are independent; nothing here couples them, and nothing
    here knows about the plant. Fixed-size scalar state and no allocation, for
    transcription to C++.
    """

    __slots__ = ("tau", "_th1", "_th2", "_w1", "_w2", "_primed")

    def __init__(self, tau: float = 0.0):
        self.tau = tau
        """s. Filter time constant. Zero gives a raw difference."""
        self.reset()

    def reset(self) -> None:
        """Forget everything. The next update primes the difference and reports
        zero rates rather than inventing one from a single sample."""
        self._th1 = 0.0
        self._th2 = 0.0
        self._w1 = 0.0
        self._w2 = 0.0
        self._primed = False

    def update(self, th1: float, th2: float, dt: float) -> tuple[float, float]:
        """One tick. Returns (w1, w2) in rad/s."""
        if not self._primed:
            self._th1 = th1
            self._th2 = th2
            self._primed = True
            return 0.0, 0.0

        raw1 = (th1 - self._th1) / dt
        raw2 = (th2 - self._th2) / dt
        self._th1 = th1
        self._th2 = th2

        if self.tau > 0.0:
            # Exact zero-order-hold response, matching the lag in motor.py so
            # the two filters in the loop are discretised the same way.
            alpha = 1.0 - math.exp(-dt / self.tau)
            self._w1 = self._w1 + alpha * (raw1 - self._w1)
            self._w2 = self._w2 + alpha * (raw2 - self._w2)
        else:
            self._w1 = raw1
            self._w2 = raw2

        return self._w1, self._w2
