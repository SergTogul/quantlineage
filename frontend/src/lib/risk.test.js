import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  money, topContributors, worstStress, limitStatus, limitStatusClass, percent, threatClass, stressSummary,
  topFactors, varMethod, hierarchyTradeCount, hierarchyCountByLevel, hierarchyPortfolio,
  hierarchySummary, hierarchyNodeAtPath, hierarchyChildRows, hierarchyNodeMetrics,
  hedgeComparisonSummary, reverseStressMultiSummary, scenarioPayload,
  attributionSummary, breachedLimits, limitDrilldownSummary, limitStatusCounts,
  spyFlatHedgePortfolio, defaultHedgeScenarios, stressFactorKeysFromPortfolio,
  riskRunStatus, riskRunStatusClass, isRiskRunTerminal, riskRunSummary, RISK_RUN_POLL_MS,
  ratesShowcaseSummary, runProvenanceSummary,
  spyScaledPortfolio, demoChangeAttributionRequest, riskChangeAttributionSummary,
  riskChangeReportSummary,
  demoPnLAttributionRequest, overviewKpis, overviewCollage,
  SCENARIO_PRESETS, defaultScenarioForm, validateScenarioForm,
  esContributionSummary, ES_CONTRIBUTION_DIMENSIONS, varCompareSummary,
  defaultReverseMultiForm, validateReverseMultiForm, reverseMultiRequestBody,
  selectedReverseMultiFactors, formatFactorShock, REVERSE_MULTI_FACTORS,
} from './risk.mjs'

test('money formats institutional-scale values',()=>{assert.equal(money(3_410_000),'$3.41M');assert.equal(money(-81_300),'-$81.3K')})
test('contributors are sorted by risk',()=>assert.deepEqual(topContributors([{risk_amount:2},{risk_amount:10},{risk_amount:3}],2).map(i=>i.risk_amount),[10,3]))
test('worst stress selects most negative pnl',()=>assert.equal(worstStress([{scenario:'a',pnl:-2},{scenario:'b',pnl:-9}]).scenario,'b'))
test('limitStatus prefers API status over utilization', () => {
  assert.equal(limitStatus({ status: 'OK', utilization_pct: 99, breached: false }), 'OK')
  assert.equal(limitStatus({ status: 'WARNING', utilization_pct: 10, breached: false }), 'WARNING')
  assert.equal(limitStatus({ status: 'BREACH', utilization_pct: 50, breached: true }), 'BREACH')
})
test('limitStatus falls back to util / breached when status missing', () => {
  assert.equal(limitStatus({ breached: true, utilization_pct: 101 }), 'BREACH')
  assert.equal(limitStatus({ breached: false, utilization_pct: 85 }), 'WARNING')
  assert.equal(limitStatus({ breached: false, utilization_pct: 50 }), 'OK')
})
test('limitStatusClass maps WARNING to warn for CSS', () => {
  assert.equal(limitStatusClass({ status: 'WARNING' }), 'warn')
  assert.equal(limitStatusClass({ status: 'OK' }), 'ok')
  assert.equal(limitStatusClass({ status: 'BREACH' }), 'breach')
})
test('threat helpers format severity and percentages',()=>{assert.equal(percent(.1234),'12.3%');assert.equal(threatClass('SEVERE'),'severe')})
test('stress summary exposes worst scenario and counters',()=>{const report={severe_count:2,breach_count:1,evaluations:[{scenario:'Crash',loss:12}]};assert.deepEqual(stressSummary(report),{worst:report.evaluations[0],severe:2,breaches:1})})
test('factor helpers rank by absolute exposure',()=>assert.equal(topFactors([{factor:'a',exposure:-20},{factor:'b',exposure:10}])[0].factor,'a'))
test('var method selects requested method',()=>assert.equal(varMethod({methods:[{method:'historical',var:1}]},'historical').var,1))
test('hierarchy counts trade leaves',()=>assert.equal(hierarchyTradeCount({level:'portfolio',children:[{level:'trade',children:[]},{level:'book',children:[{level:'trade',children:[]}]}]}),2))
test('scenario builder converts display units to formal ScenarioWire', () => {
  const x = scenarioPayload({ name: 'X', equity: -20, vol: 50, rates: 100, fx: -5, limit: 10 })
  assert.equal(x.id, 'ui_custom')
  assert.equal(x.category, 'custom')
  assert.equal(x.max_loss_pct, 0.1)
  assert.ok(!('equity_shock' in x))
  const byType = Object.fromEntries(
    ['equity', 'vol', 'rate', 'fx'].map((t) => [t, x.shocks.filter((s) => s.factor_type === t)]),
  )
  assert.ok(byType.equity.every((s) => s.amount === -0.2))
  assert.ok(byType.vol.every((s) => s.amount === 0.5))
  assert.ok(byType.rate.every((s) => s.amount === 0.01))
  assert.ok(byType.fx.every((s) => s.amount === -0.05))
  assert.ok(byType.equity.some((s) => s.key === 'SPY'))
  assert.ok(byType.rate.some((s) => s.key === 'USD:RATE' && s.bucket === 'ALL'))
})

