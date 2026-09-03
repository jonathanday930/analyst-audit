// @vitest-environment jsdom
import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AddFlow, FollowButton, GuruListPage, ProfilePage } from './App'
import type { Claim, Guru, LinkResponse } from './types'

const api = vi.hoisted(() => ({ addLink: vi.fn(), setFollowed: vi.fn() }))
vi.mock('./api', async (importOriginal) => ({ ...(await importOriginal<typeof import('./api')>()), addLink: api.addLink, setFollowed: api.setFollowed }))

afterEach(() => { cleanup(); vi.clearAllMocks() })
const gurus: Guru[] = [
  { id: 'g1', name: 'MacroChartist', followed: true, reliability_score: 78 },
  { id: 'g2', name: 'ValueVane', followed: true, reliability_score: 85 },
]
const pending = (extra: Partial<LinkResponse> = {}): LinkResponse => ({ status: 'pending', guru: gurus[0], matched_guru: gurus[0], claims: [{ id: 'p1', status: 'pending' }], ...extra })

describe('list/profile interactions', () => {
  it('searches experts and filters claims without runtime fixtures', async () => {
    const user = userEvent.setup()
    function ListHarness() { const [query, setQuery] = useState(''); return <GuruListPage kind="browse" gurus={gurus} loading={false} error={null} query={query} setQuery={setQuery} select={()=>{}} update={()=>{}} navigate={()=>{}} /> }
    const { rerender } = render(<ListHarness />)
    await user.type(screen.getByLabelText('Search experts'), 'value')
    expect(screen.queryByText('MacroChartist')).toBeNull(); expect(screen.getByText('ValueVane')).toBeTruthy()
    const claims: Claim[] = [{ id: 'open', status: 'open', asset_description: 'Gold' }, { id: 'done', status: 'resolved', verdict: 'good', asset_description: 'Oil' }]
    rerender(<ProfilePage guru={gurus[0]} claims={claims} loading={false} filter="open" setFilter={()=>{}} back={()=>{}} add={()=>{}} selectClaim={()=>{}} />)
    expect(screen.getByText('Gold')).toBeTruthy(); expect(screen.queryByText('Oil')).toBeNull()
  })

  it('rolls an optimistic follow change back when the API fails', async () => {
    api.setFollowed.mockRejectedValueOnce(new Error('offline'))
    function Harness(){ const [guru,setGuru]=useState<Guru>({...gurus[0],followed:false}); return <FollowButton guru={guru} onChange={setGuru}/> }
    render(<Harness />); fireEvent.click(screen.getByRole('button',{name:'Follow MacroChartist'}))
    await waitFor(()=>expect(screen.getByRole('button',{name:'Follow MacroChartist'})).toBeTruthy())
  })
})

describe('add-link flow', () => {
  it('asks for a name when unmatched and truthfully finishes a pending source', async () => {
    const user=userEvent.setup(); api.addLink.mockResolvedValueOnce({status:'requires_guru_name',matched_guru:null,claims:[]}).mockResolvedValueOnce(pending())
    render(<AddFlow directGuru={null} back={()=>{}} done={()=>{}} />)
    await user.type(screen.getByLabelText('Video or blog link'),'https://example.com/post'); await user.click(screen.getByRole('button',{name:'Continue'}))
    await user.type(await screen.findByLabelText('Expert name'),'New Guru'); await user.click(screen.getByRole('button',{name:'Continue'}))
    expect(await screen.findByText('Claim extraction pending')).toBeTruthy(); await user.click(screen.getByRole('button',{name:'Continue'}))
    expect(screen.getByText(/source record.*pending/)).toBeTruthy(); expect(api.addLink.mock.calls[1][0]).toMatchObject({guru_name:'New Guru',force_new:true})
  })

  it('preserves recognized-source Not them override', async () => {
    const user=userEvent.setup(); api.addLink.mockResolvedValueOnce(pending()).mockResolvedValueOnce(pending({guru:{...gurus[0],id:'new',name:'Other'}}))
    render(<AddFlow directGuru={null} back={()=>{}} done={()=>{}} />)
    await user.type(screen.getByLabelText('Video or blog link'),'https://youtube.com/watch?v=abc'); await user.click(screen.getByRole('button',{name:'Continue'}))
    await user.click(await screen.findByRole('button',{name:/Not them/})); await user.type(screen.getByLabelText('Expert name'),'Other'); await user.click(screen.getByRole('button',{name:'Continue'}))
    await screen.findByText('Source added'); expect(api.addLink.mock.calls[1][0]).toMatchObject({guru_name:'Other',force_new:true})
  })

  it('keeps draft claims checked by default and supports toggling', async () => {
    const user=userEvent.setup(); api.addLink.mockResolvedValueOnce(pending({status:'review_ready',draft_claims:[{id:'d1',status:'open',asset_description:'Nvidia'},{id:'d2',status:'open',asset_description:'Gold'}]}))
    render(<AddFlow directGuru={gurus[0]} back={()=>{}} done={()=>{}} />)
    expect(screen.getByRole('button',{name:/Video/}).className).toContain('active')
    await user.type(screen.getByLabelText('Video or blog link'),'https://example.com/post'); await user.click(screen.getByRole('button',{name:'Continue'})); await user.click(await screen.findByRole('button',{name:'Review claims'}))
    expect(screen.getByRole('button',{name:/Continue with 2 claims/})).toBeTruthy(); await user.click(screen.getByRole('button',{name:/Nvidia/})); expect(screen.getByRole('button',{name:/Continue with 1 claim/})).toBeTruthy()
  })
})
