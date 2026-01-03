import { expect, test } from '@playwright/test'

test.describe('Scenario Builder', () => {
  test('runs a custom scenario and shows loss result', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'Scenario Builder' }) })
    await expect(card).toBeVisible()

    await card.getByLabel('scenario name').fill('E2E Crash')
    await card.getByRole('button', { name: 'Run scenario' }).click()

    const result = card.locator('.scenario-result')
    await expect(result).toBeVisible()
    await expect(result.getByText('E2E Crash')).toBeVisible()
    await expect(result.getByText(/Loss/)).toBeVisible()
    await expect(result.getByText(/NAV/)).toBeVisible()
    await expect(result.locator('.threat')).toBeVisible()
  })
})