test('stressFactorKeysFromPortfolio derives keys from positions', () => {
  const keys = stressFactorKeysFromPortfolio({
    positions: [
      { type: 'equity', symbol: 'SPY' },
      { type: 'fx_forward', pair: 'EURUSD' },
      { type: 'bond', currency: 'USD' },
    ],
  })
  assert.deepEqual(keys.equities, ['SPY'])
  assert.deepEqual(keys.fxPairs, ['EURUSD'])
  assert.deepEqual(keys.rateCcys, ['EUR', 'USD'])
})

const firmTree = {
  name: 'Acme Capital',
  level: 'firm',
  market_value: 3000,
  var_95: 80,
  var_99: 100,
  expected_shortfall_99: 140,
  delta: 10,
  gamma: 1,
  vega: 20,
  dv01: 5,
  fx_delta: 2,
  children: [{
    name: 'Multi Desk Book',
    level: 'portfolio',
    market_value: 3000,
    var_99: 100,
    children: [{
      name: 'Rates Desk',
      level: 'desk',
      children: [{
        name: 'Carry',
        level: 'strategy',
        children: [{
          name: 'Rates Book',
          level: 'book',
          children: [{ name: 'eq-a', level: 'trade', children: [] }],
        }],
      }],
    }, {
      name: 'Equity Desk',
      level: 'desk',
      children: [{
        name: 'Momentum',
        level: 'strategy',
        children: [{
          name: 'EQ Book',
          level: 'book',
          children: [
            { name: 'eq-b', level: 'trade', children: [] },
            { name: 'eq-c', level: 'trade', children: [] },
          ],
        }],
      }],
    }],
  }],
}

test('hierarchyPortfolio walks firm → portfolio', () => {
  const p = hierarchyPortfolio(firmTree)
  assert.equal(p.level, 'portfolio')
  assert.equal(p.name, 'Multi Desk Book')
  assert.equal(hierarchyPortfolio(p).name, 'Multi Desk Book')
  assert.equal(hierarchyPortfolio(null), null)
})

test('hierarchy counts by level under firm root', () => {
  assert.equal(hierarchyCountByLevel(firmTree, 'desk'), 2)
  assert.equal(hierarchyCountByLevel(firmTree, 'strategy'), 2)
  assert.equal(hierarchyCountByLevel(firmTree, 'book'), 2)
  assert.equal(hierarchyTradeCount(firmTree), 3)
})

test('hierarchySummary walks firm root and surfaces API metrics', () => {
  const s = hierarchySummary(firmTree)
  assert.equal(s.firmName, 'Acme Capital')
  assert.equal(s.portfolioName, 'Multi Desk Book')
  assert.equal(s.desks, 2)
  assert.equal(s.strategies, 2)
  assert.equal(s.books, 2)
  assert.equal(s.trades, 3)
  assert.equal(s.market_value, 3000)
  assert.equal(s.var_99, 100)
  assert.equal(s.expected_shortfall_99, 140)
  assert.equal(s.delta, 10)
  assert.equal(s.vega, 20)
  assert.equal(s.dv01, 5)
  assert.equal(hierarchySummary(null), null)
})

test('hierarchySummary does not treat desks as books (legacy bug)', () => {
  // Old UI used children[0].children[0].children.length as "books" which counted strategies under first desk.
  const s = hierarchySummary(firmTree)
  assert.notEqual(s.books, 1)
  assert.equal(s.books, 2)
})

