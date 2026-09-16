"""Every physical constant in the project. Nothing numeric lives outside this file.

Each uncertain quantity is a real-world *nominal* multiplied by a dimensionless
*correction factor* that starts at 1.0. Nominals are owned by the engineer and
come from CAD, a datasheet, or a scale. Corrections are owned by the parameter
fitter, and are the only thing it is allowed to move.

The split exists so that the fitter sees well-scaled, dimensionless unknowns
near one, so a prior reads the same for every parameter regardless of units,
and so a correction that comes back far from one is legible as a warning rather
than a result.
"""

import math
from dataclasses import dataclass, field

# Canonical ordering, shared with model.py so lambdified functions can take a
# plain tuple of floats. Do not reorder.
EFFECTIVE_NAMES: tuple[str, ...] = (
    "m_cart", "m_rotor", "m1", "m2",
    "l1", "l2", "lc1", "lc2",
    "I1", "I2", "g",
    "b_cart", "b1", "b2",
    "c_cart", "c1", "c2",
    "eps_fric", "phi",
)


@dataclass(frozen=True)
class Nominal:
    """Best real-world estimates, in SI units."""

    m_cart: float = 0.30
    """kg. Carriage, bracket and belt clamp. Real, weighable mass."""

    m_rotor: float = 1.33
    """kg. EQUIVALENT mass J/r^2 of the motor rotor seen through a 20T GT2
    pulley -- NOT the rotor's weighable mass, which is about 0.28 kg.

    The belt ties rotor angle to cart position by x = r*theta_m, so the rotor's
    kinetic energy (1/2) J theta_m_dot^2 becomes (1/2) (J/r^2) xdot^2, which is
    indistinguishable from translating mass. With r = 6.4 mm the division by
    r^2 multiplies rotor inertia by roughly 25,000.

    It has inertia but no weight. It must never appear in the potential energy
    or in a normal-force term.
    """

    m1: float = 0.075
    """kg. Link 1 rod plus the elbow encoder body."""

    m2: float = 0.045
    """kg. Link 2 rod."""

    l1: float = 0.20
    """m. Measured with calipers, so it carries no correction factor."""

    l2: float = 0.20
    """m. Measured with calipers, so it carries no correction factor."""

    lc1: float = 0.12
    """m. Centre of mass of link 1 from the cart joint, biased outward from
    midspan by the elbow encoder."""

    lc2: float = 0.10
    """m. Centre of mass of link 2 from the elbow."""

    I1: float = 3.0e-4
    """kg m^2, about link 1's own centre of mass."""

    I2: float = 1.5e-4
    """kg m^2, about link 2's own centre of mass."""

    g: float = 9.81
    """m/s^2. Known, so it carries no correction factor."""

    rail_len: float = 0.50
    """m. Total cart travel between the end stops, measured, so no
    correction factor. A constraint on the state, not a term in the
    equations of motion: it must never enter EFFECTIVE_NAMES or
    effective()."""

    cart_len: float = 0.09
    """m. Length of the carriage along the rail, from the CAD. The plant
    treats the cart as a point mass, so this is a drawing dimension and
    nothing else -- it exists so the animation can size the cart in metres
    like every other object on the canvas instead of at a fixed pixel width
    that means something different at every scale. Like rail_len, it must
    never enter EFFECTIVE_NAMES or effective()."""


@dataclass(frozen=True)
class Corrections:
    """Dimensionless multipliers the fitter is allowed to move. All start at 1.0.

    Lengths and gravity are absent on purpose. Lengths are measurable to a
    fraction of a percent, and leaving them free would let the fitter trade
    length against mass to explain the same data. A correction on gravity would
    become a sponge absorbing scale errors from everywhere else, which would
    render the rest of the fit meaningless.
    """

    k_m_cart: float = 1.0
    k_m_rotor: float = 1.0
    k_m1: float = 1.0
    k_m2: float = 1.0
    k_lc1: float = 1.0
    k_lc2: float = 1.0
    k_I1: float = 1.0
    k_I2: float = 1.0


@dataclass(frozen=True)
class Friction:
    """Fitted as absolute values rather than multipliers: the nominal is zero,
    and zero times any correction stays zero forever."""

    b_cart: float = 0.0
    """N s/m. Viscous along the rail."""

    b1: float = 0.0
    """N m s. Viscous at the cart joint."""

    b2: float = 0.0
    """N m s. Viscous at the elbow."""

    c_cart: float = 0.0
    """N. Coulomb along the rail."""

    c1: float = 0.0
    """N m. Coulomb at the cart joint."""

    c2: float = 0.0
    """N m. Coulomb at the elbow."""

    eps_fric: float = 1e-3
    """Smoothing width. Coulomb friction is applied as c*tanh(v/eps) so the
    model stays differentiable, which linearisation and gradient-based fitting
    both require."""


