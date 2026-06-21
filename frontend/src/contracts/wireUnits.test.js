import { describe, expect, it } from 'vitest'
import {
  assertFormalScenarioShocks,
  assertReverseMultiFractions,
  displayBpsToDecimal,
  displayPercentToFraction,
} from './wireUnits.js'

describe('display units → wire (not pricing math)', () => {
  it('maps display percent to a fraction', () => {
    expect(displayPercentToFraction(-20)).toBe(-0.2)
    expect(displayPercentToFraction(20)).toBe(0.2)
    expect(displayPercentToFraction(5)).toBe(0.05)
  })

  it('maps display basis points to a decimal rate', () => {
    expect(displayBpsToDecimal(100)).toBe(0.01)
    expect(displayBpsToDecimal(1)).toBe(0.0001)
  })
})

describe('request-boundary shock assertions', () => {
  it('accepts ScenarioWire bump-unit amounts', () => {
    expect(() =>
      assertFormalScenarioShocks({
        shocks: [
          { factor_type: 'equity', amount: -0.2 },
          { factor_type: 'vol', amount: 0.5 },
          { factor_type: 'rate', amount: 0.01 },
          { factor_type: 'fx', amount: -0.05 },
        ],
      }),
    ).not.toThrow()
  })

  it('rejects display-percent equity −20 leaked onto the wire', () => {
    expect(() =>
      assertFormalScenarioShocks({
        shocks: [{ factor_type: 'equity', amount: -20 }],
      }),
    ).toThrow(/display|fraction|wire/i)
  })

  it('rejects rates 100 bp leaked as 100 instead of 0.01', () => {
    expect(() =>
      assertFormalScenarioShocks({
        shocks: [{ factor_type: 'rate', amount: 100 }],
      }),
    ).toThrow(/display|decimal|wire|bp/i)
  })

  it('rejects reverse-multi display percents (5% / 80%) on the wire', () => {
    expect(() => assertReverseMultiFractions({ target_loss_pct: 5, max_shock: 80 })).toThrow(
      /display|fraction|wire/i,
    )
  })

  it('accepts reverse-multi fractions', () => {
    expect(() => assertReverseMultiFractions({ target_loss_pct: 0.05, max_shock: 0.8 })).not.toThrow()
  })
})