test('hedgeComparisonSummary normalizes HedgeComparisonReport object', () => {
  const report = {
    hedge_cost: 50,
    var_improvement: 12,
    es_improvement: 8,
    base_var_99: 100,
    hedged_var_99: 88,
    base_expected_shortfall_99: 140,
    hedged_expected_shortfall_99: 132,
    methodology: 'DELTA_GAMMA',
    scenarios: [{ scenario: 'Crash', base_pnl: -10, hedged_pnl: -5, improvement: 5 }],
    factor_exposure_changes: [{ factor: 'SPX', before: 1, after: 0.5, delta: -0.5 }],
  }
  const s = hedgeComparisonSummary(report)
  assert.equal(s.hedge_cost, 50)
  assert.equal(s.var_improvement, 12)
  assert.equal(s.methodology, 'DELTA_GAMMA')
  assert.equal(s.scenarios.length, 1)
  assert.equal(s.factor_exposure_changes.length, 1)
})

test('hedgeComparisonSummary shims legacy list shape', () => {
  const legacy = [{ scenario: 'A', base_pnl: -1, hedged_pnl: 0, improvement: 1 }]
  const s = hedgeComparisonSummary(legacy)
  assert.equal(s.hedge_cost, null)
  assert.deepEqual(s.scenarios, legacy)
  assert.equal(s.methodology, null)
  assert.equal(hedgeComparisonSummary(null), null)
})

test('spyFlatHedgePortfolio zeros SPY equity qty only (request helper)', () => {
  const portfolio = {
    id: 'demo',
    name: 'Demo',
    positions: [
      { id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 },
      { id: 'opt-1', type: 'equity_option', symbol: 'SPY', quantity: 10 },
      { id: 'eq-2', type: 'equity', symbol: 'QQQ', quantity: 50 },
    ],
  }
  const hedged = spyFlatHedgePortfolio(portfolio)
  assert.equal(hedged.positions[0].quantity, 0)
  assert.equal(hedged.positions[1].quantity, 10)
  assert.equal(hedged.positions[2].quantity, 50)
  assert.equal(portfolio.positions[0].quantity, 100)
  assert.equal(spyFlatHedgePortfolio(null), null)
  assert.deepEqual(spyFlatHedgePortfolio({ id: 'x' }).positions, [])
})

test('defaultHedgeScenarios is formal Crash equity −20% wire', () => {
  const s = defaultHedgeScenarios()
  assert.equal(s.length, 1)
  assert.equal(s[0].name, 'Crash')
  assert.equal(s[0].category, 'factor')
  assert.ok(s[0].shocks.every((sh) => sh.factor_type === 'equity' && sh.amount === -0.2))
  assert.ok(s[0].shocks.some((sh) => sh.key === 'SPY'))
})

test('reverseStressMultiSummary parses multi-factor result', () => {
  const result = {
    converged: true,
    target_loss_pct: 0.1,
    target_loss: 500,
    achieved_loss_pct: 0.099,
    pnl: -500,
    base_market_value: 5000,
    objective_l2: 0.4,
    shocks: [{ factor: 'equity', required_shock: -0.2, shock_unit: 'relative', weight: 1, max_shock: 0.8 }],
    factors: ['equity'],
    method: 'ray_search_coordinate_descent',
    iterations: 3,
    message: null,
    assumptions: ['Adverse orthant'],
  }
  const s = reverseStressMultiSummary(result)
  assert.equal(s.converged, true)
  assert.equal(s.shocks.length, 1)
  assert.equal(s.factors[0], 'equity')
  assert.equal(s.method, 'ray_search_coordinate_descent')
  assert.equal(s.iterations, 3)
  assert.equal(s.assumptions[0], 'Adverse orthant')
  assert.equal(reverseStressMultiSummary(null), null)
})

test('defaultReverseMultiForm selects equity+vol', () => {
  const form = defaultReverseMultiForm()
  assert.deepEqual(selectedReverseMultiFactors(form), ['equity', 'vol'])
  assert.equal(REVERSE_MULTI_FACTORS.length, 4)
})

test('validateReverseMultiForm requires two factors and positive target', () => {
  const form = defaultReverseMultiForm()
  assert.equal(validateReverseMultiForm(form).ok, true)
  form.factors.vol = false
  assert.match(validateReverseMultiForm(form).error, /at least two/i)
  form.factors.vol = true
  form.target_loss_pct = 0
  assert.match(validateReverseMultiForm(form).error, /Target loss/i)
})

