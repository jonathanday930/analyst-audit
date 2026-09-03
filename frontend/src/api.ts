import type { Benchmark, Claim, Guru, Horizon, LinkResponse } from './types'

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload ? String(payload.detail) : null
    throw new ApiError(detail ?? `Request failed (${response.status}).`)
  }
  return payload as T
}

function query(params: Record<string, string | boolean | undefined>): string {
  const values = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') values.set(key, String(value)) })
  const result = values.toString()
  return result ? `?${result}` : ''
}

type Json = Record<string, any>
const field = <T>(value: Json, snake: string, camel: string): T | undefined => value[snake] ?? value[camel]

function normalizeClaim(raw: Json, sources: Json[] = []): Claim {
  const sourceId = field<string>(raw, 'source_id', 'sourceId')
  const embeddedSource = raw.source as Json | undefined
  const sourceRaw = embeddedSource ?? sources.find((source) => String(source.id) === String(sourceId))
  const extraction = field<string>(raw, 'extraction_status', 'extractionStatus') as Claim['extraction_status']
  const evaluations = (raw.evaluations ?? []) as Json[]
  const latest = evaluations.at(-1)
  const benchmark = latest?.benchmark as Json | null | undefined
  const benchmarks = Array.isArray(benchmark?.benchmarks) ? benchmark.benchmarks : []
  const rawHorizon = raw.horizon as string | undefined
  const horizon = (rawHorizon === 'short-term' ? 'short' : rawHorizon === 'long-term' || rawHorizon === 'structural' ? 'long' : rawHorizon) as Horizon | undefined
  const directResolution = raw.resolution as Json | null | undefined
  return {
    id: String(raw.id), source_id: sourceId, guru_id: field(raw, 'guru_id', 'guruId'), extraction_status: extraction,
    source: sourceRaw ? { id: String(sourceRaw.id), type: sourceRaw.type === 'youtube' ? 'video' : 'blog', url: sourceRaw.url, title: sourceRaw.title, published_at: field(sourceRaw, 'published_at', 'publishedAt') } : undefined,
    asset_description: field(raw, 'asset_description', 'assetDescription'), suggested_ticker: field(raw, 'suggested_ticker', 'suggestedTicker'),
    condition: field(raw, 'condition_trigger', 'conditionTrigger'), expected_outcome: field(raw, 'expected_outcome', 'expectedOutcome'),
    horizon, timeframe_text: field(raw, 'timeframe_as_stated', 'timeframeAsStated'),
    target_window_start: field(raw, 'target_window_start', 'targetWindowStart'), target_window_end: field(raw, 'target_window_end', 'targetWindowEnd'),
    trigger_status: field(raw, 'trigger_status', 'triggerStatus'), trigger_observed_at: field(raw, 'trigger_observed_at', 'triggerObservedAt'), trigger_deadline: field(raw, 'trigger_deadline', 'triggerDeadline'),
    status: extraction === 'pending' ? 'pending' : raw.status, verdict: (field(raw, 'latest_verdict', 'latestVerdict') ?? latest?.verdict) as Claim['verdict'],
    resolution: directResolution ? { rationale: String(directResolution.rationale ?? ''), evaluated_at: field(directResolution, 'evaluated_at', 'evaluatedAt') ?? '', trade_return_value: field(directResolution, 'trade_return_value', 'tradeReturnValue'), benchmarks: (directResolution.benchmarks as Benchmark[] | undefined) ?? [] } : latest ? { rationale: String(latest.rationale ?? ''), evaluated_at: field(latest, 'checked_at', 'checkedAt') ?? '', trade_return_value: field(benchmark ?? {}, 'trade_return_value', 'tradeReturnValue'), benchmarks } : null,
    pending_message: extraction === 'failed' ? 'Claim extraction failed.' : extraction === 'pending' ? 'Claim extraction pending' : undefined,
  }
}

