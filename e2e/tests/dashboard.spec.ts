import { expect, test } from '@playwright/test'

test.describe('Dashboard smoke', () => {
  test('loads portfolio risk terminal from the live API', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('Loading portfolio risk')).toHaveCount(0)
    await expect(page.getByText('API error')).toHaveCount(0)

    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()
    await expect(page.getByText('QUANTLINEAGE').first()).toBeVisible()
    const legacyBrand = ['RISK', 'FORGE'].join('')
    await expect(page.getByText(legacyBrand)).toHaveCount(0)
    await expect(page.getByText('AI-Powered Multi-Asset Risk & Attribution Platform')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const metrics = page.locator('section.metrics')
    await expect(metrics.getByText('Market Value', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% VaR', { exact: true })).toBeVisible()
    await expect(metrics.getByText('99% Expected Shortfall', { exact: true })).toBeVisible()

    await page.getByRole('link', { name: /Why did my risk change\?/i }).click()
    await expect(page.getByTestId('golden-demo-risk-change')).toBeVisible()
    await expect(page.locator('#var-es-risk-change')).toBeVisible()

    await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: /Historical/ }).click()
    const sharpeUnit = page.getByTestId('ha-sharpe-unit')
    await expect(sharpeUnit).toHaveText('—')
    await expect(page.getByTestId('data-source-badge')).toBeVisible()

    await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: /Scenario Builder/ }).click()
    const payload = page.getByTestId('scenario-api-payload')
    await expect(payload).toBeVisible()
    await expect(payload).not.toHaveAttribute('open')

    await page.getByRole('navigation', { name: 'Main' }).getByRole('button', { name: /Portfolio/ }).click()
    await expect(page.getByRole('heading', { name: 'Positions' })).toBeVisible()
    await expect(page.locator('#portfolio table tbody tr')).not.toHaveCount(0)
  })
})
