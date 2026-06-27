from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Annotated, Any, Literal, NoReturn, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

# RateZero tenors that parallel-shift scalar ``rates[ccy]`` (and all pillars).
_RATE_PARALLEL_TENORS = frozenset({"ALL", "PARALLEL"})
_VOL_GENERIC_EXPIRIES = frozenset({"GENERIC", "ALL", "PARALLEL"})
_VOL_ATM_BUCKETS = frozenset({"ATM", "GENERIC", "ALL", "PARALLEL"})
_VOL_SKEW_BUCKETS = frozenset({"SKEW", "SMILE_SKEW"})
_VOL_TERM_BUCKETS = frozenset({"TERM", "TERM_STRUCTURE"})
_FX_PAIR_RE = re.compile(r"^[A-Z]{6}$")
_NON_FINITE_LABELS = frozenset({"NaN", "Infinity", "-Infinity"})


def _non_finite_label(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


def _coerce_non_finite_to_label(value: Any) -> Any:
    """Swap NaN/Inf for a JSON-safe label before the float parser runs.

    FastAPI's 422 handler serializes ``exc.errors()`` (including ``input``)
    via Starlette ``JSONResponse`` (``allow_nan=False``). Keeping the original
    float in the error payload would turn a validation failure into HTTP 500.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return _non_finite_label(value)
    return value


def _finite_number_error() -> None:
    # PydanticCustomError keeps 422 ``exc.errors()`` JSON-serializable
    # (``raise ValueError`` puts a ValueError object in ``ctx``).
    raise PydanticCustomError("finite_number", "must be a finite number")


def _reject_non_finite_label(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return value
        if not math.isfinite(parsed):
            _finite_number_error()
    return value


def _require_finite(value: float) -> float:
    """Reject NaN / ±Infinity after Pydantic coerces the field to float."""
    if not math.isfinite(value):
        _finite_number_error()
    return value


def _require_fx_pair(value: str) -> str:
    """Accept a 6-letter ISO pair (EURUSD); reject empty or punctuation shapes."""
    pair = value.strip().upper()
    if _FX_PAIR_RE.fullmatch(pair) is None:
        raise PydanticCustomError(
            "fx_pair",
            "must be a 6-letter ISO FX pair (e.g. EURUSD)",
        )
    return pair


def _replace_nested_non_finite(value: Any) -> Any:
    """Copy a tree, replacing non-finite floats with JSON-safe labels."""
    if isinstance(value, Mapping):
        return {k: _replace_nested_non_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_nested_non_finite(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_replace_nested_non_finite(v) for v in value)
    if isinstance(value, float) and not math.isfinite(value):
        return _non_finite_label(value)
    return value


def _assert_nested_floats_finite(value: Any) -> None:
    """Walk mappings/sequences and reject non-finite floats (curves / surfaces)."""
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_nested_floats_finite(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_nested_floats_finite(item)
        return
    if isinstance(value, str) and value in _NON_FINITE_LABELS:
        _finite_number_error()
    if isinstance(value, float) and not math.isfinite(value):
        _finite_number_error()


FiniteFloat = Annotated[
    float,
    BeforeValidator(_coerce_non_finite_to_label),
    BeforeValidator(_reject_non_finite_label),
    AfterValidator(_require_finite),
]
FxPair = Annotated[str, AfterValidator(_require_fx_pair)]

# Engine labels mean "use the pricing engine evaluation date". They must not be
# rewritten to date.today() on the production path.
AsOfLabel = Literal["current", "t0"]
AS_OF_ENGINE_LABELS: frozenset[str] = frozenset({"current", "t0"})
_AS_OF_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _as_of_error() -> NoReturn:
    raise PydanticCustomError(
        "as_of_date",
        "as_of must be an ISO calendar date YYYY-MM-DD or an engine label "
        "(current, t0)",
    )


def _coerce_as_of(value: Any) -> date | AsOfLabel:
    """Parse snapshot as-of. Fail closed; never default to wall-clock."""
    if isinstance(value, datetime):
        _as_of_error()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        lowered = text.lower()
        if lowered in AS_OF_ENGINE_LABELS:
            return lowered  # type: ignore[return-value]
        if _AS_OF_ISO_RE.fullmatch(text):
            try:
                return date.fromisoformat(text)
            except ValueError:
                _as_of_error()
        _as_of_error()
    _as_of_error()


AsOf = Annotated[date | AsOfLabel, BeforeValidator(_coerce_as_of)]
_AS_OF_ADAPTER: TypeAdapter[date | AsOfLabel] = TypeAdapter(AsOf)


def as_of_wire(as_of: date | AsOfLabel) -> str:
    """API/persistence string form. Dates are ISO; labels stay labels."""
    if type(as_of) is date:
        return as_of.isoformat()
    return str(as_of)


def calendar_as_of(as_of: object) -> date | None:
    """Calendar date for pricing; None means use the engine evaluation date.

    ``datetime`` is a ``date`` subclass and is not accepted. ISO ``YYYY-MM-DD``
    strings are parsed so cache/QuantLib stay aligned if validation is bypassed
    (``model_construct``). Engine labels and anything else return None.
    """
    if type(as_of) is date:
        return as_of
    if isinstance(as_of, str):
        text = as_of.strip()
        if _AS_OF_ISO_RE.fullmatch(text):
            try:
                return date.fromisoformat(text)
            except ValueError:
                return None
    return None


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze mappings/lists so nested in-place mutation fails."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(v) for v in value)
    return value


def _deep_unfreeze(value: Any) -> Any:
    """Plain dict/list tree for JSON serialization and content hashing."""
    if isinstance(value, Mapping):
        return {k: _deep_unfreeze(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_deep_unfreeze(v) for v in value]
    if isinstance(value, list):
        return [_deep_unfreeze(v) for v in value]
    return value


def _curve_matches_currency(payload: Mapping, currency: str) -> bool:
    return str(payload.get("currency", "")).upper() == currency.upper()


def _bump_curve_zeros(payload: Mapping, amount: float, tenor: str | None) -> dict:
    """Copy a curve payload, shifting zeros for one tenor or all tenors."""
    out = _deep_unfreeze(payload)
    zeros = dict(out.get("zeros") or {})
    if tenor is None:
        for t in list(zeros):
            zeros[t] = float(zeros[t]) + amount
    elif tenor in zeros:
        zeros[tenor] = float(zeros[tenor]) + amount
    out["zeros"] = zeros
    return out


def _vol_surface_matches_asset_class(payload: Mapping, asset_class: str) -> bool:
    return str(payload.get("asset_class", "")).lower() == asset_class


def _bump_vol_surface_payload(payload: Mapping, factor, amount: float) -> dict:
    """Copy and shock one vol surface payload using RiskForge surface semantics."""
    from app.market.vol_surfaces import EXPIRY_YEARS, vol_surface_from_dict

    surface = vol_surface_from_dict(payload, default_name=getattr(factor, "underlying", getattr(factor, "pair", "")))
    expiry = str(getattr(factor, "expiry", "GENERIC")).upper()
    moneyness = str(getattr(factor, "moneyness", "ATM")).upper()

    if moneyness in _VOL_SKEW_BUCKETS:
        return surface.skew_shock(amount).to_dict()
    if expiry in _VOL_TERM_BUCKETS:
        return surface.term_structure_shock(amount).to_dict()
    if expiry in EXPIRY_YEARS and moneyness in _VOL_ATM_BUCKETS:
        return surface.expiry_bucket_relative_shift(expiry, amount).to_dict()
    if expiry in _VOL_GENERIC_EXPIRIES and moneyness in _VOL_ATM_BUCKETS:
        return surface.relative_shift(amount).to_dict()
    # Preserve pre-surface behavior for future dimensions such as delta buckets:
    # older typed vol bumps ignored expiry/moneyness and applied a scalar move.
    return surface.relative_shift(amount).to_dict()


class AssetClass(str, Enum):
    EQUITY = "equity"
    RATES = "rates"
    FX = "fx"


class FiniteInputMixin(BaseModel):
    """Rewrite NaN/±Inf to JSON-safe labels before field validation.

    Pydantic records the *field* input in ``ValidationError.errors()``. FastAPI
    then serializes that list as the 422 body. Replacing non-finite floats here
    keeps those details JSON-compliant without changing ``errors.py``.
    """

    @model_validator(mode="before")
    @classmethod
    def _label_non_finite_inputs(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            return _replace_nested_non_finite(data)
        return data


class PositionHierarchyMixin(FiniteInputMixin):
    """Optional desk/strategy placement on a trade.

    ``None`` inherits :attr:`Portfolio.desk` / :attr:`Portfolio.strategy`
    (backward-compatible default). Explicit strings enable multi-desk books.
    Live market marks are forbidden on Position DTOs (``extra='forbid'``).
    """

    model_config = ConfigDict(extra="forbid")

    desk: str | None = None
    strategy: str | None = None


class EquityPosition(PositionHierarchyMixin):
    """Cash equity economics. Live spot lives on ``MarketSnapshot.equity_spots``."""

    type: Literal["equity"]
    id: str
    symbol: str
    quantity: FiniteFloat
    currency: str = "USD"
    sector: str = "Other"
    book: str = "Equity"


class EquityFuturePosition(PositionHierarchyMixin):
    """Equity index future economics. Spot / carry rates live on the snapshot."""

    type: Literal["equity_future"]
    id: str
    symbol: str
    quantity: FiniteFloat
    multiplier: FiniteFloat = 50.0
    maturity_years: FiniteFloat = Field(default=0.25, gt=0)
    currency: str = "USD"
    sector: str = "Index"
    book: str = "Equity Derivatives"


class EuropeanOptionPosition(PositionHierarchyMixin):
    """European equity option economics. Spot / vol / rates live on the snapshot."""

    type: Literal["european_option"]
    id: str
    symbol: str
    quantity: FiniteFloat
    strike: FiniteFloat
    maturity_years: FiniteFloat = Field(gt=0)
    option_type: Literal["call", "put"]
    currency: str = "USD"
    sector: str = "Other"
    book: str = "Equity Derivatives"


class BondPosition(PositionHierarchyMixin):
    """Zero-bond economics. Yield marks live on the snapshot.

    ``duration`` is contractual/schedule metadata. Reported ``Valuation.dv01``
    is a same-curve PARALLEL +1bp bump-and-revalue, not duration × PV.
    """

    type: Literal["bond"]
    id: str
    issuer: str
    face_value: FiniteFloat = Field(gt=0)
    quantity: FiniteFloat = 1.0
    maturity_years: FiniteFloat = Field(gt=0)
    duration: FiniteFloat = Field(gt=0)
    currency: str = "USD"
    book: str = "Rates"


class SwapPosition(PositionHierarchyMixin):
    """IRS economics. Market swap rate lives on the snapshot.

    ``duration`` is the annuity factor used by the builtin swap PV. Reported
    ``Valuation.dv01`` is a same-curve PARALLEL +1bp bump-and-revalue.
    """

    type: Literal["swap"]
    id: str
    currency: str = "USD"
    notional: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    fixed_rate: FiniteFloat
    pay_fixed: bool = True
    duration: FiniteFloat = Field(gt=0)
    book: str = "Rates Derivatives"


class FXForwardPosition(PositionHierarchyMixin):
    """FX forward economics. Spot and funding rates live on the snapshot."""

    type: Literal["fx_forward"]
    id: str
    pair: FxPair
    notional_base: FiniteFloat
    strike: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    book: str = "FX"


class FXOptionPosition(PositionHierarchyMixin):
    """FX option economics. Spot / vol / funding rates live on the snapshot."""

    type: Literal["fx_option"]
    id: str
    pair: FxPair
    notional_base: FiniteFloat
    strike: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    option_type: Literal["call", "put"]
    book: str = "FX Derivatives"


class InterestRateFuturePosition(PositionHierarchyMixin):
    """Exchange-traded short-rate future economics (STIR-style).

    Quoted / forward rates live on the snapshot; ``pv01`` is a contractual
    contract multiplier convention, not a live mark.
    """

    type: Literal["ir_future"]
    id: str
    currency: str = "USD"
    quantity: FiniteFloat
    # Dollar value of a 1bp move per contract (e.g. 25 for classic Eurodollar).
    pv01: FiniteFloat = Field(default=25.0, gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    book: str = "Rates Derivatives"


class CapFloorPosition(PositionHierarchyMixin):
    """Vanilla interest-rate cap/floor as a flat-forward Black-76 optionlet strip.

    Conventions are intentionally explicit for the M1.9 slice:
    rates/strike are decimals, notional is currency notional,
    ``option_type='cap'`` is a long cap and ``'floor'`` is a long floor, and
    equal accrual periods are generated from ``maturity_years`` and
    ``payment_frequency_per_year``. Live forward / discount / vol marks live
    on the snapshot. The lognormal Black model requires positive strike and
    forward rates; richer IR-vol cube/exercise schedules are deferred.
    """

    type: Literal["cap_floor"]
    id: str
    currency: str = "USD"
    notional: FiniteFloat = Field(gt=0)
    quantity: FiniteFloat = 1.0
    strike: FiniteFloat = Field(gt=0)
    maturity_years: FiniteFloat = Field(gt=0)
    option_type: Literal["cap", "floor"]
    payment_frequency_per_year: int = Field(default=2, ge=1, le=12)
    book: str = "Rates Derivatives"


class SwaptionPosition(PositionHierarchyMixin):
    """Vanilla European swaption on a flat-rate par swap representation.

    Conventions are intentionally narrow for the M1.9 slice: rates and strike
    are decimals; ``option_type='payer'`` is a call on the forward swap rate
    and ``'receiver'`` is a put; the underlying swap annuity is generated from
    equal fixed-leg periods over ``swap_tenor_years`` after
    ``option_maturity_years``. Live forward / discount / vol marks live on the
    snapshot. Explicit date schedules and IR vol cubes are deferred.
    """

    type: Literal["swaption"]
    id: str
    currency: str = "USD"
    notional: FiniteFloat = Field(gt=0)
    quantity: FiniteFloat = 1.0
    strike: FiniteFloat = Field(gt=0)
    option_maturity_years: FiniteFloat = Field(gt=0)
    swap_tenor_years: FiniteFloat = Field(gt=0)
    option_type: Literal["payer", "receiver"]
    payment_frequency_per_year: int = Field(default=2, ge=1, le=12)
    book: str = "Rates Derivatives"


Position = Annotated[
    Union[
        EquityPosition,
        EquityFuturePosition,
        EuropeanOptionPosition,
        BondPosition,
        SwapPosition,
        FXForwardPosition,
        FXOptionPosition,
        InterestRateFuturePosition,
        CapFloorPosition,
        SwaptionPosition,
    ],
    Field(discriminator="type"),
]


class Portfolio(FiniteInputMixin):
    id: str
    name: str
    positions: list[Position]
    firm: str = "RiskForge"
    desk: str = "Global Macro"
    strategy: str = "Multi-Asset"
    # Server-owned monotonic identity (R0.8.8). Create starts at 1; clients may
    # send a value on first persist but the repository overwrites it.
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [p.id for p in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError("position ids must be unique")
        return self


class MarketSnapshot(FiniteInputMixin):
    """Immutable market marks consumed by pricing and risk.

    Flat dict fields remain the storage/API shape for compatibility. Typed
    :meth:`bump` / :meth:`apply` / :meth:`diff` and sub-market views
    (:attr:`equity`, :attr:`rates_market`, :attr:`vol`, :attr:`fx`) are the
    preferred mutation/inspection APIs. Nested maps (including ``curves`` /
    ``vol_surfaces`` payloads) are recursively frozen via ``MappingProxyType``
    so in-place edits fail at every nesting level.

    ``as_of`` is a calendar ``date`` or an explicit engine label
    (``current`` / ``t0``). ISO ``YYYY-MM-DD`` strings coerce to ``date``.
    Labels mean "use the pricing-engine evaluation date" and are never
    rewritten to ``date.today()``. Unparseable values fail closed. Wire and
    persistence keep a string via :func:`as_of_wire`.

    Bump units:
    - EquitySpot / FXSpot: relative return (0.01 = +1%)
    - EquityVol / FXVol: relative vol change (0.25 = +25% of current vol level)
    - RateZero: absolute decimal rate shift (0.0001 = +1bp)
      - tenor ``PARALLEL`` or ``ALL``: parallel-shift scalar ``rates[ccy]``,
        all ``key_rates[ccy]`` pillars, and matching curve zeros
      - specific tenor (e.g. ``10Y``): bump ``key_rates[ccy][tenor]`` and
        matching curve zeros only — does **not** shift scalar ``rates[ccy]``
    """

    model_config = ConfigDict(frozen=True)

    id: str = "current"
    as_of: AsOf = "current"
    equity_spots: dict[str, FiniteFloat] = Field(default_factory=dict)
    equity_vols: dict[str, FiniteFloat] = Field(default_factory=dict)
    fx_spots: dict[str, FiniteFloat] = Field(default_factory=dict)
    fx_vols: dict[str, FiniteFloat] = Field(default_factory=dict)
    rates: dict[str, FiniteFloat] = Field(default_factory=lambda: {"USD": 0.04})
    key_rates: dict[str, dict[str, FiniteFloat]] = Field(default_factory=dict)
    dividend_yields: dict[str, FiniteFloat] = Field(default_factory=dict)
    projection_rates: dict[str, FiniteFloat] = Field(default_factory=dict)
    rate_spreads: dict[str, FiniteFloat] = Field(default_factory=dict)
    ir_vols: dict[str, FiniteFloat] = Field(default_factory=dict)
    ir_future_quotes: dict[str, FiniteFloat] = Field(default_factory=dict)
    # Named curve payloads: {name: {currency, curve_type, name, zeros}}
    curves: dict[str, dict] = Field(default_factory=dict)
    # Named vol surface payloads: {name: {asset_class, atm_vol, grid, ...}}
    vol_surfaces: dict[str, dict] = Field(default_factory=dict)

    _NESTED_MAP_FIELDS: tuple[str, ...] = (
        "equity_spots",
        "equity_vols",
        "fx_spots",
        "fx_vols",
        "rates",
        "key_rates",
        "dividend_yields",
        "projection_rates",
        "rate_spreads",
        "ir_vols",
        "ir_future_quotes",
        "curves",
        "vol_surfaces",
    )

    def _apply_nested_freeze(self) -> None:
        """Recursively freeze all nested map fields in-place (via object.__setattr__)."""
        for name in self._NESTED_MAP_FIELDS:
            object.__setattr__(self, name, _deep_freeze(_deep_unfreeze(getattr(self, name))))

    @model_validator(mode="after")
    def _freeze_nested_maps(self):
        for name in self._NESTED_MAP_FIELDS:
            _assert_nested_floats_finite(getattr(self, name))
        self._apply_nested_freeze()
        return self

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False):
        """Copy then re-freeze.

        Pydantic v2 ``model_copy(update=...)`` does not re-run after validators, so
        plain dict updates would otherwise leave nested ``curves`` /
        ``vol_surfaces`` mutable and ``as_of`` unparsed.
        """
        copied = super().model_copy(update=update, deep=deep)
        object.__setattr__(copied, "as_of", _AS_OF_ADAPTER.validate_python(copied.as_of))
        MarketSnapshot._apply_nested_freeze(copied)
        return copied

    @field_serializer("as_of")
    def _ser_as_of(self, value: date | AsOfLabel) -> str:
        return as_of_wire(value)

    @field_serializer(
        "equity_spots",
        "equity_vols",
        "fx_spots",
        "fx_vols",
        "rates",
        "dividend_yields",
        "projection_rates",
        "rate_spreads",
        "ir_vols",
        "ir_future_quotes",
        "key_rates",
        "curves",
        "vol_surfaces",
    )
    def _ser_nested_map(self, value: Mapping) -> dict:
        return _deep_unfreeze(value)

    @property
    def equity(self):
        """Canonical typed equity sub-market view (``app.market.markets.EquityMarket``)."""
        from app.market.markets import EquityMarket

        return EquityMarket(spots=self.equity_spots, dividend_yields=self.dividend_yields)

    @field_validator("fx_spots")
    @classmethod
    def _validate_fx_spot_keys(cls, value: Mapping) -> Mapping:
        """Reject non-6-letter ISO FX pair keys. Empty ``fx_spots`` stays valid."""
        for pair in value:
            _require_fx_pair(str(pair))
        return value

    @property
    def rates_market(self):
        """Canonical typed rates sub-market view (``app.market.markets.RateMarket``)."""
        from app.market.markets import RateMarket, typed_yield_curves

        return RateMarket(
            discount=self.rates,
            projection=self.projection_rates,
            spreads=self.rate_spreads,
            key_rates=self.key_rates,
            curves=typed_yield_curves(self.curves),
        )

    @property
    def vol(self):
        """Canonical typed vol sub-market view (``app.market.markets.VolMarket``)."""
        from app.market.markets import VolMarket, typed_vol_surfaces

        return VolMarket(
            equity=self.equity_vols,
            fx=self.fx_vols,
            surfaces=typed_vol_surfaces(self.vol_surfaces),
        )

    @property
    def fx(self):
        """Canonical typed FX sub-market view (``app.market.markets.FxMarket``)."""
        from app.market.markets import FxMarket

        return FxMarket(spots=self.fx_spots)

    def _staging_maps(self) -> dict[str, Any]:
        """Mutable plain-dict copies of all nested map fields (unfrozen once)."""
        return {name: _deep_unfreeze(getattr(self, name)) for name in self._NESTED_MAP_FIELDS}

    def _stage_rate_zero(self, staging: dict[str, Any], factor, amount: float, current_id: str) -> str:
        """Parallel vs tenor RateZero shock into staging (see class docstring)."""
        ccy = factor.currency
        tenor = factor.tenor
        parallel = tenor in _RATE_PARALLEL_TENORS
        rates = staging["rates"]
        key_rates = staging["key_rates"]
        curves = staging["curves"]

        if parallel:
            if ccy not in rates:
                raise KeyError(f"rate not in snapshot: {ccy}")
            rates[ccy] = rates[ccy] + amount
            if ccy in key_rates:
                key_rates[ccy] = {t: float(z) + amount for t, z in key_rates[ccy].items()}
            for name, payload in list(curves.items()):
                if _curve_matches_currency(payload, ccy):
                    curves[name] = _bump_curve_zeros(payload, amount, tenor=None)
            return f"{current_id}:bump:{factor.key}:{tenor}"

        # Tenor-specific: key_rates + curve zeros only — never parallel-shift rates[ccy].
        touched = False
        if ccy in key_rates and tenor in key_rates[ccy]:
            key_rates[ccy][tenor] = float(key_rates[ccy][tenor]) + amount
            touched = True
        for name, payload in list(curves.items()):
            if not _curve_matches_currency(payload, ccy):
                continue
            zeros = payload.get("zeros") or {}
            if tenor in zeros:
                curves[name] = _bump_curve_zeros(payload, amount, tenor=tenor)
                touched = True
        if not touched:
            raise KeyError(
                f"tenor {tenor!r} not in key_rates or curves for {ccy}; "
                f"use RateZero({ccy!r}, 'PARALLEL') or 'ALL' for a parallel shock"
            )
        return f"{current_id}:bump:{factor.key}:{tenor}"

    def _stage_shock(self, staging: dict[str, Any], factor, amount: float, current_id: str) -> str:
        """Apply one typed shock to staging maps; return the bump-chained id."""
        from app.risk.factor_types import EquitySpot, EquityVol, FXSpot, FXVol, RateZero

        if isinstance(factor, EquitySpot):
            spots = staging["equity_spots"]
            if factor.symbol not in spots:
                raise KeyError(f"equity spot not in snapshot: {factor.symbol}")
            spots[factor.symbol] = spots[factor.symbol] * (1.0 + amount)
            return f"{current_id}:bump:{factor.key}"
        if isinstance(factor, FXSpot):
            spots = staging["fx_spots"]
            if factor.pair not in spots:
                raise KeyError(f"fx spot not in snapshot: {factor.pair}")
            spots[factor.pair] = spots[factor.pair] * (1.0 + amount)
            return f"{current_id}:bump:{factor.key}"
        if isinstance(factor, EquityVol):
            vols = staging["equity_vols"]
            if factor.underlying not in vols:
                raise KeyError(f"equity vol not in snapshot: {factor.underlying}")
            vols[factor.underlying] = max(1e-6, vols[factor.underlying] * (1.0 + amount))
            surfaces = staging["vol_surfaces"]
            payload = surfaces.get(factor.underlying)
            if payload is not None and _vol_surface_matches_asset_class(payload, "equity"):
                surfaces[factor.underlying] = _bump_vol_surface_payload(payload, factor, amount)
                vols[factor.underlying] = float(surfaces[factor.underlying]["atm_vol"])
            return f"{current_id}:bump:{factor.key}"
        if isinstance(factor, FXVol):
            vols = staging["fx_vols"]
            if factor.pair not in vols:
                raise KeyError(f"fx vol not in snapshot: {factor.pair}")
            vols[factor.pair] = max(1e-6, vols[factor.pair] * (1.0 + amount))
            surfaces = staging["vol_surfaces"]
            payload = surfaces.get(factor.pair)
            if payload is not None and _vol_surface_matches_asset_class(payload, "fx"):
                surfaces[factor.pair] = _bump_vol_surface_payload(payload, factor, amount)
                vols[factor.pair] = float(surfaces[factor.pair]["atm_vol"])
            return f"{current_id}:bump:{factor.key}"
        if isinstance(factor, RateZero):
            return self._stage_rate_zero(staging, factor, amount, current_id)
        raise TypeError(f"unsupported risk factor type: {type(factor)!r}")

    def bump(self, factor, amount: float) -> MarketSnapshot:
        """Return a new snapshot with one typed factor shocked."""
        return self.apply([(factor, amount)])

    def apply(self, shocks: list) -> MarketSnapshot:
        """Apply an ordered sequence of ``(RiskFactor, amount)`` shocks.

        Stages all nested maps once, applies every shock with the same
        semantics as historical per-factor ``bump``, then constructs one new
        immutable snapshot (single ``model_copy`` / nested freeze). Empty
        ``shocks`` returns ``self``.

        Id policy: each shock appends the same ``:bump:…`` suffix that a
        successive ``bump`` would, so ``apply(shocks).id`` matches the final
        id of sequential bumping. Callers that assign a scenario id (e.g.
        ``apply_scenario``) may ``model_copy`` the id afterward.
        """
        if not shocks:
            return self
        staging = self._staging_maps()
        new_id = self.id
        for factor, amount in shocks:
            new_id = self._stage_shock(staging, factor, amount, new_id)
        update = {"id": new_id, **staging}
        return self.model_copy(update=update)

    def diff(self, other: MarketSnapshot) -> dict[str, float]:
        """Content diff vs ``other`` (self → other).

        Spots/vols (incl. surface grid nodes): relative changes.
        Rates / key_rates / projection / dividends / curve zeros: absolute.
        Keys use typed factor ``.key`` strings where applicable.
        """
        out: dict[str, float] = {}
        for sym, base in self.equity_spots.items():
            nxt = other.equity_spots.get(sym)
            if nxt is not None and base != 0:
                rel = (nxt - base) / base
                if rel != 0:
                    out[sym] = rel
        for sym, base in self.equity_vols.items():
            nxt = other.equity_vols.get(sym)
            if nxt is not None and base != 0:
                rel = (nxt - base) / base
                if rel != 0:
                    out[f"{sym}:VOL"] = rel
        for pair, base in self.fx_spots.items():
            nxt = other.fx_spots.get(pair)
            if nxt is not None and base != 0:
                rel = (nxt - base) / base
                if rel != 0:
                    out[pair] = rel
        for pair, base in self.fx_vols.items():
            nxt = other.fx_vols.get(pair)
            if nxt is not None and base != 0:
                rel = (nxt - base) / base
                if rel != 0:
                    out[f"{pair}:VOL"] = rel
        for ccy, base in self.rates.items():
            nxt = other.rates.get(ccy)
            if nxt is not None and nxt != base:
                out[f"{ccy}:RATE"] = nxt - base
        for ccy, tenors in self.key_rates.items():
            other_tenors = other.key_rates.get(ccy) or {}
            for tenor, base in tenors.items():
                nxt = other_tenors.get(tenor)
                if nxt is not None and nxt != base:
                    out[f"{ccy}:RATE:{tenor}"] = float(nxt) - float(base)
        for ccy, base in self.projection_rates.items():
            nxt = other.projection_rates.get(ccy)
            if nxt is not None and nxt != base:
                out[f"{ccy}:PROJ"] = float(nxt) - float(base)
        for sym, base in self.dividend_yields.items():
            nxt = other.dividend_yields.get(sym)
            if nxt is not None and nxt != base:
                out[f"{sym}:DIV"] = float(nxt) - float(base)
        for name, payload in self.curves.items():
            other_payload = other.curves.get(name)
            if other_payload is None:
                continue
            zeros = payload.get("zeros") or {}
            other_zeros = other_payload.get("zeros") or {}
            for tenor, base in zeros.items():
                nxt = other_zeros.get(tenor)
                if nxt is not None and float(nxt) != float(base):
                    out[f"{name}:ZERO:{tenor}"] = float(nxt) - float(base)
        for name, payload in self.vol_surfaces.items():
            other_payload = other.vol_surfaces.get(name)
            if other_payload is None:
                continue
            grid = payload.get("grid") or {}
            other_grid = other_payload.get("grid") or {}
            for node, base in grid.items():
                nxt = other_grid.get(node)
                if nxt is not None and float(base) != 0 and float(nxt) != float(base):
                    out[f"{name}:VOL:{node}"] = (float(nxt) - float(base)) / float(base)
            base_atm = payload.get("atm_vol")
            nxt_atm = other_payload.get("atm_vol")
            if (
                base_atm is not None
                and nxt_atm is not None
                and float(base_atm) != 0
                and float(nxt_atm) != float(base_atm)
            ):
                out[f"{name}:ATM_VOL"] = (float(nxt_atm) - float(base_atm)) / float(base_atm)
        return out

    def content_hash(self) -> str:
        """Deterministic hash of market marks (excludes id/as_of)."""
        import hashlib
        import json

        payload = {
            "equity_spots": _deep_unfreeze(self.equity_spots),
            "equity_vols": _deep_unfreeze(self.equity_vols),
            "fx_spots": _deep_unfreeze(self.fx_spots),
            "fx_vols": _deep_unfreeze(self.fx_vols),
            "rates": _deep_unfreeze(self.rates),
            "key_rates": _deep_unfreeze(self.key_rates),
            "dividend_yields": _deep_unfreeze(self.dividend_yields),
            "projection_rates": _deep_unfreeze(self.projection_rates),
            "rate_spreads": _deep_unfreeze(self.rate_spreads),
            "ir_vols": _deep_unfreeze(self.ir_vols),
            "ir_future_quotes": _deep_unfreeze(self.ir_future_quotes),
            "curves": _deep_unfreeze(self.curves),
            "vol_surfaces": _deep_unfreeze(self.vol_surfaces),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()


class Valuation(BaseModel):
    position_id: str
    market_value: float
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    dv01: float = 0.0
    fx_delta: float = 0.0


class VaRMethodology(str, Enum):
    """Historical VaR approximation / revaluation mode (M2.3).

    - LINEAR: first-order Greek approximation (no gamma)
    - DELTA_GAMMA: delta-gamma + vega/DV01/FX (legacy default)
    - FULL_REVALUATION: reprice under each historical shocked MarketSnapshot
    """

    LINEAR = "LINEAR"
    DELTA_GAMMA = "DELTA_GAMMA"
    FULL_REVALUATION = "FULL_REVALUATION"


class RiskSummary(BaseModel):
    portfolio_id: str
    market_value: float
    delta: float
    gamma: float
    vega: float
    dv01: float
    fx_delta: float = 0.0
    var_95: float
    var_99: float
    expected_shortfall_99: float
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA


class RiskFactorExposure(BaseModel):
    factor: str
    factor_type: Literal["equity", "vol", "rate", "fx"]
    bucket: str
    exposure: float


class ScenarioKind(str, Enum):
    FACTOR = "factor"
    MACRO = "macro"
    HISTORICAL_STYLE = "historical_style"
    CUSTOM = "custom"
    REVERSE = "reverse"


class StressScenario(FiniteInputMixin):
    id: str | None = None
    name: str
    description: str = ""
    kind: ScenarioKind = ScenarioKind.FACTOR
    horizon: str = "instant"
    equity_shock: FiniteFloat = 0.0
    vol_shock: FiniteFloat = 0.0
    rates_shift_bps: FiniteFloat = 0.0
    fx_shock: FiniteFloat = 0.0
    equity_shocks: dict[str, FiniteFloat] = {}
    vol_shocks: dict[str, FiniteFloat] = {}
    rate_shocks_bps: dict[str, FiniteFloat] = {}
    fx_shocks: dict[str, FiniteFloat] = {}
    max_loss_pct: FiniteFloat | None = Field(default=None, gt=0)


class StressResult(BaseModel):
    scenario: str
    pnl: float
    by_position: dict[str, float]


class PositionStressContribution(BaseModel):
    position_id: str
    pnl: float
    contribution_pct: float


class ScenarioContribution(BaseModel):
    """One entity's stress P&L contribution for a scenario (M3.4).

    ``pnl`` uses the same currency units and sign as portfolio stress P&L
    (negative = loss). Contributions within a dimension sum to ``portfolio_pnl``.
    """

    key: str
    label: str = ""
    pnl: float
    contribution_pct: float


class ScenarioContributionBreakdown(BaseModel):
    """Hierarchy + risk-factor decomposition for one stress scenario (M3.4)."""

    scenario_id: str
    portfolio_pnl: float
    by_portfolio: list[ScenarioContribution]
    by_desk: list[ScenarioContribution]
    by_strategy: list[ScenarioContribution]
    by_book: list[ScenarioContribution]
    by_trade: list[ScenarioContribution]
    by_risk_factor: list[ScenarioContribution]
    reconciliation_error_portfolio: float = 0.0
    reconciliation_error_desk: float = 0.0
    reconciliation_error_strategy: float = 0.0
    reconciliation_error_book: float = 0.0
    reconciliation_error_trade: float = 0.0
    reconciliation_error_risk_factor: float = 0.0


class StressEvaluation(BaseModel):
    scenario_id: str
    scenario: str
    kind: ScenarioKind
    description: str
    base_market_value: float
    stressed_market_value: float
    pnl: float
    loss: float
    loss_pct_nav: float
    threat_level: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    breached: bool
    max_loss_pct: float | None = None
    by_position: dict[str, float]
    top_loss_contributors: list[PositionStressContribution]
    # Full hierarchy/factor decomposition (M3.4); optional for backward compat.
    contributions: ScenarioContributionBreakdown | None = None


class ScenarioEvaluationReport(BaseModel):
    portfolio_id: str
    base_market_value: float
    worst_scenario: str | None
    worst_loss: float
    severe_count: int
    breach_count: int
    evaluations: list[StressEvaluation]


class ReverseStressConvergence(BaseModel):
    """Numerical solver diagnostics for single-factor reverse stress (M3.5)."""

    iterations: int = Field(ge=0)
    tolerance: float = Field(ge=0)
    search_bound: float = Field(gt=0, description="Wire-unit search bound (relative or bp).")
    bound_loss_pct: float = Field(ge=0, description="Loss % of |NAV| at the search bound.")
    method: str = "binary_search"
    message: str | None = None


class ReverseStressResult(BaseModel):
    """Reverse-stress answer: required factor move for a target loss.

    Legacy fields (``factor``, ``target_loss_pct``, ``required_shock``,
    ``achieved_loss_pct``, ``converged``) remain stable for
    ``POST /risk/stress/reverse``. M3.5 adds absolute target loss, resulting
    P&L, shock unit, base MV, and convergence diagnostics. R0.4.2-G adds the
    canonical ``Scenario`` that was applied (JSON projects as ScenarioWire;
    ``required_shock`` wire units are unchanged).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    factor: str
    target_loss_pct: float
    required_shock: float | None
    achieved_loss_pct: float
    converged: bool
    # Absolute target loss in portfolio currency (|NAV| * target_loss_pct).
    target_loss: float = 0.0
    # Portfolio P&L at the solved shock (or at the search bound if not converged).
    pnl: float = 0.0
    shock_unit: Literal["relative", "bp"] = "relative"
    base_market_value: float = 0.0
    convergence: ReverseStressConvergence | None = None
    scenario: Any = Field(
        default=None,
        description="Canonical Scenario applied at the solved, bound, or zero shock.",
    )

    @field_serializer("scenario")
    def _serialize_scenario(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        from app.persistence.scenario_codec import scenario_to_definition

        return scenario_to_definition(value)

    @field_validator("scenario", mode="before")
    @classmethod
    def _parse_scenario(cls, value: Any) -> Any:
        if value is None:
            return None
        from app.risk.scenario_model import Scenario as CanonicalScenario

        if isinstance(value, CanonicalScenario):
            return value
        if isinstance(value, Mapping):
            from app.persistence.scenario_codec import definition_to_scenario

            return definition_to_scenario(dict(value))
        return value


class FactorShockSolution(BaseModel):
    factor: str
    required_shock: float
    shock_unit: Literal["relative", "bp"]
    weight: float
    max_shock: float


class MultiFactorReverseStressResult(BaseModel):
    """Multi-factor reverse-stress solution with documented solver metadata."""

    target_loss_pct: float
    target_loss: float
    achieved_loss_pct: float
    pnl: float
    base_market_value: float
    converged: bool
    objective_l2: float | None = None
    shocks: list[FactorShockSolution] = Field(default_factory=list)
    factors: list[str] = Field(default_factory=list)
    method: str = "ray_search_coordinate_descent"
    iterations: int = 0
    message: str | None = None
    assumptions: list[str] = Field(default_factory=list)


class ScenarioComparison(BaseModel):
    """Per-scenario before/after hedge P&L (legacy fields) plus loss diagnostics (M3.7)."""

    scenario: str
    base_pnl: float
    hedged_pnl: float
    improvement: float
    # Loss = max(0, -pnl); loss_improvement = base_loss - hedged_loss (>0 = hedge helps).
    base_loss: float = 0.0
    hedged_loss: float = 0.0
    loss_improvement: float = 0.0


class Contributor(BaseModel):
    position_id: str
    label: str
    risk_amount: float
    contribution_pct: float


LimitMetric = Literal[
    "var_99",
    "var_95",
    "expected_shortfall_99",
    "dv01",
    "key_rate_dv01",
    "vega",
    "fx_delta",
    "single_position_pct",
    "stress_loss",
]

LimitStatus = Literal["OK", "WARNING", "BREACH"]

LimitScope = Literal["firm", "portfolio", "desk", "strategy", "book", "trade"]


class RiskLimit(FiniteInputMixin):
    """Configurable risk limit with optional warning band.

    ``warning_threshold_pct`` is utilization (%) at/above which status becomes
    WARNING while still below the hard ``limit`` (BREACH when value > limit).
    ``scope`` / ``label`` are informational (e.g. firm vs desk VaR); evaluation
    uses the portfolio subset passed to ``LimitEngine``.
    """

    metric: LimitMetric
    limit: FiniteFloat
    warning_threshold_pct: FiniteFloat = 80.0
    scope: LimitScope | None = None
    label: str | None = None


class LimitResult(BaseModel):
    metric: str
    value: float
    limit: float
    utilization_pct: float
    breached: bool
    status: LimitStatus = "OK"
    warning_threshold_pct: float = 80.0
    scope: LimitScope | None = None
    label: str | None = None


class VaRMethodResult(BaseModel):
    method: Literal["historical", "parametric"]
    confidence: float
    var: float
    expected_shortfall: float


class RiskContribution(BaseModel):
    position_id: str
    component_var: float
    contribution_pct: float
    # Historical tail-conditional ES contribution (M2.5); optional for backward compat.
    component_es: float | None = None
    es_contribution_pct: float | None = None
    # M2.7: Euler ∂VaR/∂w_i at current holdings; equals component_var when w_i ≡ 1
    marginal_var: float = 0.0


class ESContribution(BaseModel):
    """One entity's historical Expected Shortfall contribution (M2.5).

    ``component_es`` is the mean entity loss on portfolio-tail scenarios
    (loss = -P&L). Contributions within a dimension sum to ``portfolio_es``.
    """

    key: str
    label: str = ""
    component_es: float
    contribution_pct: float


class ESContributionReport(BaseModel):
    """Tail-conditional ES contributions by hierarchy and risk factor (M2.5)."""

    portfolio_id: str
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA
    confidence: float
    portfolio_var: float
    portfolio_es: float
    by_position: list[ESContribution]
    by_book: list[ESContribution]
    by_strategy: list[ESContribution]
    by_desk: list[ESContribution]
    by_risk_factor: list[ESContribution]
    reconciliation_error_position: float = 0.0
    reconciliation_error_book: float = 0.0
    reconciliation_error_strategy: float = 0.0
    reconciliation_error_desk: float = 0.0
    reconciliation_error_risk_factor: float = 0.0


class VaRReport(BaseModel):
    portfolio_id: str
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA
    methods: list[VaRMethodResult]
    contributions: list[RiskContribution]


class VaRMethodologyMetrics(BaseModel):
    """One methodology's historical VaR/ES plus wall-clock runtime (M2.4)."""

    methodology: VaRMethodology
    var_95: float
    var_99: float
    expected_shortfall_99: float
    runtime_ms: float


class VaRMethodologyComparison(BaseModel):
    """Side-by-side Linear / Δ-Γ / Full-revaluation VaR comparison (M2.4)."""

    portfolio_id: str
    observations: int
    results: list[VaRMethodologyMetrics]


class HierarchyLevel(str, Enum):
    """Canonical firm risk tree (M4.1)."""

    FIRM = "firm"
    PORTFOLIO = "portfolio"
    DESK = "desk"
    STRATEGY = "strategy"
    BOOK = "book"
    TRADE = "trade"


class HierarchyRef(BaseModel):
    """Address of a node in the Firm → … → Trade tree for risk subsetting."""

    level: HierarchyLevel
    firm: str | None = None
    portfolio_id: str | None = None
    desk: str | None = None
    strategy: str | None = None
    book: str | None = None
    trade_id: str | None = None


class LimitBreachDrilldown(BaseModel):
    """One limit row enriched with hierarchy context and top contributors."""

    hierarchy_node: str
    hierarchy_level: LimitScope
    metric: str
    value: float
    limit: float
    utilization_pct: float
    breached: bool
    status: LimitStatus = "OK"
    warning_threshold_pct: float = 80.0
    scope: LimitScope | None = None
    label: str | None = None
    contributors: list[Contributor] = Field(default_factory=list)


class LimitDrilldownReport(BaseModel):
    portfolio_id: str
    hierarchy_node: str
    hierarchy_level: LimitScope
    items: list[LimitBreachDrilldown] = Field(default_factory=list)


class HierarchyNode(BaseModel):
    """Risk tree node with NAV / Greeks / VaR / ES / stress / limits (M4.2).

    Additive metrics (reconcile parent == sum children within abs 1e-9):
    ``market_value``, ``delta``, ``gamma``, ``vega``, ``dv01``, ``fx_delta``,
    and each scenario's stress ``pnl``.

    Non-additive metrics are computed on the node sub-portfolio:
    ``var_95``, ``var_99``, ``expected_shortfall_99``, ``limits``.

    ``id`` is the stable node key (aligned with ``portfolio_at`` sub-portfolio
    ids). Default ``""`` keeps older payloads/OpenAPI clients parseable;
    ``HierarchyEngine`` always populates it.
    """

    id: str = ""
    name: str
    level: Literal["firm", "portfolio", "desk", "strategy", "book", "trade"]
    market_value: float
    var_99: float
    path: str = ""
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    dv01: float = 0.0
    fx_delta: float = 0.0
    var_95: float = 0.0
    expected_shortfall_99: float = 0.0
    stress: list[StressResult] = Field(default_factory=list)
    limits: list[LimitResult] = Field(default_factory=list)
    children: list["HierarchyNode"] = []


class AttributionItem(BaseModel):
    driver: str
    pnl: float


class AttributionReport(BaseModel):
    base_market_value: float
    current_market_value: float
    total_change: float
    explained_change: float
    residual: float
    items: list[AttributionItem]


class AttributionRequest(FiniteInputMixin):
    previous_portfolio: Portfolio
    current_portfolio: Portfolio
    previous_market: MarketSnapshot | None = None
    current_market: MarketSnapshot | None = None
    # Day fraction for theta (maturity aging). 0 → no theta. Additive; optional for API compat.
    dt_years: FiniteFloat = 0.0


class RiskChangeItem(BaseModel):
    """One driver of a change in a risk metric (VaR / ES), not P&L."""

    driver: str
    delta_risk: float


class RiskChangeAttributionReport(BaseModel):
    """Waterfall explaining why a risk metric changed between two states."""

    metric: Literal["var_99", "var_95", "expected_shortfall_99"] = "var_99"
    previous_risk: float
    current_risk: float
    total_change: float
    explained_change: float
    residual: float
    items: list[RiskChangeItem]


class RiskChangeAttributionRequest(FiniteInputMixin):
    previous_portfolio: Portfolio
    current_portfolio: Portfolio
    previous_market: MarketSnapshot | None = None
    current_market: MarketSnapshot | None = None
    metric: Literal["var_99", "var_95", "expected_shortfall_99"] = "var_99"
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA


class WhatIfChange(FiniteInputMixin):
    """One hypothetical trade mutation for incremental VaR / what-if (M2.8/M2.9).

    - ``add``: requires ``position`` with a new unique id
    - ``remove``: requires ``position_id`` (or ``position.id``)
    - ``modify``: requires ``position``; ``position_id`` defaults to ``position.id``
    """

    operation: Literal["add", "remove", "modify"]
    position_id: str | None = None
    position: Position | None = None


class WhatIfRequest(FiniteInputMixin):
    """What-if request: evaluate changes without mutating persisted portfolio state."""

    portfolio: Portfolio
    changes: list[WhatIfChange]
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA
    scenarios: list[StressScenario] | None = None


class WhatIfIncrementalRisk(BaseModel):
    """Metric-wise after − before (currency loss for VaR/ES; same units as RiskSummary)."""

    market_value: float
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    dv01: float = 0.0
    fx_delta: float = 0.0
    var_95: float
    var_99: float
    expected_shortfall_99: float


class FactorExposureChange(BaseModel):
    factor: str
    factor_type: Literal["equity", "vol", "rate", "fx"]
    bucket: str
    before: float
    after: float
    delta: float


class HedgeComparisonReport(BaseModel):
    """Strengthened hedge comparison (M3.7).

    Sign conventions:
    - ``hedge_cost`` = MV(hedged) − MV(base); positive ≈ capital deployed / higher MV
    - ``var_improvement`` / ``es_improvement`` = base − hedged (>0 = risk reduced)
    - per-scenario ``improvement`` remains hedged_pnl − base_pnl (legacy)
    """

    hedge_cost: float
    base_market_value: float
    hedged_market_value: float
    base_var_99: float
    hedged_var_99: float
    base_expected_shortfall_99: float
    hedged_expected_shortfall_99: float
    var_improvement: float
    es_improvement: float
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA
    factor_exposure_changes: list[FactorExposureChange] = Field(default_factory=list)
    scenarios: list[ScenarioComparison] = Field(default_factory=list)


class StressLossChange(BaseModel):
    scenario: str
    before_pnl: float
    after_pnl: float
    delta_pnl: float


class WhatIfReport(BaseModel):
    """What-if / incremental VaR response (M2.8/M2.9)."""

    portfolio_id: str
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA
    before: RiskSummary
    after: RiskSummary
    incremental: WhatIfIncrementalRisk
    changed_factor_exposures: list[FactorExposureChange] = Field(default_factory=list)
    changed_stress_losses: list[StressLossChange] = Field(default_factory=list)


class RiskRunStatus(str, Enum):
    """Lifecycle states for a risk run (M5.2 domain; M5.3 execution)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RiskResultRef(BaseModel):
    """Reference to a named result payload stored with a risk run.

    Full payloads live in persistence ``risk_results``; the domain header only
    carries type + optional row id so APIs can link without duplicating bodies.
    """

    result_type: str = Field(min_length=1)
    result_id: int | None = None


def _utcnow_domain() -> datetime:
    return datetime.now(UTC)


class RiskRunCalculationConfig(BaseModel):
    """Deterministic calculation knobs captured on a RiskRun.

    Observations and methodology extras only — no free-form secrets or
    vendor credentials. Unknown keys are rejected (``extra='forbid'``).
    """

    model_config = ConfigDict(extra="forbid")

    observations: int | None = Field(default=None, ge=1, le=5000)
    seed: int | None = None
    confidence: float | None = Field(default=None, gt=0.0, lt=1.0)


class RiskRun(BaseModel):
    """Domain DTO for a persisted / async risk computation (M5.2).

    Persistence field mapping (ORM ``RiskRunRow``):
    - ``completed_at`` ↔ ``finished_at``
    - ``error`` ↔ ``error_message``
    - ``result_refs`` ↔ ``risk_results`` (``result_type`` + row ``id``)
    - ``pricing_engine_version``, ``methodology``, ``scenario_set`` are first-class
      columns (Alembic ``002_risk_run_domain_fields``)
    - ``historical_dataset_id``, ``historical_dataset_version``, ``as_of``,
      ``calculation_config`` are first-class spec columns
      (Alembic ``003_risk_run_spec_fields``); omitted remains valid for old rows.
    - ``portfolio_version`` is captured from the stored book at submit
      (Alembic ``004_portfolio_version``); omitted remains valid for old rows.
    - ``owner`` is the submitting shared-profile principal (Alembic
      ``005_object_owner``); omitted remains valid for old rows.
    - ``run_type`` / ``request`` remain the generic envelope for M5.3/M5.4.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    portfolio_version: int | None = Field(default=None, ge=1)
    owner: str | None = None
    market_snapshot_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow_domain)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    pricing_engine_version: str | None = None
    methodology: VaRMethodology | None = None
    scenario_set: list[str] = Field(default_factory=list)
    historical_dataset_id: str | None = None
    historical_dataset_version: str | None = None
    as_of: AsOf | None = None
    calculation_config: RiskRunCalculationConfig | None = None
    status: RiskRunStatus = RiskRunStatus.QUEUED
    result_refs: list[RiskResultRef] = Field(default_factory=list)
    error: str | None = None
    run_type: str = Field(default="summary", min_length=1)
    request: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("as_of")
    def _ser_as_of(self, value: date | AsOfLabel | None) -> str | None:
        if value is None:
            return None
        return as_of_wire(value)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration(self) -> float | None:
        """Wall-clock seconds from ``started_at`` to ``completed_at``, if both set."""
        if self.started_at is None or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> RiskRun:
        if not self.id.strip():
            raise ValueError("id must be non-empty")
        if not self.portfolio_id.strip():
            raise ValueError("portfolio_id must be non-empty")
        for sid in self.scenario_set:
            if not str(sid).strip():
                raise ValueError("scenario_set entries must be non-empty")
        if self.pricing_engine_version is not None and not self.pricing_engine_version.strip():
            raise ValueError("pricing_engine_version must be non-empty when set")
        if self.historical_dataset_id is not None and not self.historical_dataset_id.strip():
            raise ValueError("historical_dataset_id must be non-empty when set")
        if (
            self.historical_dataset_version is not None
            and not self.historical_dataset_version.strip()
        ):
            raise ValueError("historical_dataset_version must be non-empty when set")

        if self.started_at is not None and self.completed_at is not None:
            if self.completed_at < self.started_at:
                raise ValueError("completed_at must be >= started_at")

        status = self.status
        if status == RiskRunStatus.QUEUED:
            if self.started_at is not None or self.completed_at is not None:
                raise ValueError("QUEUED runs must not have started_at or completed_at")
            if self.error is not None:
                raise ValueError("QUEUED runs must not have error")
        elif status == RiskRunStatus.RUNNING:
            if self.started_at is None:
                raise ValueError("RUNNING runs require started_at")
            if self.completed_at is not None:
                raise ValueError("RUNNING runs must not have completed_at")
            if self.error is not None:
                raise ValueError("RUNNING runs must not have error")
        elif status == RiskRunStatus.COMPLETED:
            if self.started_at is None or self.completed_at is None:
                raise ValueError("COMPLETED runs require started_at and completed_at")
            if self.error is not None:
                raise ValueError("COMPLETED runs must not have error")
        elif status == RiskRunStatus.FAILED:
            if self.started_at is None or self.completed_at is None:
                raise ValueError("FAILED runs require started_at and completed_at")
            if self.error is None or not str(self.error).strip():
                raise ValueError("FAILED runs require a non-empty error")
        return self
