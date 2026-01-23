import { expect, test } from '@playwright/test'

/**
 * M9.10 — E2E breadth for Milestone 8 panels that call post-M2/M3/M4 APIs.
 * Asserts UI → live API → rendered results (no client-side risk math).
 * Multi-factor reverse stress live E2E: `e2e/tests/reverse-stress.spec.ts`
 * (fill controls + Converged/Not converged status — no invented PnL numbers).
 */

test.describe('M8 VaR & ES panels', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/#var-es')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'VaR & ES' })).toBeVisible()
  })

  test('loads ES contributions from POST /risk/es', async ({ page }) => {
    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'ES Contributions' }) })
    await expect(card).toBeVisible()

    await card.getByLabel('es methodology').selectOption('DELTA_GAMMA')
    await card.getByRole('button', { name: 'Load ES' }).click()

    const result = card.locator('.risk-panel-result')
    await expect(result).toBeVisible({ timeout: 30_000 })
    await expect(result.getByText('99% VaR')).toBeVisible()
    await expect(result.getByText('99% ES')).toBeVisible()
    await expect(result.locator('table tbody tr')).not.toHaveCount(0)
    await expect(card.getByText('API error')).toHaveCount(0)
    await expect(card.locator('.error')).toHaveCount(0)
  })

  test('runs risk change attribution waterfall', async ({ page }) => {
    const card = page.locator('.card', {
      has: page.getByRole('heading', { name: 'Risk Change Attribution' }),
    })
    await expect(card).toBeVisible()

    await card.getByLabel('change attribution metric').selectOption('var_99')
    await card.getByRole('button', { name: 'Run attribution' }).click()

    const result = card.locator('.risk-panel-result')
    await expect(result).toBeVisible({ timeout: 30_000 })
    await expect(result.locator('.attribution-total')).toContainText('Residual')
    await expect(result.locator('table tbody tr')).not.toHaveCount(0)
    await expect(card.locator('.error')).toHaveCount(0)
  })

  test('compares VaR methodologies side-by-side', async ({ page }) => {
    const card = page.locator('.card', {
      has: page.getByRole('heading', { name: 'VaR Methodology Compare' }),
    })
    await expect(card).toBeVisible()

    await card.getByLabel('var compare observations').fill('64')
    await card.getByRole('button', { name: 'Compare methods' }).click()

    const result = card.locator('.risk-panel-result')
    await expect(result).toBeVisible({ timeout: 45_000 })
    await expect(result.getByText(/64 observations/)).toBeVisible()
    await expect(result.getByText('LINEAR')).toBeVisible()
    await expect(result.getByText('DELTA_GAMMA')).toBeVisible()
    await expect(result.getByText('FULL_REVALUATION')).toBeVisible()
    await expect(card.locator('.error')).toHaveCount(0)
  })
})

test.describe('M8 Hedge Compare', () => {
  test('compares base vs SPY-flat hedge via stress/compare', async ({ page }) => {
    await page.goto('/#scenario-builder')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'Hedge Compare' }) })
    await expect(card).toBeVisible()

    await card.getByLabel('hedge methodology').selectOption('DELTA_GAMMA')
    await card.getByRole('button', { name: 'Compare hedge' }).click()

    const result = card.locator('.hedge-compare-result')
    await expect(result).toBeVisible({ timeout: 45_000 })
    await expect(result.getByText('Hedge cost')).toBeVisible()
    await expect(result.getByText(/99% VaR/)).toBeVisible()
    await expect(result.getByText(/99% ES/)).toBeVisible()
    await expect(result.locator('table tbody tr')).not.toHaveCount(0)
    await expect(card.locator('.error')).toHaveCount(0)
  })
})

test.describe('M8 Overview collage', () => {
  test('KPI strip and collage navigate to VaR & ES', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()

    const metrics = page.locator('section.metrics')
    await expect(metrics.getByText('Market Value', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% Expected Shortfall', { exact: true })).toBeVisible()

    const collage = page.locator('.overview-collage')
    await expect(collage.getByRole('heading', { name: 'Terminal map' })).toBeVisible()
    await collage.getByRole('button', { name: /VaR & ES/ }).click()

    await expect(page.getByRole('heading', { name: 'VaR & ES' })).toBeVisible()
    await expect(page.locator('.card', { has: page.getByRole('heading', { name: 'ES Contributions' }) }))
      .toBeVisible()
  })
})
