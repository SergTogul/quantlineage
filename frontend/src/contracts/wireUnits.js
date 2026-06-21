/**
 * Display % / bp → ScenarioWire bump units (request shaping only; no risk math).
 * Equity/FX/vol: fraction. Rates: absolute decimal (100 bp → 0.01).
 */

export function displayPercentToFraction(displayPct) {
  return Number(displayPct) / 100
}

export function displayBpsToDecimal(bps) {
  return Number(bps) / 10_000
}

const RELATIVE_TYPES = new Set(['equity', 'vol', 'fx'])

/**
 * Fail closed if a UI form leaked display %/bp onto a formal ScenarioWire shock.
 * Relative |amount| ≥ 2 (e.g. −20, 50) is display percent, not a fraction.
 * Rate |amount| ≥ 1 (e.g. 100) is display bp, not a decimal bump.
 */
export function assertFormalScenarioShocks(scenario) {
  for (const shock of scenario?.shocks || []) {
    const amount = Number(shock.amount)
    const type = shock.factor_type
    if (!Number.isFinite(amount)) {
      throw new Error(`ScenarioWire ${type} amount is not a finite wire fraction`)
    }
    if (RELATIVE_TYPES.has(type) && Math.abs(amount) >= 2) {
      throw new Error(
        `ScenarioWire ${type} amount ${amount} looks like display percent; expected a fraction (e.g. -20% → -0.20)`,
      )
    }
    if (type === 'rate' && Math.abs(amount) >= 1) {
      throw new Error(
        `ScenarioWire rate amount ${amount} looks like display bp; expected decimal (e.g. 100bp → 0.01)`,
      )
    }
  }
}

export function assertFormalScenarios(scenarios) {
  for (const scenario of scenarios || []) {
    assertFormalScenarioShocks(scenario)
  }
}

/**
 * Reverse-multi target_loss_pct / max_shock are fractions on the wire.
 * Display 5% / 80% leaked as 5 / 80 must fail.
 */
export function assertReverseMultiFractions({ target_loss_pct, max_shock } = {}) {
  if (target_loss_pct != null && Number(target_loss_pct) > 1) {
    throw new Error(
      `reverse-multi target_loss_pct ${target_loss_pct} looks like display percent; expected a fraction (e.g. 5% → 0.05)`,
    )
  }
  if (max_shock != null && Number(max_shock) > 2) {
    throw new Error(
      `reverse-multi max_shock ${max_shock} looks like display percent; expected a fraction (e.g. 80% → 0.80)`,
    )
  }
}
