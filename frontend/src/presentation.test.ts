import { describe, expect, it } from 'vitest'
import { horizonLabel, scoreTone, statusLabel, windowText } from './presentation'
import type { Claim } from './types'

const claim = (patch: Partial<Claim>): Claim => ({ id: '1', status: 'open', ...patch })
describe('presentation', () => {
  it('uses approved score thresholds', () => {
    expect(scoreTone(70)).toBe('good'); expect(scoreTone(50)).toBe('mid'); expect(scoreTone(49)).toBe('bad'); expect(scoreTone(null)).toBe('pending')
  })
  it('keeps status and verdict separate', () => {
    expect(statusLabel(claim({ status: 'resolved', verdict: 'good' }))).toBe('GOOD CALL')
    expect(statusLabel(claim({ status: 'expired', verdict: null }))).toBe('EXPIRED')
  })
  it('formats lifecycle windows without fixture strings', () => {
    expect(windowText(claim({ trigger_status: 'waiting' }))).toBe('Trigger not yet met')
    expect(windowText(claim({ horizon: 'swing' }))).toContain('SWING')
  })
  it('labels all supported horizons', () => expect(['short', 'swing', 'long'].map(horizonLabel)).toEqual(['SHORT-TERM', 'SWING', 'LONG-TERM']))
})