@dataclass(frozen=True)
class Drive:
    """The stepper drive train. Provisional until the hardware is finalised.

    None of these appear in the equations of motion, so they are deliberately
    absent from EFFECTIVE_NAMES: they shape the command the motor accepts, not
    the physics of the plant.
    """

    r_pulley: float = 6.4e-3
    """m. 20T GT2 pitch radius. The same r that makes m_rotor = J/r^2."""

    steps_per_rev: int = 200
    """NEMA-17 at 1.8 degrees per full step."""

    microsteps: int = 16
    """TMC2209 microstepping divisor."""

    tau_hold: float = 0.40
    """N m. Holding torque of a typical 42x40 mm NEMA-17."""

    tau_derate: float = 0.5
    """Dimensionless. Available torque falls off with step rate; this is the
    fraction of holding torque treated as usable."""

    a_max: float = 10.0
    """m/s^2. Acceleration ceiling set by torque through the pulley."""

    v_max: float = 0.5
    """m/s. Step rate beyond this is unsustainable."""

    jerk_max: float = 200.0
    """m/s^3. How fast the step generator can ramp its own rate."""

    tau_lag: float = 3e-3
    """s. First-order stand-in for the step generator's finite bandwidth."""

    slip_enable: bool = False
    """Step loss is implemented but off by default. It is the only mechanism
    that makes the step-counted position differ from the truth, so enabling it
    is a deliberate question, not a default."""

    @property
    def step_res(self) -> float:
        """m of belt travel per microstep."""
        return 2.0 * math.pi * self.r_pulley / (self.steps_per_rev * self.microsteps)

    @property
    def tau_budget(self) -> float:
        """N m the motor can actually be relied on to deliver."""
        return self.tau_hold * self.tau_derate

    @property
    def F_max(self) -> float:
        """N at the belt corresponding to the torque budget."""
        return self.tau_budget / self.r_pulley


@dataclass(frozen=True)
class Control:
    """Loop timing. Not physical, but numeric, so it lives here like everything
    else numeric."""

    ts: float = 1e-3
    """s. Control period. One measurement, one command, one motor update."""

    substeps: int = 10
    """Plant integration steps per control tick. Exists only so integration
    error stays well below the effects under study."""

    tau_rate: float = 5e-3
    """s. Low-pass time constant on differenced angular rates."""


@dataclass(frozen=True)
class Params:
    """The complete parameter set: nominals, their corrections, and the
    quantities that are fitted directly."""

    nominal: Nominal = field(default_factory=Nominal)
    corr: Corrections = field(default_factory=Corrections)
    fric: Friction = field(default_factory=Friction)
    drive: Drive = field(default_factory=Drive)
    ctrl: Control = field(default_factory=Control)

    phi: float = 0.0
    """rad. Rail tilt from horizontal."""

    @property
    def x_lim(self) -> float:
        """m. How far the cart can travel either side of centre."""
        return self.nominal.rail_len / 2.0

    def effective(self) -> dict[str, float]:
        """Nominal times correction, plus the directly-fitted quantities."""
        n, c, f = self.nominal, self.corr, self.fric
        return {
            "m_cart": n.m_cart * c.k_m_cart,
            "m_rotor": n.m_rotor * c.k_m_rotor,
            "m1": n.m1 * c.k_m1,
            "m2": n.m2 * c.k_m2,
            "l1": n.l1,
            "l2": n.l2,
            "lc1": n.lc1 * c.k_lc1,
            "lc2": n.lc2 * c.k_lc2,
            "I1": n.I1 * c.k_I1,
            "I2": n.I2 * c.k_I2,
            "g": n.g,
            "b_cart": f.b_cart,
            "b1": f.b1,
            "b2": f.b2,
            "c_cart": f.c_cart,
            "c1": f.c1,
            "c2": f.c2,
            "eps_fric": f.eps_fric,
            "phi": self.phi,
        }

    def vector(self) -> tuple[float, ...]:
        """Effective values in EFFECTIVE_NAMES order, for lambdified functions.

        Memoised on the instance. Every lambdified call -- M, Cqd, G, Ffric --
        asks for this, so it is rebuilt four times per solve and forty times per
        control tick at substeps=10. Assembling the dict costs 1.7 us, about 29%
        of what a solve costs in total.

        Params is frozen, so object.__setattr__ is the way in. The cache lives in
        __dict__ rather than in a declared field, which leaves the
        dataclass-generated __eq__ and __hash__ untouched -- both read the
        declared fields only.
        """
        cached = self.__dict__.get("_vector_cache")
        if cached is None:
            eff = self.effective()
            cached = tuple(eff[name] for name in EFFECTIVE_NAMES)
            object.__setattr__(self, "_vector_cache", cached)
        return cached