test('reverseMultiRequestBody maps display % to API fractions', () => {
  const form = defaultReverseMultiForm()
  form.weights.equity = '0.7'
  form.weights.vol = '0.3'
  const body = reverseMultiRequestBody(form)
  assert.equal(body.target_loss_pct, 0.05)
  assert.equal(body.max_shock, 0.8)
  assert.deepEqual(body.factors, ['equity', 'vol'])
  assert.deepEqual(body.weights, { equity: 0.7, vol: 0.3 })
})

test('reverseMultiRequestBody omits weights when blank', () => {
  const body = reverseMultiRequestBody(defaultReverseMultiForm())
  assert.equal(body.weights, undefined)
})

test('formatFactorShock uses wire unit from API', () => {
  assert.equal(formatFactorShock({ required_shock: -0.14, shock_unit: 'relative' }), '-14.0%')
  assert.equal(formatFactorShock({ required_shock: 125, shock_unit: 'bp' }), '125 bp')
  assert.equal(formatFactorShock(null), '—')
})

test('attributionSummary passes M4.3 driver labels through unchanged', () => {
  const report = {
    base_market_value: 1000,
    current_market_value: 1100,
    total_change: 100,
    explained_change: 95,
    residual: 5,
    items: [
      { driver: 'Delta', pnl: 40 },
      { driver: 'Gamma', pnl: 10 },
      { driver: 'Vega', pnl: 15 },
      { driver: 'Rates', pnl: -5 },
      { driver: 'FX', pnl: 3 },
      { driver: 'Theta', pnl: -2 },
      { driver: 'New trades', pnl: 20 },
      { driver: 'Closed trades', pnl: 14 },
    ],
  }
  const s = attributionSummary(report)
  assert.deepEqual(s.drivers, [
    'Delta', 'Gamma', 'Vega', 'Rates', 'FX', 'Theta', 'New trades', 'Closed trades',
  ])
  assert.equal(s.residual, 5)
  assert.equal(s.total_change, 100)
  assert.equal(s.explained_change, 95)
  assert.equal(s.items[0].driver, 'Delta')
  assert.equal(attributionSummary(null), null)
})

test('breachedLimits filters on API breached flag', () => {
  const items = [
    { metric: 'var_99', breached: true, utilization_pct: 110 },
    { metric: 'vega', breached: false, utilization_pct: 90 },
    { metric: 'dv01', breached: true, utilization_pct: 101 },
  ]
  assert.deepEqual(breachedLimits(items).map((x) => x.metric), ['var_99', 'dv01'])
  assert.deepEqual(breachedLimits(null), [])
  assert.deepEqual(breachedLimits([]), [])
})

test('limitDrilldownSummary passes API fields and counts breaches', () => {
  const report = {
    portfolio_id: 'p1',
    hierarchy_node: 'Multi Desk Book',
    hierarchy_level: 'portfolio',
    items: [
      {
        hierarchy_node: 'Multi Desk Book',
        hierarchy_level: 'portfolio',
        metric: 'var_99',
        value: 120,
        limit: 100,
        utilization_pct: 120,
        breached: true,
        status: 'BREACH',
        contributors: [
          { position_id: 't1', label: 'EQ Call', risk_amount: 40, contribution_pct: 50 },
        ],
      },
      {
        hierarchy_node: 'Multi Desk Book',
        hierarchy_level: 'portfolio',
        metric: 'vega',
        value: 50,
        limit: 80,
        utilization_pct: 62.5,
        breached: false,
        status: 'OK',
        contributors: [],
      },
    ],
  }
  const s = limitDrilldownSummary(report)
  assert.equal(s.portfolio_id, 'p1')
  assert.equal(s.hierarchy_node, 'Multi Desk Book')
  assert.equal(s.hierarchy_level, 'portfolio')
  assert.equal(s.breach_count, 1)
  assert.equal(s.items.length, 2)
  assert.equal(s.items[0].contributors[0].label, 'EQ Call')
  assert.equal(limitDrilldownSummary(null), null)
  assert.equal(limitDrilldownSummary({ portfolio_id: 'x' }).items.length, 0)
  assert.equal(limitDrilldownSummary({ portfolio_id: 'x' }).breach_count, 0)
})

