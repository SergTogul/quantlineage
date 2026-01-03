import test from 'node:test'; import assert from 'node:assert/strict'
import {
  money, topContributors, worstStress, limitStatus, limitStatusClass, percent, threatClass, stressSummary,
  topFactors, varMethod, hierarchyTradeCount, hierarchyCountByLevel, hierarchyPortfolio,
  hierarchySummary, hedgeComparisonSummary, reverseStressMultiSummary, scenarioPayload,
  attributionSummary, breachedLimits, limitDrilldownSummary,
  riskRunStatus, riskRunStatusClass, isRiskRunTerminal, riskRunSummary, RISK_RUN_POLL_MS,
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
test('scenario builder converts display units to API units',()=>{const x=scenarioPayload({name:'X',equity:-20,vol:50,rates:100,fx:-5,limit:10});assert.equal(x.equity_shock,-.2);assert.equal(x.vol_shock,.5);assert.equal(x.rates_shift_bps,100);assert.equal(x.fx_shock,-.05);assert.equal(x.max_loss_pct,.1)})

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
    scenarios: [{ scenario: 'Crash', base_pnl: -10, hedged_pnl: -5, improvement: 5 }],
    factor_exposure_changes: [{ factor: 'SPX', before: 1, after: 0.5, delta: -0.5 }],
  }
  const s = hedgeComparisonSummary(report)
  assert.equal(s.hedge_cost, 50)
  assert.equal(s.var_improvement, 12)
  assert.equal(s.scenarios.length, 1)
  assert.equal(s.factor_exposure_changes.length, 1)
})

test('hedgeComparisonSummary shims legacy list shape', () => {
  const legacy = [{ scenario: 'A', base_pnl: -1, hedged_pnl: 0, improvement: 1 }]
  const s = hedgeComparisonSummary(legacy)
  assert.equal(s.hedge_cost, null)
  assert.deepEqual(s.scenarios, legacy)
  assert.equal(hedgeComparisonSummary(null), null)
})

test('reverseStressMultiSummary parses multi-factor result', () => {
  const result = {
    converged: true,
    target_loss_pct: 0.1,
    achieved_loss_pct: 0.099,
    pnl: -500,
    shocks: [{ factor: 'equity', required_shock: -0.2, shock_unit: 'relative', weight: 1, max_shock: 0.8 }],
    factors: ['equity'],
    message: null,
  }
  const s = reverseStressMultiSummary(result)
  assert.equal(s.converged, true)
  assert.equal(s.shocks.length, 1)
  assert.equal(s.factors[0], 'equity')
  assert.equal(reverseStressMultiSummary(null), null)
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
