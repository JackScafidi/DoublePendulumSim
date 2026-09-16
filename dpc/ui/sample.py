"""The vocabulary the dashboard speaks, whatever is producing the data.

Nothing here knows about Qt, and nothing here knows whether a solver or a serial
port produced the numbers. That is the point: the same struct, the same buffer
and the same plots serve simulation today and hardware later.
"""

from dataclasses import dataclass

import numpy as np

_CHANNELS = ("t", "th1", "th2", "x_count", "a_cmd", "a_del", "F_req", "tau")


@dataclass(frozen=True)
class Sample:
    """One control tick, from wherever."""

    t: float
    """s since the run started."""

    th1: float
    th2: float
    """rad. What the encoders reported."""

    x_count: float
    """m. Position implied by the step counter -- not a measurement."""

    a_cmd: float
    """m/s^2 the controller asked for."""

    a_del: float
    """m/s^2 the motor delivered."""

    F_req: float
    """N the plant required."""

    tau: float
    """N m at the motor shaft."""

    mode: str
    """Which law was active."""

    slipped: bool
    """Whether the torque budget was exceeded on this tick."""

    pinned: bool
    """Whether the step counter was held against an end stop on this tick."""

    truth: np.ndarray | None = None
    """(6,) true state, or None.

    On hardware this does not exist -- there is no sensor for it. Keeping it
    explicitly None rather than absent means the traces that use it simply stop
    drawing when the real cart is connected, with no branching anywhere."""


@dataclass(frozen=True)
class Command:
    """The upward path: what the dashboard sends to whatever produces data.

    SimSource applies these to the next tick. A SerialSource would frame them up
    the wire. Building the path now costs nothing and cannot be retrofitted
    without rewriting the source layer.
    """

    kind: str
    """"start" | "stop" | "reset" | "set_param"."""

    name: str = ""
    """Dotted target for set_param: "drive.a_max" or "controller.a"."""

    value: float = 0.0


class SampleBuffer:
    """Append-and-window storage for a run.

    Growable rather than fixed, because a hardware session has no known length.
    Simulation is then the special case that fills it quickly, and the same
    scrub bar works over both.
    """

    __slots__ = ("_n", "_cap", "_cols", "_truth", "_mode", "_slipped",
                 "_pinned")

    def __init__(self, capacity: int = 4096):
        self._n = 0
        self._cap = max(1, capacity)
        self._cols = {name: np.empty(self._cap) for name in _CHANNELS}
        self._truth = np.full((self._cap, 6), np.nan)
        self._slipped = np.zeros(self._cap, dtype=bool)
        self._pinned = np.zeros(self._cap, dtype=bool)
        self._mode: list[str] = []

    def __len__(self) -> int:
        return self._n

    @property
    def t_head(self) -> float:
        """Time of the most recent sample; 0.0 when empty."""
        return float(self._cols["t"][self._n - 1]) if self._n else 0.0

    def _grow(self) -> None:
        self._cap *= 2
        for name, arr in self._cols.items():
            self._cols[name] = np.resize(arr, self._cap)
        truth = np.full((self._cap, 6), np.nan)
        truth[:self._n] = self._truth[:self._n]
        self._truth = truth
        self._slipped = np.resize(self._slipped, self._cap)
        self._pinned = np.resize(self._pinned, self._cap)

    def append(self, s: Sample) -> None:
        if self._n == self._cap:
            self._grow()
        i = self._n
        for name in _CHANNELS:
            self._cols[name][i] = getattr(s, name)
        self._slipped[i] = s.slipped
        self._pinned[i] = s.pinned
        self._truth[i] = np.nan if s.truth is None else s.truth
        self._mode.append(s.mode)
        self._n = i + 1

    def clear(self) -> None:
        self._n = 0
        self._mode.clear()
        self._truth[:] = np.nan

    def window(self, t0: float, t1: float) -> dict[str, np.ndarray]:
        """Every channel over [t0, t1], as views a plot can draw directly."""
        t = self._cols["t"][:self._n]
        lo = int(np.searchsorted(t, t0, side="left"))
        hi = int(np.searchsorted(t, t1, side="right"))
        out = {name: self._cols[name][lo:hi] for name in _CHANNELS}
        out["slipped"] = self._slipped[lo:hi]
        out["pinned"] = self._pinned[lo:hi]
        out["truth"] = self._truth[lo:hi]
        return out

    def at(self, t: float) -> Sample | None:
        """The sample in force at time t -- the most recent one at or before it.

        Deliberately not interpolated: the animation should show states the
        simulator actually produced.
        """
        if self._n == 0:
            return None
        i = int(np.searchsorted(self._cols["t"][:self._n], t, side="right")) - 1
        if i < 0:
            return None
        truth = self._truth[i]
        return Sample(
            **{name: float(self._cols[name][i]) for name in _CHANNELS},
            mode=self._mode[i],
            slipped=bool(self._slipped[i]),
            pinned=bool(self._pinned[i]),
            truth=None if np.isnan(truth[0]) else truth.copy(),
        )