test('riskRunStatus prefers known API statuses', () => {
  assert.equal(riskRunStatus({ status: 'QUEUED' }), 'QUEUED')
  assert.equal(riskRunStatus({ status: 'RUNNING' }), 'RUNNING')
  assert.equal(riskRunStatus({ status: 'COMPLETED' }), 'COMPLETED')
  assert.equal(riskRunStatus({ status: 'FAILED' }), 'FAILED')
  assert.equal(riskRunStatus('RUNNING'), 'RUNNING')
  assert.equal(riskRunStatus({ status: 'mystery' }), 'QUEUED')
  assert.equal(riskRunStatus(null), 'QUEUED')
})

test('riskRunStatusClass lowercases status for CSS', () => {
  assert.equal(riskRunStatusClass({ status: 'QUEUED' }), 'queued')
  assert.equal(riskRunStatusClass({ status: 'RUNNING' }), 'running')
  assert.equal(riskRunStatusClass({ status: 'COMPLETED' }), 'completed')
  assert.equal(riskRunStatusClass({ status: 'FAILED' }), 'failed')
})

test('isRiskRunTerminal stops poll on COMPLETED / FAILED', () => {
  assert.equal(isRiskRunTerminal({ status: 'QUEUED' }), false)
  assert.equal(isRiskRunTerminal({ status: 'RUNNING' }), false)
  assert.equal(isRiskRunTerminal({ status: 'COMPLETED' }), true)
  assert.equal(isRiskRunTerminal({ status: 'FAILED' }), true)
  assert.equal(isRiskRunTerminal('COMPLETED'), true)
  assert.equal(RISK_RUN_POLL_MS, 500)
})

test('riskRunSummary passes RiskRunView fields through (no risk math)', () => {
  const run = {
    id: 'run-1',
    portfolio_id: 'demo',
    status: 'COMPLETED',
    run_type: 'summary',
    error_message: null,
    created_at: '2026-09-02T17:00:00+00:00',
    started_at: '2026-09-02T17:00:01+00:00',
    finished_at: '2026-09-02T17:00:02+00:00',
    duration_seconds: 1.25,
    results: [{ result_type: 'summary', payload: { var_99: 100 } }],
  }
  const s = riskRunSummary(run)
  assert.equal(s.id, 'run-1')
  assert.equal(s.status, 'COMPLETED')
  assert.equal(s.run_type, 'summary')
  assert.equal(s.duration_seconds, 1.25)
  assert.equal(s.result_count, 1)
  assert.deepEqual(s.result_types, ['summary'])
  assert.equal(s.error_message, null)
  assert.equal(riskRunSummary(null), null)
  assert.equal(riskRunSummary({ id: 'x', status: 'FAILED', run_type: 'var', error_message: 'boom', results: [] }).error_message, 'boom')
  assert.equal(riskRunSummary({ id: 'x', status: 'QUEUED', run_type: 'var' }).result_count, 0)
})

test('ratesShowcaseSummary passes API curve nodes and KR-DV01 (no risk math)', () => {
  const payload = {
    portfolio_id: 'rates-macro',
    market_snapshot_id: 'demo:rates-macro',
    conventions: {
      shock_unit: '1bp = 1e-4 decimal',
      sensitivity_unit: 'currency P&L per +1bp',
      limitations: 'Demo OIS/SOFR-style zeros; not a production multi-curve framework.',
    },
    discount_curve: {
      name: 'USD_OIS',
      currency: 'USD',
      curve_type: 'discount',
      nodes: [
        { tenor: '2Y', years: 2, zero_rate: 0.043 },
        { tenor: '5Y', years: 5, zero_rate: 0.041 },
        { tenor: '10Y', years: 10, zero_rate: 0.0415 },
      ],
    },
    parallel_dv01: -1200.5,
    key_rate_dv01: [
      { tenor: '2Y', value: -200, unit: 'per_bp' },
      { tenor: '5Y', value: -400, unit: 'per_bp' },
      { tenor: '10Y', value: -500, unit: 'per_bp' },
    ],
  }
  const s = ratesShowcaseSummary(payload)
  assert.equal(s.portfolio_id, 'rates-macro')
  assert.equal(s.market_snapshot_id, 'demo:rates-macro')
  assert.deepEqual(s.nodes.map((n) => n.tenor), ['2Y', '5Y', '10Y'])
  assert.equal(s.nodes[0].zero_rate, 0.043)
  assert.equal(s.parallel_dv01, -1200.5)
  assert.equal(s.key_rate_dv01[0].value, -200)
  assert.equal(s.conventions.shock_unit, '1bp = 1e-4 decimal')
  assert.equal(ratesShowcaseSummary(null), null)
})

