"""Volatility surface scaffolding (M1.5).

Equity and FX implied-vol grids over expiry × moneyness (K/S). RiskForge-owned
types only — QuantLib Black surfaces may be built later behind pricing adapters
from ``to_dict()`` / ``vol()``; QL types never leave this module.

Conventions
-----------
- Vols: absolute decimals (0.20 = 20%).
- Parallel / expiry-bucket shocks: absolute vol shifts (0.01 = +1 vol point).
- Snapshot typed vol bumps: relative vol-level changes (0.25 = +25%).
- Skew shock: ``Δσ = amount * (moneyness - 1.0)`` (ATM unchanged).
- Term-structure shock: ``Δσ = amount * expiry_years``.
- Floor: vols clamped to ``MIN_VOL`` after shocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

AssetClass = Literal["equity", "fx"]

DEFAULT_EXPIRIES: tuple[str, ...] = ("1M", "3M", "6M", "1Y", "2Y")
EXPIRY_YEARS: dict[str, float] = {
    "1M": 1.0 / 12.0,
    "3M": 0.25,
    "6M": 0.5,
    "1Y": 1.0,
    "2Y": 2.0,
}
DEFAULT_MONEYNESS: tuple[float, ...] = (0.8, 0.9, 1.0, 1.1, 1.2)

MIN_VOL = 1e-6
GridKey = tuple[str, float]  # (expiry_label, moneyness)


@dataclass(frozen=True, slots=True)
class VolPoint:
    expiry: str
    expiry_years: float
    moneyness: float
    vol: float


@dataclass(frozen=True, slots=True)
class VolSurface:
    """Immutable expiry × moneyness implied-vol surface."""

    name: str
    asset_class: AssetClass
    points: tuple[VolPoint, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("surface requires at least one point")

    @property
    def underlying(self) -> str:
        return self.name

    @property
    def pair(self) -> str:
        return self.name

    @classmethod
    def from_grid(
        cls,
        name: str,
        asset_class: AssetClass,
        grid: Mapping[GridKey, float],
    ) -> VolSurface:
        points: list[VolPoint] = []
        for (expiry, m), vol in sorted(grid.items(), key=lambda kv: (EXPIRY_YEARS.get(kv[0][0], 0.0), kv[0][1])):
            if expiry not in EXPIRY_YEARS:
                raise KeyError(f"unknown expiry label: {expiry}")
            points.append(
                VolPoint(
                    expiry=expiry,
                    expiry_years=EXPIRY_YEARS[expiry],
                    moneyness=float(m),
                    vol=max(MIN_VOL, float(vol)),
                )
            )
        return cls(name=name, asset_class=asset_class, points=tuple(points))

    def _grid_map(self) -> dict[GridKey, float]:
        return {(p.expiry, p.moneyness): p.vol for p in self.points}

    def atm_vol(self, expiry: str = "1Y") -> float:
        """ATM (moneyness=1) vol at a labeled expiry; falls back to mean surface vol."""
        for p in self.points:
            if p.expiry == expiry and abs(p.moneyness - 1.0) < 1e-12:
                return p.vol
        return float(sum(p.vol for p in self.points) / len(self.points))

    def vol(self, expiry_years: float, moneyness: float) -> float:
        """Bilinear interpolation in (expiry_years, moneyness); flat outside the grid."""
        expiries = sorted({p.expiry_years for p in self.points})
        moneynesses = sorted({p.moneyness for p in self.points})
        if not expiries or not moneynesses:
            raise ValueError("empty surface")

        t = min(max(expiry_years, expiries[0]), expiries[-1])
        m = min(max(moneyness, moneynesses[0]), moneynesses[-1])

        t0, t1 = _bracket(expiries, t)
        m0, m1 = _bracket(moneynesses, m)

        # Map year → a representative expiry label present on the surface.
        label_by_t = {}
        for p in self.points:
            label_by_t.setdefault(p.expiry_years, p.expiry)

        def node(ty: float, my: float) -> float:
            # Prefer exact grid node; otherwise average points at that year/moneyness.
            lab = label_by_t[ty]
            exact = self._grid_map().get((lab, my))
            if exact is not None:
                return exact
            # Match moneyness with tolerance.
            for p in self.points:
                if abs(p.expiry_years - ty) < 1e-12 and abs(p.moneyness - my) < 1e-12:
                    return p.vol
            raise KeyError(f"missing grid node t={ty} m={my}")

        v00 = node(t0, m0)
        v01 = node(t0, m1)
        v10 = node(t1, m0)
        v11 = node(t1, m1)
        if t1 == t0:
            wt = 0.0
        else:
            wt = (t - t0) / (t1 - t0)
        if m1 == m0:
            wm = 0.0
        else:
            wm = (m - m0) / (m1 - m0)
        v0 = v00 + wm * (v01 - v00)
        v1 = v10 + wm * (v11 - v10)
        return float(v0 + wt * (v1 - v0))

    def parallel_shift(self, dvol: float) -> VolSurface:
        return self._map_vols(lambda p: p.vol + dvol)

    def relative_shift(self, amount: float) -> VolSurface:
        """Scale every node by ``1 + amount`` for typed MarketSnapshot vol bumps."""
        return self._map_vols(lambda p: p.vol * (1.0 + amount))

    def expiry_bucket_shift(self, expiry: str, dvol: float) -> VolSurface:
        if expiry not in EXPIRY_YEARS:
            raise KeyError(f"unknown expiry label: {expiry}")
        return self._map_vols(lambda p: p.vol + dvol if p.expiry == expiry else p.vol)

    def expiry_bucket_relative_shift(self, expiry: str, amount: float) -> VolSurface:
        if expiry not in EXPIRY_YEARS:
            raise KeyError(f"unknown expiry label: {expiry}")
        return self._map_vols(lambda p: p.vol * (1.0 + amount) if p.expiry == expiry else p.vol)

    def skew_shock(self, amount: float) -> VolSurface:
        """Tilt smile: ``Δσ = amount * (moneyness - 1)``."""
        return self._map_vols(lambda p: p.vol + amount * (p.moneyness - 1.0))

    def term_structure_shock(self, amount: float) -> VolSurface:
        """Tilt term structure: ``Δσ = amount * expiry_years``."""
        return self._map_vols(lambda p: p.vol + amount * p.expiry_years)

    def _map_vols(self, fn) -> VolSurface:
        points = tuple(
            VolPoint(
                expiry=p.expiry,
                expiry_years=p.expiry_years,
                moneyness=p.moneyness,
                vol=max(MIN_VOL, float(fn(p))),
            )
            for p in self.points
        )
        return VolSurface(name=self.name, asset_class=self.asset_class, points=points)

    def to_dict(self) -> dict:
        grid = {
            f"{p.expiry}|{p.moneyness:g}": p.vol for p in self.points
        }
        return {
            "name": self.name,
            "asset_class": self.asset_class,
            "atm_vol": self.atm_vol(),
            "grid": grid,
            "expiries": list(DEFAULT_EXPIRIES),
            "moneyness": list(DEFAULT_MONEYNESS),
        }

def flat_vol_grid(
    vol: float,
    expiries: Sequence[str] = DEFAULT_EXPIRIES,
    moneyness: Sequence[float] = DEFAULT_MONEYNESS,
) -> dict[GridKey, float]:
    return {(e, float(m)): float(vol) for e in expiries for m in moneyness}


def build_equity_vol_surface(underlying: str, vol: float) -> VolSurface:
    """Equity implied-vol surface (flat scaffolding)."""
    return VolSurface.from_grid(underlying, "equity", flat_vol_grid(vol))


def build_fx_vol_surface(pair: str, vol: float) -> VolSurface:
    """FX implied-vol surface (flat scaffolding)."""
    return VolSurface.from_grid(pair, "fx", flat_vol_grid(vol))


def vol_surface_from_dict(payload: Mapping, *, default_name: str) -> VolSurface:
    """Rebuild a RiskForge surface from a snapshot ``vol_surfaces`` payload."""
    raw_grid = payload.get("grid") or {}
    grid: dict[GridKey, float] = {}
    for key, vol in raw_grid.items():
        expiry_s, m_s = str(key).split("|", 1)
        grid[(expiry_s, float(m_s))] = float(vol)
    return VolSurface.from_grid(
        str(payload.get("name") or default_name),
        payload["asset_class"],
        grid,
    )


# Public aliases for callers / type hints (same concrete type).
EquityVolSurface = VolSurface
FxVolSurface = VolSurface


def attach_vol_surface(snapshot, surface: VolSurface):
    """Attach a surface payload onto ``MarketSnapshot.vol_surfaces`` (copy-on-write).

    Also refreshes the scalar ATM mark in ``equity_vols`` / ``fx_vols`` for
    pricing paths that still read flat vols.
    """
    from app.domain.models import _deep_unfreeze

    surfaces = _deep_unfreeze(getattr(snapshot, "vol_surfaces", {}))
    surfaces[surface.name] = surface.to_dict()
    update: dict = {
        "id": f"{snapshot.id}:vol_surface:{surface.name}",
        "vol_surfaces": surfaces,
    }
    atm = surface.atm_vol()
    if surface.asset_class == "equity":
        eq = dict(snapshot.equity_vols)
        eq[surface.name] = atm
        update["equity_vols"] = eq
    else:
        fx = dict(snapshot.fx_vols)
        fx[surface.name] = atm
        update["fx_vols"] = fx
    return snapshot.model_copy(update=update)


def _bracket(sorted_vals: Sequence[float], x: float) -> tuple[float, float]:
    if x <= sorted_vals[0]:
        return sorted_vals[0], sorted_vals[0]
    if x >= sorted_vals[-1]:
        return sorted_vals[-1], sorted_vals[-1]
    for a, b in zip(sorted_vals, sorted_vals[1:]):
        if a <= x <= b:
            return a, b
    return sorted_vals[-1], sorted_vals[-1]


__all__ = [
    "DEFAULT_EXPIRIES",
    "DEFAULT_MONEYNESS",
    "EXPIRY_YEARS",
    "MIN_VOL",
    "VolPoint",
    "VolSurface",
    "EquityVolSurface",
    "FxVolSurface",
    "flat_vol_grid",
    "build_equity_vol_surface",
    "build_fx_vol_surface",
    "vol_surface_from_dict",
    "attach_vol_surface",
]
