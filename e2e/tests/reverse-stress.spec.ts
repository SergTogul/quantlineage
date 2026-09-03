import { expect, test } from '@playwright/test'

test.describe('Reverse Stress', () => {
  test('solves for required equity shock', async ({ page }) => {
    await page.goto('/#stress')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    // testid: multi-factor card title also contains "Reverse Stress"
    const card = page.getByTestId('reverse-stress')
    await expect(card).toBeVisible()
    await expect(card.getByRole('heading', { name: 'Reverse Stress', exact: true })).toBeVisible()

    await card.locator('select').selectOption('equity')
    await card.locator('input[type="number"]').fill('5')
    await card.getByRole('button', { name: 'Solve' }).click()

    await expect(card.getByText(/Required equity shock:/)).toBeVisible()
  })

  test('multi-factor: validates fewer than two factors', async ({ page }) => {
    await page.goto('/#stress')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.getByTestId('reverse-stress-multi')
    await expect(card).toBeVisible()

    // Defaults: equity + vol selected. Leave only equity → client validation.
    await card.getByLabel('factor vol').uncheck()
    await expect(card.getByLabel('factor equity')).toBeChecked()
    await expect(card.getByLabel('factor vol')).not.toBeChecked()

    await card.getByRole('button', { name: 'Solve multi-factor' }).click()

    await expect(card.locator('.error')).toContainText(/at least two factors/i)
    await expect(card.locator('.reverse-multi-result')).toHaveCount(0)
  })

  test('multi-factor panel fills controls and shows solve status', async ({ page }) => {
    await page.goto('/#stress')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.getByTestId('reverse-stress-multi')
    await expect(card).toBeVisible()
    await expect(card.getByRole('heading', { name: 'Multi-Factor Reverse Stress' })).toBeVisible()
    await expect(card.getByText(/No multi-factor reverse run yet/i)).toBeVisible()

    // Defaults + explicit fills (display %); add rates so ≥2 factors with a third family.
    await expect(card.getByLabel('factor equity')).toBeChecked()
    await expect(card.getByLabel('factor vol')).toBeChecked()
    await card.getByLabel('factor rates').check()
    await card.getByLabel('multi reverse target loss percent').fill('5')
    await card.getByLabel('multi reverse max shock percent').fill('80')
    await card.getByLabel('weight equity').fill('1')
    await card.getByLabel('weight vol').fill('1')
    await card.getByLabel('weight rates').fill('1')

    await card.getByRole('button', { name: 'Solve multi-factor' }).click()

    const result = card.locator('.reverse-multi-result')
    await expect(result).toBeVisible({ timeout: 45_000 })
    const totals = result.locator('.attribution-total')
    // Structural outcome only — no invented PnL / shock magnitudes.
    await expect(totals).toContainText(/Status/)
    await expect(totals.getByText(/Converged|Not converged/)).toBeVisible()
    await expect(totals).toContainText(/Target/)
    await expect(totals).toContainText(/Achieved/)
    await expect(totals).toContainText(/P&L/)
    await expect(result.getByRole('columnheader', { name: 'Factor' })).toBeVisible()
    await expect(result.getByRole('columnheader', { name: 'Required shock' })).toBeVisible()
    await expect(result.locator('table tbody tr')).not.toHaveCount(0)
    await expect(result.locator('table tbody')).toContainText('equity')
    await expect(result.locator('table tbody')).toContainText('vol')
    await expect(result.locator('table tbody')).toContainText('rates')
    await expect(card.locator('.error')).toHaveCount(0)
  })
})