test('runProvenanceSummary displays backend lineage fields only (no invented SHA)', () => {
  const payload = {
    risk_run_id: 'run-9',
    portfolio_id: 'rates-macro',
    portfolio_version: 1,
    market_snapshot_id: 'demo:rates-macro',
    as_of: 'current',
    historical_dataset_id: 'demo-multi-factor-history',
    historical_dataset_version: 'v1',
    pricing_engine_version: 'builtin-0.3.0',
    methodology: 'DELTA_GAMMA',
    scenario_set: ['rates-steepener'],
    calculation_config: { observations: 50, seed: 7 },
    duration_seconds: 1.5,
    status: 'COMPLETED',
  }
  const s = runProvenanceSummary(payload)
  assert.equal(s.risk_run_id, 'run-9')
  assert.equal(s.portfolio_id, 'rates-macro')
  assert.equal(s.portfolio_version, 1)
  assert.equal(s.historical_dataset_id, 'demo-multi-factor-history')
  assert.equal(s.historical_dataset_version, 'v1')
  assert.equal(s.pricing_engine_version, 'builtin-0.3.0')
  assert.equal(s.methodology, 'DELTA_GAMMA')
  assert.deepEqual(s.scenario_set, ['rates-steepener'])
  assert.equal(s.duration_seconds, 1.5)
  assert.equal(s.status, 'COMPLETED')
  assert.equal(s.release_sha, null)
  assert.equal(runProvenanceSummary({ ...payload, release_sha: 'abc123' }).release_sha, 'abc123')
  assert.equal(runProvenanceSummary(null), null)
})

test('spyScaledPortfolio scales SPY equity qty only (request helper)', () => {
  const portfolio = {
    id: 'demo',
    positions: [
      { id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 },
      { id: 'opt-1', type: 'equity_option', symbol: 'SPY', quantity: 10 },
      { id: 'eq-2', type: 'equity', symbol: 'QQQ', quantity: 50 },
    ],
  }
  const scaled = spyScaledPortfolio(portfolio, 1.5)
  assert.equal(scaled.positions[0].quantity, 150)
  assert.equal(scaled.positions[1].quantity, 10)
  assert.equal(scaled.positions[2].quantity, 50)
  assert.equal(portfolio.positions[0].quantity, 100)
  assert.equal(spyScaledPortfolio(null), null)
})

test('demoChangeAttributionRequest builds previous→SPY×scale current', () => {
  const portfolio = {
    id: 'demo',
    positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
  }
  const req = demoChangeAttributionRequest(portfolio, {
    metric: 'expected_shortfall_99',
    methodology: 'LINEAR',
    scale: 2,
  })
  assert.equal(req.previous_portfolio, portfolio)
  assert.equal(req.current_portfolio.positions[0].quantity, 200)
  assert.equal(req.metric, 'expected_shortfall_99')
  assert.equal(req.methodology, 'LINEAR')
  assert.equal(demoChangeAttributionRequest(null), null)
  assert.equal(demoChangeAttributionRequest(portfolio).metric, 'var_99')
  assert.equal(demoChangeAttributionRequest(portfolio).methodology, 'DELTA_GAMMA')
})

test('riskChangeAttributionSummary passes drivers / delta_risk through', () => {
  const report = {
    metric: 'var_99',
    previous_risk: 100,
    current_risk: 130,
    total_change: 30,
    explained_change: 28,
    residual: 2,
    items: [
      { driver: 'New trades', delta_risk: 20 },
      { driver: 'Equity moves', delta_risk: 8 },
      { driver: 'Correlation / residual', delta_risk: 2 },
    ],
  }
  const s = riskChangeAttributionSummary(report)
  assert.equal(s.metric, 'var_99')
  assert.equal(s.total_change, 30)
  assert.equal(s.residual, 2)
  assert.deepEqual(s.drivers, ['New trades', 'Equity moves', 'Correlation / residual'])
  assert.equal(s.items[0].delta_risk, 20)
  assert.equal(riskChangeAttributionSummary(null), null)
})

