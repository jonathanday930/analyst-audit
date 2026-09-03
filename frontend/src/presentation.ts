import type { Claim, Analyst } from './types'

export const score = (analyst: Analyst): number | null => analyst.reliability_score ?? analyst.score ?? null
export const initials = (analyst: Analyst): string => analyst.initials ?? analyst.name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
export const claimCount = (analyst: Analyst): number => analyst.claim_count ?? (typeof analyst.claims === 'number' ? analyst.claims : analyst.claims?.length) ?? 0
export const resolvedCount = (analyst: Analyst): number => analyst.resolved_count ?? analyst.resolved ?? 0
export const openCount = (analyst: Analyst): number => analyst.open_count ?? analyst.open ?? 0
export const asset = (claim: Claim): string => claim.asset_description ?? claim.asset ?? 'Pending claim'
export const ticker = (claim: Claim): string => claim.suggested_ticker ?? claim.ticker ?? '—'
export const outcome = (claim: Claim): string => claim.expected_outcome ?? claim.outcome ?? claim.pending_message ?? 'Claim extraction pending'

export function scoreTone(value: number | null): 'good' | 'mid' | 'bad' | 'pending' {
  if (value === null) return 'pending'
  if (value >= 70) return 'good'
  if (value >= 50) return 'mid'
  return 'bad'
}
export function statusLabel(claim: Claim): string {
  if (claim.status === 'pending') return 'PENDING'
  if (claim.status === 'expired') return 'EXPIRED'
  if (claim.status === 'open') return 'OPEN'
  return claim.verdict === 'good' ? 'GOOD CALL' : claim.verdict === 'bad' ? 'BAD CALL' : 'RESOLVED'
}
export function horizonLabel(value?: string): string {
  return value === 'short' ? 'SHORT-TERM' : value === 'long' ? 'LONG-TERM' : value === 'swing' ? 'SWING' : '—'
}
export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(date)
}
export function windowText(claim: Claim): string {
  if (claim.trigger_status === 'expired' || claim.status === 'expired') return 'Trigger deadline passed — condition never triggered'
  if (claim.trigger_status === 'waiting') return 'Trigger not yet met'
  if (!claim.target_window_start && !claim.target_window_end) return 'Open-ended — rechecked periodically'
  return [formatDate(claim.target_window_start), formatDate(claim.target_window_end)].join(' – ')
}
export function openNote(claim: Claim): string {
  if (claim.status === 'pending') return claim.pending_message ?? 'Claim extraction is pending. It will appear in the ledger when the claim finder is connected.'
  if (claim.status === 'expired') return 'The condition never triggered before its deadline. This claim expired unevaluated and is not scored.'
  if (claim.trigger_status === 'waiting') return 'The condition has not triggered yet. It will be checked until the trigger deadline passes.'
  if (!claim.target_window_start && !claim.target_window_end) return 'No fixed target date. The analyzer rechecks this claim periodically.'
  return 'The target window has not arrived yet. The analyzer will resolve this claim once it does.'
}
