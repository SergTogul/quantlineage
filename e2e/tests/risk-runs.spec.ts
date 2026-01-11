import { expect, test } from '@playwright/test'

test.describe('Risk Runs', () => {
  test('starts a run and shows COMPLETED or FAILED status', async ({ page }) => {
    // M8.9: Risk Runs lives on its own hash section (not Overview).
    await page.goto('/#risk-runs')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()
    await expect(page.locator('#risk-runs-heading')).toBeVisible()

    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'Risk Runs', level: 3 }) })
    await expect(card).toBeVisible()

    await card.getByLabel('run type').selectOption('summary')
    await card.getByRole('button', { name: 'Start run' }).click()

    const status = card.locator('.risk-run-status .status')
    await expect(status).toBeVisible()
    // Poll UI until terminal; allow worker + GET poll cycle under builtin engine.
    await expect(status).toHaveText(/^(COMPLETED|FAILED)$/, { timeout: 45_000 })
  })
})
