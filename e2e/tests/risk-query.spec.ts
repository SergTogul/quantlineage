import { expect, test } from '@playwright/test'

test.describe('Risk Query', () => {
  test('answers the worst-stress question via deterministic routing', async ({ page }) => {
    await page.goto('/#risk-query')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.getByTestId('golden-demo-risk-query')
    await expect(card).toBeVisible()

    await card.locator('.query input').fill('What is the worst stress scenario?')
    await card.getByRole('button', { name: 'Ask' }).click()

    const answer = card.locator('.query-answer')
    await expect(answer).toBeVisible({ timeout: 30_000 })
    await expect(card.getByTestId('risk-query-waiting')).toHaveCount(0)
    await expect(answer).toContainText(/Worst stress scenario/i)
  })
})
