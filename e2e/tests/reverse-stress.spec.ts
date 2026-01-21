import { expect, test } from '@playwright/test'

test.describe('Reverse Stress', () => {
  test('solves for required equity shock', async ({ page }) => {
    await page.goto('/#stress')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'Reverse Stress' }) })
    await expect(card).toBeVisible()

    await card.locator('select').selectOption('equity')
    await card.locator('input[type="number"]').fill('5')
    await card.getByRole('button', { name: 'Solve' }).click()

    await expect(card.getByText(/Required equity shock:/)).toBeVisible()
  })

  test('multi-factor panel shows labels and solve status', async ({ page }) => {
    await page.goto('/#stress')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.getByTestId('reverse-stress-multi')
    await expect(card).toBeVisible()
    await expect(card.getByRole('heading', { name: 'Multi-Factor Reverse Stress' })).toBeVisible()
    await expect(card.getByText(/No multi-factor reverse run yet/i)).toBeVisible()
    await expect(card.getByLabel('factor equity')).toBeChecked()
    await expect(card.getByLabel('factor vol')).toBeChecked()
    await expect(card.getByRole('button', { name: 'Solve multi-factor' })).toBeVisible()

    await card.getByRole('button', { name: 'Solve multi-factor' }).click()

    const result = card.locator('.reverse-multi-result')
    await expect(result).toBeVisible({ timeout: 45_000 })
    await expect(result.getByText(/Converged|Not converged/)).toBeVisible()
    await expect(result.getByText('Target')).toBeVisible()
    await expect(result.getByText('Achieved')).toBeVisible()
    await expect(result.getByRole('columnheader', { name: 'Factor' })).toBeVisible()
    await expect(result.getByRole('columnheader', { name: 'Required shock' })).toBeVisible()
    await expect(card.locator('.error')).toHaveCount(0)
  })
})
