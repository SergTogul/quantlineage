import { expect, test } from '@playwright/test'

test.describe('Risk Query', () => {
  test('answers the worst-stress question via deterministic routing', async ({ page }) => {
    await page.goto('/#scenario-builder')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.locator('.card', { has: page.getByRole('heading', { name: 'Risk Query' }) })
    await expect(card).toBeVisible()

    await card.locator('.query input').fill('What is the worst stress scenario?')
    await card.getByRole('button', { name: 'Ask' }).click()

    const answer = card.locator('.query-answer')
    await expect(answer).toBeVisible()
    await expect(answer).toContainText(/Worst stress scenario/i)
  })
})
