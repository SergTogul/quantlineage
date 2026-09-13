import { expect, test } from '@playwright/test'

/**
 * Stage 10.4 — Golden institutional demo journey (5–8 min story).
 *
 * Asserts UI → API → rendered results only. Does not invent or pin dollar VaR/ES.
 * Flagship path is POST /api/v1/risk/runs/compare (Compare T0/T1). Provenance is
 * GET /api/v1/risk/runs/{id} fields (Task 5 panel if present; no second schema).
 */

const MAIN = { name: 'Main' }

function isPostPath(url: string, method: string, pathname: string) {
  return method === 'POST' && new URL(url).pathname === pathname
}

test.describe('Stage 10.4 golden institutional demo', () => {
  test('catalog → VaR/ES/Greeks → hierarchy → stress → compare T0/T1 → hedge → provenance → limits', async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000)

    const catalog = await request.get('http://127.0.0.1:8000/api/v1/portfolios')
    expect(catalog.ok()).toBeTruthy()
    const books = await catalog.json()
    const ids = books.map((b: { id: string }) => b.id)
    expect(ids).toEqual(expect.arrayContaining(['global-macro', 'equity-vol', 'rates-macro']))

    const dashboardBatch = page.waitForResponse(
      (res) => isPostPath(res.url(), res.request().method(), '/api/v1/risk/dashboard') && res.ok(),
    )
    await page.goto('/')
    await dashboardBatch
    await expect(page.getByText('Loading portfolio risk')).toHaveCount(0)
    await expect(page.getByText('API error')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

    const metrics = page.getByTestId('golden-demo-metrics')
    await expect(metrics).toBeVisible()
    await expect(metrics.getByText('Market Value', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% VaR', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% Expected Shortfall', { exact: true })).toBeVisible()
    await expect(metrics.locator('strong').first()).toHaveText(/\$/)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Portfolio/ }).click()
    const hierarchy = page.getByTestId('golden-demo-hierarchy')
    await expect(hierarchy).toBeVisible()
    await expect(hierarchy.getByRole('heading', { name: 'Portfolio Hierarchy' })).toBeVisible()
    await expect(hierarchy.getByText(/DV01/)).toBeVisible()
    await expect(hierarchy.locator('.hierarchy-children tbody tr')).not.toHaveCount(0)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /VaR & ES/ }).click()
    await expect(page.getByRole('heading', { name: 'VaR & ES' })).toBeVisible()
    const varEs = page.getByTestId('golden-demo-var-es')
    await expect(varEs).toBeVisible()
    await expect(varEs.getByText('99% VaR')).toBeVisible()
    const contributors = page.getByTestId('golden-demo-contributors')
    await expect(contributors).toBeVisible()
    await expect(contributors.locator('table tbody tr')).not.toHaveCount(0)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Stress/ }).click()
    const stress = page.getByTestId('golden-demo-stress')
    await expect(stress).toBeVisible()
    await expect(stress.getByRole('heading', { name: 'Stress Tests' })).toBeVisible()
    await expect(stress.locator('table tbody tr')).not.toHaveCount(0)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Scenario Builder/ }).click()
    const query = page.getByTestId('golden-demo-risk-query')
    await expect(query).toBeVisible()
    await query.locator('.query input').fill('Why did my risk change?')
    await query.getByRole('button', { name: 'Ask' }).click()
    const answer = query.locator('.query-answer')
    await expect(answer).toBeVisible()
    await expect(answer).toContainText(/RiskRun/i)
    await expect(answer).not.toContainText(/\$\d/)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /VaR & ES/ }).click()
    const change = page.getByTestId('golden-demo-risk-change')
    await expect(change).toBeVisible()
    await expect(change.getByText(/Why did my risk change/i)).toBeVisible()

    const compareRequest = page.waitForRequest((req) =>
      isPostPath(req.url(), req.method(), '/api/v1/risk/runs/compare'),
    )
    const compareResponse = page.waitForResponse(
      (res) =>
        isPostPath(res.url(), res.request().method(), '/api/v1/risk/runs/compare') && res.ok(),
    )
    await change.getByRole('button', { name: 'Compare T0/T1' }).click()
    const comparePost = await compareRequest
    const compareRes = await compareResponse
    const compareBody = comparePost.postDataJSON()
    expect(compareBody.t0_run_id).toBeTruthy()
    expect(compareBody.t1_run_id).toBeTruthy()
    expect(compareBody.t0_run_id).not.toBe(compareBody.t1_run_id)

    const report = await compareRes.json()
    expect(report.t0_run_id).toBe(compareBody.t0_run_id)
    expect(report.t1_run_id).toBe(compareBody.t1_run_id)
    expect(report.total_change).not.toBe(0)
    expect(typeof report.portfolio_trade_change).toBe('number')
    expect(typeof report.market_change).toBe('number')
    expect(typeof report.residual).toBe('number')
    const explained =
      Number(report.portfolio_trade_change) + Number(report.market_change) + Number(report.residual)
    expect(Math.abs(explained - Number(report.total_change))).toBeLessThan(1e-4)

    const flagship = change.getByTestId('golden-demo-risk-change-result')
    await expect(flagship).toBeVisible({ timeout: 120_000 })
    await expect(flagship.getByTestId('risk-change-waterfall')).toBeVisible()
    await expect(flagship.getByTestId('waterfall-step-portfolio')).toBeVisible()
    await expect(flagship.getByTestId('waterfall-step-market')).toBeVisible()
    await expect(flagship.getByTestId('waterfall-step-residual')).toBeVisible()
    await expect(flagship.getByText('Market snapshot')).toBeVisible()
    await expect(flagship.locator('table tbody tr')).not.toHaveCount(0)
    await expect(change.locator('.error')).toHaveCount(0)

    const t0Href = await flagship.getByRole('link').first().getAttribute('href')
    expect(t0Href).toMatch(/\/api\/v1\/risk\/runs\//)
    const t0Res = await request.get(`http://127.0.0.1:8000${t0Href}`)
    expect(t0Res.ok()).toBeTruthy()
    const t0 = await t0Res.json()
    expect(t0.id).toBe(compareBody.t0_run_id)
    expect(t0.status).toBe('COMPLETED')
    expect(t0.historical_dataset_id).toBeTruthy()
    expect(t0.portfolio_id).toBeTruthy()

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Risk Runs/ }).click()
    const runs = page.getByTestId('golden-demo-risk-runs')
    await expect(runs).toBeVisible()
    await runs.getByRole('button', { name: 'Start run' }).click()
    await expect(runs.locator('.status')).toHaveText(/^(COMPLETED|FAILED)$/, { timeout: 45_000 })
    const provenancePanel = page.getByTestId('golden-demo-provenance')
    await expect(provenancePanel).toBeVisible()
    await expect(provenancePanel.getByRole('heading', { name: 'Calculation provenance' })).toBeVisible()
    await expect(provenancePanel.getByRole('cell', { name: 'Dataset', exact: true })).toBeVisible()
    if (t0.historical_dataset_id) {
      await expect(provenancePanel).toContainText(String(t0.historical_dataset_id))
    }

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /Scenario Builder/ }).click()
    const hedge = page.getByTestId('golden-demo-hedge')
    await expect(hedge).toBeVisible()
    await hedge.getByLabel('hedge methodology').selectOption('DELTA_GAMMA')
    const hedgeResponse = page.waitForResponse(
      (res) =>
        isPostPath(res.url(), res.request().method(), '/api/v1/risk/stress/formal/compare') &&
        res.ok(),
    )
    await hedge.getByRole('button', { name: 'Compare hedge' }).click()
    const hedgeJson = await (await hedgeResponse).json()
    expect(hedgeJson.base_var_99).not.toBe(hedgeJson.hedged_var_99)
    expect(hedgeJson.var_improvement).not.toBe(0)

    const hedgeResult = hedge.getByTestId('golden-demo-hedge-result')
    await expect(hedgeResult).toBeVisible({ timeout: 45_000 })
    await expect(hedgeResult.getByText(/99% VaR/)).toBeVisible()
    await expect(hedge.locator('.error')).toHaveCount(0)

    await page.getByRole('navigation', MAIN).getByRole('button', { name: /VaR & ES/ }).click()
    const helpBtn = change.getByRole('button', { name: 'About this block' })
    await helpBtn.click()
    const help = change.locator('.block-help-popover')
    await expect(help).toBeVisible()
    await expect(help).toContainText(/backend payload|does not compute risk|synthetic/i)
  })
})
