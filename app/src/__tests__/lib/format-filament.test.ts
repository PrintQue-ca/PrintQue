import { describe, expect, it } from 'vitest'
import { formatFilamentKg } from '@/lib/format-filament'

describe('formatFilamentKg', () => {
  it('formats zero', () => {
    expect(formatFilamentKg(0)).toBe('0 g')
  })

  it('formats sub-kilogram as grams', () => {
    expect(formatFilamentKg(0.025)).toBe('25.0 g')
    expect(formatFilamentKg(0.5)).toBe('500 g')
  })

  it('formats kilograms', () => {
    expect(formatFilamentKg(2.5)).toBe('2.50 kg')
  })
})
