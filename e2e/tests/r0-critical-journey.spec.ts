import { expect, test } from '@playwright/test'

/**
 * R0.12.3 — Critical E2E journey against the live local API (builtin pricing).
 *
 * load demo portfolio → inspect dashboard VaR/ES → run a named custom scenario
 * → inspect contributors → SPY-flat hedge compare → verify changed risk from compare JSON.
 *
 * Asserts UI → API → rendered results only. Does not invent or pin dollar VaR/ES.
 * Request units (display % / bp → API decimal / bp) are captured where they matter.
 * Hedge change is `base_var_99 !== hedged_var_99` from POST /risk/stress/formal/compare JSON.
 */

const MAIN = { name: 'Main' }

function metricCard(page, label) {
  return page.locator('section.metrics .card.metric', {
    has: page.getByText(label, { exact: true }),
  })
}

function isPostPath(url, method, pathname) {
  return method === 'POST' && new URL(url).pathname === pathname
}

test.describe('R0.12.3 critical journey', () => {
  test('demo portfolio → VaR/ES → custom scenario → contributors → hedge compare', async ({
    page,
  }) => {
    test.setTimeout(120_000)

    const dashboardVar = page.waitForResponse(
      (res) => isPostPath(res.url(), res.request().method(), '/api/v1/risk/var') && res.ok(),
    )
    await page.goto('/')
    await dashboardVar
    await expect(page.getByText('Loading portfolio risk')).toHaveCount(0)
    await expect(page.getByText('API error')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

    const metrics = page.locator('section.metrics')
    await expect(metrics.getByText('Market Value', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% VaR', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% Expected Shortfall', { exact: true })).toBeVisible()
    await expect(metricCard(page, '99% VaR').locator('strong')).toHaveText(/\$/)
    await expect(metricCard(page, '99% Expected Shortfall').locator('strong')).toHaveText(/\$/)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Scenario Builder/ }).click()
    await expect(page.getByRole('heading', { name: 'Scenario Builder', level: 2 })).toBeVisible()

    const builder = page.locator('.card', { has: page.getByRole('heading', { name: 'Scenario Builder' }) })
    await expect(builder).toBeVisible()

    await builder.getByLabel('scenario name').fill('R0 Critical Journey')
    await builder.locator('label', { hasText: 'Equity %' }).locator('input').fill('-20')
    await builder.locator('label', { hasText: 'Rates bp' }).locator('input').fill('100')

    // Display % / bp → API decimal / bp (preview is request-unit, not a risk number).
    await expect(builder.locator('.scenario-payload-preview')).toContainText('API shocks: equity -0.2')
    await expect(builder.locator('.scenario-payload-preview')).toContainText('rates 100 bp')

    const scenarioRequest = page.waitForRequest((req) =>
      isPostPath(req.url(), req.method(), '/api/v1/risk/stress/evaluate/custom'),
    )
    const scenarioResponse = page.waitForResponse(
      (res) => isPostPath(res.url(), res.request().method(), '/api/v1/risk/stress/evaluate/custom') && res.ok(),
    )
    await builder.getByRole('button', { name: 'Run scenario' }).click()
    const scenarioPost = await scenarioRequest
    await scenarioResponse
    const scenarioBody = scenarioPost.postDataJSON()
    const custom = scenarioBody.scenarios[0]
    expect(custom.name).toBe('R0 Critical Journey')
    expect(custom.equity_shock).toBeCloseTo(-0.2, 10)
    expect(custom.vol_shock).toBeCloseTo(0.5, 10)
    expect(custom.rates_shift_bps).toBe(100)
    expect(custom.fx_shock).toBeCloseTo(-0.05, 10)
    expect(custom.max_loss_pct).toBeCloseTo(0.1, 10)

    const scenarioResult = builder.locator('.scenario-result')
    await expect(scenarioResult).toBeVisible({ timeout: 45_000 })
    await expect(scenarioResult.getByText('R0 Critical Journey')).toBeVisible()
    await expect(scenarioResult.getByText(/Loss/)).toBeVisible()
    await expect(scenarioResult.getByText(/NAV/)).toBeVisible()
    await expect(scenarioResult.locator('.threat')).toBeVisible()
    await expect(builder.locator('.error')).toHaveCount(0)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /VaR & ES/ }).click()
    await expect(page.getByRole('heading', { name: 'VaR & ES' })).toBeVisible()

    const componentVar = page.locator('.card', {
      has: page.getByRole('heading', { name: 'Component VaR Contributors' }),
    })
    await expect(componentVar).toBeVisible()
    await expect(componentVar.locator('table tbody tr')).not.toHaveCount(0)

    const esCard = page.locator('.card', { has: page.getByRole('heading', { name: 'ES Contributions' }) })
    await expect(esCard).toBeVisible()
    await esCard.getByLabel('es methodology').selectOption('DELTA_GAMMA')
    const esResponse = page.waitForResponse(
      (res) => isPostPath(res.url(), res.request().method(), '/api/v1/risk/es') && res.ok(),
    )
    await esCard.getByRole('button', { name: 'Load ES' }).click()
    await esResponse

    const esResult = esCard.locator('.risk-panel-result')
    await expect(esResult).toBeVisible({ timeout: 30_000 })
    await expect(esResult.getByText('99% VaR')).toBeVisible()
    await expect(esResult.getByText('99% ES')).toBeVisible()
    await expect(esResult.locator('table tbody tr')).not.toHaveCount(0)
    await expect(esCard.getByText('API error')).toHaveCount(0)
    await expect(esCard.locator('.error')).toHaveCount(0)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Scenario Builder/ }).click()
    await expect(page.getByRole('heading', { name: 'Scenario Builder', level: 2 })).toBeVisible()

    const hedge = page.locator('.card', { has: page.getByRole('heading', { name: 'Hedge Compare' }) })
    await expect(hedge).toBeVisible()
    await hedge.getByLabel('hedge methodology').selectOption('DELTA_GAMMA')

    const hedgeRequest = page.waitForRequest((req) =>
      isPostPath(req.url(), req.method(), '/api/v1/risk/stress/formal/compare'),
    )
    const hedgeResponse = page.waitForResponse(
      (res) =>
        isPostPath(res.url(), res.request().method(), '/api/v1/risk/stress/formal/compare') &&
        res.ok(),
    )
    await hedge.getByRole('button', { name: 'Compare hedge' }).click()
    const hedgePost = await hedgeRequest
    const hedgeRes = await hedgeResponse
    const hedgeBody = hedgePost.postDataJSON()
    expect(hedgeBody.scenarios[0].equity_shock).toBeCloseTo(-0.2, 10)
    const spyEquity = (hedgeBody.hedged_portfolio?.positions || []).find(
      (p) => p.symbol === 'SPY' && p.type === 'equity',
    )
    expect(spyEquity?.quantity).toBe(0)

    const compareJson = await hedgeRes.json()
    expect(compareJson.base_var_99, JSON.stringify({
      base_var_99: compareJson.base_var_99,
      hedged_var_99: compareJson.hedged_var_99,
      var_improvement: compareJson.var_improvement,
    })).not.toBe(compareJson.hedged_var_99)
    expect(compareJson.var_improvement).not.toBe(0)

    const hedgeResult = hedge.locator('.hedge-compare-result')
    await expect(hedgeResult).toBeVisible({ timeout: 45_000 })
    await expect(hedgeResult.getByText('Hedge cost')).toBeVisible()
    await expect(hedgeResult.getByText(/99% VaR/)).toBeVisible()
    await expect(hedgeResult.getByText(/99% ES/)).toBeVisible()
    await expect(hedgeResult.locator('table tbody tr')).not.toHaveCount(0)
    await expect(hedge.locator('.error')).toHaveCount(0)
  })
})
