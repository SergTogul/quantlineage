import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import MetricCard from './MetricCard.jsx'

describe('MetricCard', () => {
  it('renders label and value without transforming numbers', () => {
    render(<MetricCard label="99% VaR" value="$50.0K" />)
    expect(screen.getByText('99% VaR')).toBeInTheDocument()
    expect(screen.getByText('$50.0K')).toBeInTheDocument()
  })
})