function normalizeGuru(raw: Json): Guru {
  const sources = (raw.sources ?? []) as Json[]
  return {
    id: String(raw.id), name: raw.name, followed: !!raw.followed,
    claim_count: field(raw, 'claim_count', 'claimCount') ?? raw.claims?.length ?? 0,
    resolved_count: field(raw, 'resolved_count', 'resolvedCount') ?? 0,
    open_count: field(raw, 'open_count', 'openCount') ?? 0,
    last_active_at: field(raw, 'last_active_at', 'lastActiveAt'),
    primary_source_type: field(raw, 'primary_source_type', 'primarySourceType'),
    reliability_score: field(raw, 'reliability_score', 'reliabilityScore'),
    sources: sources.map((source) => ({ id: String(source.id), type: source.type === 'youtube' ? 'video' : 'blog', url: source.url, title: source.title, published_at: field(source, 'published_at', 'publishedAt') })),
    detail_claims: Array.isArray(raw.claims) ? raw.claims.map((claim: Json) => normalizeClaim(claim, sources)) : undefined,
  }
}

export async function listGurus(followed?: boolean): Promise<Guru[]> {
  const result = await request<Json[] | { gurus: Json[] }>(`/api/gurus${query({ followed })}`)
  return (Array.isArray(result) ? result : result.gurus).map(normalizeGuru)
}
export async function getGuru(id: string): Promise<Guru> { return normalizeGuru(await request<Json>(`/api/gurus/${encodeURIComponent(id)}`)) }
export async function listClaims(guruId?: string, status?: string, verdict?: string): Promise<Claim[]> {
  const result = await request<Json[] | { claims: Json[] }>(`/api/claims${query({ guru_id: guruId, status, verdict })}`)
  return (Array.isArray(result) ? result : result.claims).map((claim) => normalizeClaim(claim))
}
export async function getClaim(id: string): Promise<Claim> { return normalizeClaim(await request<Json>(`/api/claims/${encodeURIComponent(id)}`)) }
export function setFollowed(id: string, followed: boolean): Promise<Guru> {
  return request<Json>(`/api/gurus/${encodeURIComponent(id)}/follow`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ followed }),
  }).then(normalizeGuru)
}
export async function addLink(body: { url: string; guru_id?: string; guru_name?: string; force_new?: boolean }): Promise<LinkResponse> {
  const raw = await request<Json>('/api/links', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const wireStatus = raw.status as LinkResponse['status'] | undefined
  const requiresName = wireStatus === 'requires_guru_name' || (field<boolean>(raw, 'requires_guru_name', 'requiresGuruName') ?? false)
  const matchedRaw = field<Json>(raw, 'matched_guru', 'matchedGuru')
  const matched = matchedRaw ? normalizeGuru(matchedRaw) : null
  const claimRaw = raw.claim as Json | undefined
  const sourceRaw = raw.source as Json | undefined
  const claimsRaw = Array.isArray(raw.claims) ? raw.claims as Json[] : claimRaw ? [claimRaw] : []
  const draftsRaw = field<Json[]>(raw, 'draft_claims', 'draftClaims') ?? []
  const sourceType = field<string>(raw, 'source_type', 'sourceType') ?? sourceRaw?.type
  const guruRaw = raw.guru as Json | undefined
  return { status: requiresName ? 'requires_guru_name' : wireStatus ?? 'pending', source_type: sourceType === 'youtube' ? 'video' : sourceType as LinkResponse['source_type'], matched_guru: matched, guru: guruRaw ? normalizeGuru(guruRaw) : matched ?? undefined, source_id: field(raw, 'source_id', 'sourceId') ?? sourceRaw?.id as string | undefined, claims: claimsRaw.map((claim) => normalizeClaim(claim, sourceRaw ? [sourceRaw] : [])), draft_claims: draftsRaw.map((claim) => normalizeClaim(claim)), message: raw.message as string | undefined }
}
