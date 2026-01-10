import { expect, test } from '@playwright/test'

test.describe('Dashboard smoke', () => {
  test('loads portfolio risk terminal from the live API', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('Loading portfolio risk')).toHaveCount(0)
    await expect(page.getByText('API error')).toHaveCount(0)

    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    await expect(page.getByText('RISKFORGE').first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const metrics = page.locator('section.metrics')
    await expect(metrics.getByText('Market Value', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% VaR', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% Expected Shortfall', { exact: true })).toBeVisible()

    await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: /Portfolio/ }).click()
    await expect(page.getByRole('heading', { name: 'Positions' })).toBeVisible()
    await expect(page.locator('#portfolio table tbody tr')).not.toHaveCount(0)
  })
})