test('riskChangeReportSummary passes run identity / contributors / residual through', () => {
  const report = {
    t0_run_id: 'run-t0',
    t1_run_id: 'run-t1',
    metric: 'var_99',
    unit: 'currency loss',
    sign_convention: 'positive total_change means the selected metric increased',
    previous_risk: 100,
    current_risk: 140,
    total_change: 40,
    portfolio_trade_change: 25,
    market_change: 14,
    explained_change: 39,
    residual: 1,
    residual_name: 'residual / interactions',
    disclosed_changes: ['methodology'],
    identity: {
      changed_fields: ['methodology'],
      t0: { run_id: 'run-t0', portfolio_id: 'demo', portfolio_version: 1 },
      t1: { run_id: 'run-t1', portfolio_id: 'demo', portfolio_version: 2 },
    },
    factor_contributors: [{ factor_id: 'EquitySpot:SPY', factor_type: 'equity', factor: 'SPY', bucket: 'SPY', delta_risk: 14 }],
    hierarchy_contributors: [{ level: 'trade', name: 'eq-spy', path: 'RiskForge/Global Macro/Equity/eq-spy', position_id: 'eq-spy', delta_risk: 25, children: [] }],
    items: [{ driver: 'Position changes', delta_risk: 25 }],
  }
  const s = riskChangeReportSummary(report)
  assert.equal(s.t0_run_id, 'run-t0')
  assert.equal(s.t1_run_id, 'run-t1')
  assert.equal(s.total_change, 40)
  assert.equal(s.residual, 1)
  assert.equal(s.unit, 'currency loss')
  assert.equal(s.factor_contributors[0].factor_id, 'EquitySpot:SPY')
  assert.equal(s.hierarchy_contributors[0].delta_risk, 25)
  assert.deepEqual(s.disclosed_changes, ['methodology'])
  assert.equal(riskChangeReportSummary(null), null)
})

test('esContributionSummary slices dimension and recon error', () => {
  const report = {
    portfolio_id: 'demo',
    methodology: 'DELTA_GAMMA',
    confidence: 0.99,
    portfolio_var: 100,
    portfolio_es: 140,
    by_position: [
      { key: 'a', label: 'A', component_es: 80, contribution_pct: 57.1 },
      { key: 'b', label: 'B', component_es: 60, contribution_pct: 42.9 },
    ],
    by_book: [{ key: 'Equity', label: 'Equity', component_es: 140, contribution_pct: 100 }],
    by_strategy: [],
    by_desk: [],
    by_risk_factor: [{ key: 'equity', label: 'Equity', component_es: 120, contribution_pct: 85.7 }],
    reconciliation_error_position: 0.01,
    reconciliation_error_book: 0,
    reconciliation_error_strategy: 0,
    reconciliation_error_desk: 0,
    reconciliation_error_risk_factor: 0.5,
  }
  const pos = esContributionSummary(report, 'by_position', 1)
  assert.equal(pos.dimension, 'by_position')
  assert.equal(pos.items.length, 1)
  assert.equal(pos.item_count, 2)
  assert.equal(pos.portfolio_es, 140)
  assert.equal(pos.reconciliation_error, 0.01)
  const factor = esContributionSummary(report, 'by_risk_factor')
  assert.equal(factor.items[0].key, 'equity')
  assert.equal(factor.reconciliation_error, 0.5)
  assert.equal(esContributionSummary(null), null)
  assert.equal(esContributionSummary(report, 'bogus').dimension, 'by_position')
  assert.ok(ES_CONTRIBUTION_DIMENSIONS.includes('by_desk'))
})

test('varCompareSummary passes methodology rows through', () => {
  const report = {
    portfolio_id: 'demo',
    observations: 40,
    results: [
      { methodology: 'LINEAR', var_95: 10, var_99: 15, expected_shortfall_99: 20, runtime_ms: 1.2 },
      { methodology: 'DELTA_GAMMA', var_95: 11, var_99: 16, expected_shortfall_99: 21, runtime_ms: 1.5 },
      { methodology: 'FULL_REVALUATION', var_95: 12, var_99: 17, expected_shortfall_99: 22, runtime_ms: 8 },
    ],
  }
  const s = varCompareSummary(report)
  assert.equal(s.portfolio_id, 'demo')
  assert.equal(s.observations, 40)
  assert.equal(s.results.length, 3)
  assert.equal(s.results[2].methodology, 'FULL_REVALUATION')
  assert.equal(varCompareSummary(null), null)
  assert.equal(varCompareSummary({ portfolio_id: 'x' }).results.length, 0)
})

