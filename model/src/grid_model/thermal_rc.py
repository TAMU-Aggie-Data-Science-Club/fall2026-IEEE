import math


def temperature(t: float, ambient: float, power: float, dt: float,
                resistance: float = 3.2, tau: float = 300.0) -> float:
    """Exact first-order RC step for constant forcing (demo parameters only)."""
    if dt < 0 or tau <= 0 or resistance < 0:
        raise ValueError("invalid RC parameters")
    equilibrium = ambient + resistance * max(power, 0)
    return equilibrium + (t - equilibrium) * math.exp(-dt / tau)


def eta(t, ambient, power, resistance=3.2, tau=300., threshold=80., horizon=600.):
    equilibrium = ambient + resistance * max(power, 0)
    if t >= threshold:
        return 0.0
    if equilibrium <= threshold:
        return None
    seconds = -tau * math.log((threshold - equilibrium) / (t - equilibrium))
    return seconds if 0 <= seconds <= horizon else None
