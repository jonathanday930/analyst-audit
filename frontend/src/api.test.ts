import { afterEach, describe, expect, it, vi } from 'vitest'
import { addLink, getGuru, listGurus } from './api'

afterEach(() => vi.unstubAllGlobals())
const respond = (body: unknown) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }))

describe('API wire normalization', () => {
  it('normalizes FastAPI camel-case guru summaries', async () => {
    respond([{ id: 'g1', name: 'Macro', followed: true, claimCount: 4 }])
    await expect(listGurus(true)).resolves.toMatchObject([{ id: 'g1', claim_count: 4 }])
    expect(fetch).toHaveBeenCalledWith('/api/gurus?followed=true', undefined)
  })

  it('joins guru-detail sources onto claims and treats extraction placeholders as pending', async () => {
    respond({ id: 'g1', name: 'Macro', followed: true, claimCount: 1, sources: [{ id: 's1', type: 'youtube', url: 'https://youtu.be/x', title: 'Video', publishedAt: '2026-09-01' }], claims: [{ id: 'c1', sourceId: 's1', guruId: 'g1', extractionStatus: 'pending', status: 'open', evaluations: [] }] })
    const guru = await getGuru('g1')
    expect(guru.detail_claims?.[0]).toMatchObject({ status: 'pending', source: { type: 'video', title: 'Video' } })
  })

  it('maps the current add-link response into the frontend flow contract', async () => {
    respond({ requiresGuruName: false, matchedGuru: { id: 'g1', name: 'Macro', followed: true, claimCount: 1 }, source: { id: 's1', type: 'blog', url: 'https://example.com/a' }, claim: { id: 'c1', sourceId: 's1', guruId: 'g1', extractionStatus: 'pending', status: 'open', evaluations: [] } })
    await expect(addLink({ url: 'https://example.com/a' })).resolves.toMatchObject({ status: 'pending', source_type: 'blog', claims: [{ status: 'pending' }] })
  })

  it('preserves link status and normalizes an embedded claim source', async () => {
    respond({ status: 'review_ready', source_type: 'video', claims: [{ id: 'c1', source_id: 's1', guru_id: 'g1', extraction_status: 'complete', status: 'open', horizon: 'short-term', source: { id: 's1', type: 'video', url: 'https://youtu.be/x', title: 'Clip' }, evaluations: [] }], draft_claims: [] })
    const result = await addLink({ url: 'https://youtu.be/x' })
    expect(result).toMatchObject({ status: 'review_ready', claims: [{ horizon: 'short', source: { title: 'Clip' } }] })
  })

  it('preserves all guru summary metrics', async () => {
    respond([{ id: 'g1', name: 'Macro', followed: true, claim_count: 4, resolved_count: 2, open_count: 1, last_active_at: '2026-09-02T10:00:00Z', primary_source_type: 'video', reliability_score: 78 }])
    await expect(listGurus()).resolves.toMatchObject([{ resolved_count: 2, open_count: 1, primary_source_type: 'video', reliability_score: 78 }])
  })
})
