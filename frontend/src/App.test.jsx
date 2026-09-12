import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import App from './App.jsx'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    loadDashboard: vi.fn(),
  }
})

import { loadDashboard } from './api'

describe('App market-data gate', () => {
  it('renders Market Data when dashboard load failed', async () => {
    window.location.hash = '#market-data'
    loadDashboard.mockRejectedValue(new Error('dashboard down'))
    render(<App />)
    expect(await screen.findByLabelText(/instrument search/i)).toBeInTheDocument()
    expect(screen.queryByText(/API error/i)).not.toBeInTheDocument()
  })

  it('renders Market Data while dashboard load is pending', async () => {
    window.location.hash = '#market-data'
    loadDashboard.mockReturnValue(new Promise(() => {}))
    render(<App />)
    await waitFor(() => expect(screen.getByLabelText(/instrument search/i)).toBeInTheDocument())
    expect(screen.queryByText(/Loading portfolio risk/i)).not.toBeInTheDocument()
  })
})
