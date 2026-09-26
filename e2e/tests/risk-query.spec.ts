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

  test('keeps conversation_id across two deterministic Risk Query turns', async ({ page }) => {
    await page.goto('/#risk-query')
    await expect(page.getByRole('heading', { name: 'Global Macro Demo' })).toBeVisible()

    const card = page.getByTestId('golden-demo-risk-query')
    await expect(card).toBeVisible()

    const posts: Array<{
      question?: string
      conversation_id?: string
      conversationFromResponse?: string
    }> = []
    page.on('response', async (res) => {
      if (res.request().method() !== 'POST' || !res.url().includes('/risk/query') || !res.ok()) {
        return
      }
      const reqBody = res.request().postDataJSON() as {
        question?: string
        conversation_id?: string
      } | null
      const json = await res.json()
      posts.push({
        question: reqBody?.question,
        conversation_id: reqBody?.conversation_id,
        conversationFromResponse: json?.data?.conversation_id,
      })
    })

    await card.locator('.query input').fill('What is the worst stress scenario?')
    await card.getByRole('button', { name: 'Ask' }).click()
    const transcript = card.getByTestId('risk-query-transcript')
    await expect(transcript).toBeVisible({ timeout: 30_000 })
    await expect(transcript).toContainText(/Worst stress scenario/i)
    await expect(card.getByTestId('risk-query-waiting')).toHaveCount(0)

    await card.locator('.query input').fill('What is 99% VaR?')
    await card.getByRole('button', { name: 'Ask' }).click()
    await expect(transcript).toContainText(/VaR/i, { timeout: 30_000 })
    await expect(transcript.locator('.risk-query-turn-user')).toHaveCount(2)
    await expect(transcript.locator('.risk-query-turn-assistant')).toHaveCount(2)
    await expect(transcript).toContainText('What is the worst stress scenario?')
    await expect(transcript).toContainText('What is 99% VaR?')
    await expect(card.getByTestId('risk-query-waiting')).toHaveCount(0)

    await expect.poll(() => posts.length).toBe(2)
    expect(posts[0].conversation_id).toBeFalsy()
    expect(posts[0].conversationFromResponse).toMatch(/^conv_/)
    expect(posts[1].conversation_id).toBe(posts[0].conversationFromResponse)
    expect(JSON.stringify(posts)).not.toMatch(/OPENAI_API[_-]KEY/)
  })
})