test('hierarchyNodeAtPath drills by child indices', () => {
  const at = hierarchyNodeAtPath(firmTree, [0, 0])
  assert.equal(at.node.level, 'desk')
  assert.equal(at.node.name, 'Rates Desk')
  assert.equal(at.trail.length, 3)
  assert.deepEqual(at.pathIndices, [0, 0])
  assert.equal(hierarchyNodeAtPath(firmTree, [0, 9]).pathIndices.length, 1)
  assert.equal(hierarchyNodeAtPath(null), null)
})

test('hierarchyChildRows and hierarchyNodeMetrics are display-only', () => {
  const rows = hierarchyChildRows(firmTree)
  assert.equal(rows.length, 1)
  assert.equal(rows[0].name, 'Multi Desk Book')
  assert.equal(rows[0].level, 'portfolio')
  const m = hierarchyNodeMetrics(firmTree)
  assert.equal(m.name, 'Acme Capital')
  assert.equal(m.var_99, 100)
  assert.equal(m.child_count, 1)
  assert.equal(hierarchyNodeMetrics(null), null)
  assert.deepEqual(hierarchyChildRows(null), [])
})

test('scenario presets and validation', () => {
  assert.ok(SCENARIO_PRESETS.length >= 4)
  const form = defaultScenarioForm()
  assert.equal(validateScenarioForm(form).ok, true)
  assert.equal(validateScenarioForm({ ...form, name: '' }).ok, false)
  assert.equal(validateScenarioForm({ ...form, limit: 0 }).ok, false)
  assert.equal(validateScenarioForm({ ...form, equity: 'x' }).ok, false)
  const crash = SCENARIO_PRESETS.find((p) => p.id === 'equity_crash')
  const payload = scenarioPayload(crash.form)
  assert.equal(payload.category, 'custom')
  assert.ok(payload.shocks.some((s) => s.factor_type === 'equity' && s.amount === -0.2))
  assert.ok(payload.shocks.some((s) => s.factor_type === 'vol' && s.amount === 0.5))
})

test('overviewKpis and overviewCollage use API teasers', () => {
  const summary = { market_value: 1e6, var_99: 50_000, expected_shortfall_99: 70_000 }
  const threats = { severe_count: 1, breach_count: 2, evaluations: [{ scenario: 'Crash', loss: 12_000 }] }
  const k = overviewKpis(summary, threats)
  assert.equal(k.var_99, 50_000)
  assert.equal(k.threat_breaches, 2)
  assert.equal(k.worst_threat_name, 'Crash')
  const cards = overviewCollage({
    summary,
    threats,
    limits: [
      { metric: 'var_99', status: 'BREACH', breached: true, utilization_pct: 110 },
      { metric: 'vega', status: 'OK', breached: false, utilization_pct: 40 },
    ],
    hierarchy: firmTree,
    stress: [{ scenario: 'A', pnl: -9 }, { scenario: 'B', pnl: -2 }],
    factors: [{ factor: 'SPX', exposure: -100, factor_type: 'equity', bucket: 'spot' }],
  })
  assert.equal(cards.length, 8)
  assert.equal(cards[0].id, 'portfolio')
  assert.match(cards[0].teaser, /desks/)
  assert.match(cards[6].teaser, /1 breach/)
  assert.equal(cards[2].id, 'var-es')
})

test('limitStatusCounts tallies OK/WARNING/BREACH', () => {
  const counts = limitStatusCounts([
    { status: 'OK' },
    { status: 'WARNING' },
    { status: 'BREACH' },
    { status: 'BREACH' },
  ])
  assert.deepEqual(counts, { OK: 1, WARNING: 1, BREACH: 2 })
  assert.deepEqual(limitStatusCounts(null), { OK: 0, WARNING: 0, BREACH: 0 })
})

test('demoPnLAttributionRequest builds AttributionRequest body', () => {
  const portfolio = {
    id: 'demo',
    name: 'Demo',
    positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
  }
  const req = demoPnLAttributionRequest(portfolio, { scale: 2, dt_years: 0.01 })
  assert.equal(req.previous_portfolio, portfolio)
  assert.equal(req.current_portfolio.positions[0].quantity, 200)
  assert.equal(req.dt_years, 0.01)
  assert.equal(demoPnLAttributionRequest(null), null)
})
