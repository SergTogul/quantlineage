import { expect, test } from '@playwright/test'

test.describe('Reverse Stress', () => {
  test('solves for required equity shock', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'Reverse Stress' }) })
    await expect(card).toBeVisible()

    await card.locator('select').selectOption('equity')
    await card.locator('input[type="number"]').fill('5')
    await card.getByRole('button', { name: 'Solve' }).click()

    await expect(card.getByText(/Required equity shock:/)).toBeVisible()
  })
})
