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
class Params:
    """The complete parameter set: nominals, their corrections, and the
    quantities that are fitted directly."""

    nominal: Nominal = field(default_factory=Nominal)
    corr: Corrections = field(default_factory=Corrections)
    fric: Friction = field(default_factory=Friction)

    phi: float = 0.0
    """rad. Rail tilt from horizontal."""

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
        """Effective values in EFFECTIVE_NAMES order, for lambdified functions."""
        eff = self.effective()
        return tuple(eff[name] for name in EFFECTIVE_NAMES)
