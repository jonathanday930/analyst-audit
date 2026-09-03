import { FormEvent, MouseEvent, useEffect, useMemo, useState } from 'react'
import { addLink, ApiError, getClaim, getAnalyst, listClaims, listAnalysts, setFollowed } from './api'
import { asset, claimCount, formatDate, horizonLabel, initials, openCount, openNote, outcome, resolvedCount, score, scoreTone, statusLabel, ticker, windowText } from './presentation'
import type { Claim, Analyst, LinkResponse, SourceType } from './types'

type Screen = 'watchlist' | 'browse' | 'profile' | 'claim' | 'add'
const icon = (name: string) => <span className="icon" aria-hidden="true">{name}</span>
const message = (error: unknown) => error instanceof ApiError ? error.message : 'Something went wrong. Try again.'

function Sidebar({ screen, stats, navigate }: { screen: Screen; stats: string; navigate: (screen: Screen) => void }) {
  return <aside className="sidebar">
    <div className="brand"><div className="mono">ANALYST<span>·</span>AUDIT</div><small>track record engine</small></div>
    <nav aria-label="Main navigation">
      <button className={screen === 'watchlist' ? 'active' : ''} aria-current={screen === 'watchlist' ? 'page' : undefined} onClick={() => navigate('watchlist')}>{icon('▯')}Watchlist</button>
      <button className={screen === 'browse' ? 'active' : ''} aria-current={screen === 'browse' ? 'page' : undefined} onClick={() => navigate('browse')}>{icon('▦')}Browse all</button>
      <button className={screen === 'add' ? 'active' : ''} aria-current={screen === 'add' ? 'page' : undefined} onClick={() => navigate('add')}>{icon('+')}Add a link</button>
    </nav>
    <footer><div className="mono">{stats}</div><small>Single-user · MVP</small></footer>
  </aside>
}

export function FollowButton({ analyst, onChange }: { analyst: Analyst; onChange: (analyst: Analyst) => void }) {
  const [busy, setBusy] = useState(false)
  async function toggle(event: MouseEvent) {
    event.stopPropagation(); setBusy(true)
    const previous = !!analyst.followed
    onChange({ ...analyst, followed: !previous })
    try { onChange({ ...analyst, ...(await setFollowed(analyst.id, !previous)), followed: !previous }) }
    catch { onChange({ ...analyst, followed: previous }) }
    finally { setBusy(false) }
  }
  return <button className={`follow ${analyst.followed ? 'selected' : ''}`} disabled={busy} aria-label={`${analyst.followed ? 'Unfollow' : 'Follow'} ${analyst.name}`} onClick={toggle}>☆<span>{analyst.followed ? 'Following' : 'Follow'}</span></button>
}

function AnalystCard({ analyst, select, update }: { analyst: Analyst; select: () => void; update: (analyst: Analyst) => void }) {
  const value = score(analyst); const tone = scoreTone(value)
  return <article className="analyst-card" tabIndex={0} role="button" onClick={select} onKeyDown={(event) => { if (event.key === 'Enter') select() }}>
    <div className="analyst-top"><div className="avatar mono">{initials(analyst)}</div><div className="grow"><strong>{analyst.name}</strong><small>{analyst.last_active ?? formatDate(analyst.last_active_at)} · {(analyst.primary_source_type ?? 'mixed').toUpperCase()}</small></div><FollowButton analyst={analyst} onChange={update} /></div>
    <div><div className="score-line"><b className={`mono ${tone}`}>{value ?? '—'}</b><small>reliability</small></div><div className="score-track"><i className={tone} style={{ width: `${value ?? 0}%` }} /></div></div>
    {!!analyst.categories?.length && <div className="category-pills">{analyst.categories.map((category) => <span className="mono" key={category.label}>{category.label} {category.score ?? category.pct ?? '—'}%</span>)}</div>}
    <small className="counts">{claimCount(analyst)} claims · {resolvedCount(analyst)} resolved · {openCount(analyst)} open</small>
  </article>
}

export function AnalystListPage({ kind, analysts, loading, error, query, setQuery, select, update, navigate }: { kind: 'watchlist'|'browse'; analysts: Analyst[]; loading: boolean; error: string|null; query: string; setQuery: (s:string)=>void; select:(g: Analyst)=>void; update:(g:Analyst)=>void; navigate:(s:Screen)=>void }) {
  const shown = useMemo(() => analysts.slice().sort((a,b)=>(score(b)??-1)-(score(a)??-1)).filter(g=>g.name.toLowerCase().includes(query.trim().toLowerCase())), [analysts,query])
  return <div className="page list-page"><header className="page-header"><div><small>{kind === 'watchlist' ? 'Your assortment' : 'Catalog'}</small><h1>{kind === 'watchlist' ? 'Watchlist' : 'Browse all experts'}</h1></div><button className={kind === 'browse' ? 'primary' : 'secondary'} onClick={()=>navigate(kind==='browse'?'add':'browse')}>{kind==='browse'?'+ Add a link':'Browse all experts'}</button></header>
    <label className="search"><span aria-hidden="true">⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search experts" aria-label="Search experts" /></label>
    {loading && <p className="status" aria-live="polite">Loading experts…</p>}{error && <p className="error">{error}</p>}
    {!loading && !error && shown.length===0 && <div className="empty">{query ? `No experts match “${query}”.` : kind==='watchlist' ? 'Your watchlist is empty.' : 'No experts have been added yet.'}</div>}
    <div className="analyst-grid">{shown.map(g=><AnalystCard key={g.id} analyst={g} select={()=>select(g)} update={update}/>)}</div>
  </div>
}

function ClaimRow({ claim, select }: { claim: Claim; select:()=>void }) {
  const label=statusLabel(claim)
  return <button className="claim-row" onClick={select}><span className="claim-asset"><strong>{asset(claim)}</strong><small className="mono">{ticker(claim)}</small></span><span className="claim-source"><em>“{claim.source?.title ?? 'Source pending'}”</em><small className="mono">{claim.source?.type?.toUpperCase() ?? 'SOURCE'} · {formatDate(claim.source?.published_at ?? claim.created_at)}</small></span><span className="claim-outcome">{outcome(claim)}</span><span className={`badge horizon ${claim.horizon ?? ''}`}>{horizonLabel(claim.horizon)}</span><span className={`claim-status ${claim.status} ${claim.verdict ?? ''}`}>{label}</span><span aria-hidden="true">›</span></button>
}

export function ProfilePage({ analyst, claims, loading, filter, setFilter, back, add, selectClaim }: { analyst: Analyst; claims: Claim[]; loading:boolean; filter:string; setFilter:(s:string)=>void; back:()=>void; add:()=>void; selectClaim:(c:Claim)=>void }) {
  const visible=filter==='all'?claims:claims.filter(c=>c.status===filter)
  const value=score(analyst), tone=scoreTone(value)
  return <div className="page profile-page"><div className="toolbar"><button className="text-button" onClick={back}>‹ Back</button><button className="secondary" onClick={add}>+ Add a video or post</button></div>
    <section className="profile-head"><div className="avatar large mono">{initials(analyst)}</div><div className="grow"><h1>{analyst.name}</h1><p>{analyst.last_active ?? formatDate(analyst.last_active_at)} · {analyst.primary_source_type ? `${analyst.primary_source_type === 'video'?'Video':'Blog'}-focused`:'Mixed sources'} · {claimCount(analyst)} claims · {resolvedCount(analyst)} resolved · {openCount(analyst)} open</p>{!!analyst.categories?.length&&<><small className="eyebrow">Categories · auto-derived from claim history</small><div className="category-bars">{analyst.categories.map(c=><div key={c.label}><span>{c.label}</span><i><b style={{width:`${c.score??c.pct??0}%`}}/></i><span className="mono">{c.score??c.pct??'—'}%</span></div>)}</div></>}</div><div className="profile-score"><b className={`mono ${tone}`}>{value??'—'}</b><small>reliability</small>{analyst.score_delta_90d!=null&&<p className={`mono ${tone}`}>{analyst.score_delta_90d>=0?'+':''}{analyst.score_delta_90d} vs. prior period</p>}</div></section>
    <div className="tabs" role="group" aria-label="Claim filter">{['all','open','resolved'].map(v=><button key={v} className={filter===v?'active':''} onClick={()=>setFilter(v)}>{v==='all'?'All claims':v[0].toUpperCase()+v.slice(1)}</button>)}</div>
    {loading?<p className="status">Loading claims…</p>:visible.length?<div className="claim-list">{visible.map(c=><ClaimRow key={c.id} claim={c} select={()=>selectClaim(c)}/>)}</div>:<div className="empty">No claims in this filter.</div>}
  </div>
}

function ClaimDetailPage({ claim, back }: { claim: Claim; back:()=>void }) {
  const resolution=claim.resolution; const benchmarks=resolution?.benchmarks??[]; const trade=resolution?.trade_return_value
  return <div className="page detail-page"><button className="text-button" onClick={back}>‹ {claim.analyst?.name ?? claim.analyst_name ?? 'Expert'}</button><header><h1>{asset(claim)}</h1><p className="mono">{ticker(claim)}</p></header><div className="detail-grid">
    <section className="panel"><h2>The claim</h2><dl><dt>Condition</dt><dd>{claim.condition ?? 'None — unconditional'}<small className="mono">{(claim.condition_type??'unconditional').replace('_',' ').toUpperCase()}</small></dd><dt>Expected outcome</dt><dd>{outcome(claim)}</dd><dt>Horizon</dt><dd><span className={`badge horizon ${claim.horizon??''}`}>{horizonLabel(claim.horizon)}</span></dd><dt>Stated timeframe</dt><dd><em>{claim.timeframe_text ?? 'Not stated'}</em></dd><dt>Target window</dt><dd className="mono">{windowText(claim)}</dd></dl><div className="source-line"><div><small>Source</small>{claim.source?.url?<a href={claim.source.url} target="_blank" rel="noreferrer">“{claim.source.title??'View source'}” — {claim.source.type==='video'?'video':'blog post'}</a>:<span>Source pending</span>}</div><div><small>Claimed on</small><span className="mono">{formatDate(claim.source?.published_at??claim.created_at)}</span></div></div></section>
    <section className={`panel evaluation ${claim.status} ${claim.verdict??''}`}><h2>Evaluation</h2><span className={`badge status-badge ${claim.status} ${claim.verdict??''}`}>{statusLabel(claim)}</span>{resolution?<><p className="mono evaluated">Evaluated {formatDate(resolution.evaluated_at)}</p><h3>Rationale</h3><p>{resolution.rationale}</p></>:<p className="muted">{openNote(claim)}</p>}{benchmarks.length>0&&trade!=null&&<div className="benchmarks"><h3>Benchmark comparison</h3><div><span>This trade</span><b className={`mono ${trade>=0?'good':'bad'}`}>{trade>=0?'+':''}{trade.toFixed(1)}%</b></div>{benchmarks.map(b=><div key={`${b.ticker}-${b.label}`}><span>{b.label} <i className="mono">{b.ticker}</i></span><span className="mono">{b.value>=0?'+':''}{b.value.toFixed(1)}% <small className={trade>b.value?'good':'bad'}>{trade>b.value?'Beat':'Lagged'}</small></span></div>)}</div>}</section>
  </div></div>
}

type AddPhase='link'|'detect'|'processing'|'review'|'done'
export function AddFlow({ directAnalyst, back, done }: { directAnalyst: Analyst|null; back:()=>void; done:(analyst?:Analyst)=>void }) {
  const [phase,setPhase]=useState<AddPhase>('link'), [url,setUrl]=useState(''), [name,setName]=useState(''), [sourceHint,setSourceHint]=useState<SourceType>('video'), [forceNew,setForceNew]=useState(false), [response,setResponse]=useState<LinkResponse|null>(null), [selected,setSelected]=useState<Set<string>>(new Set()), [busy,setBusy]=useState(false), [error,setError]=useState<string|null>(null)
  const drafts=response?.draft_claims??[]; const returned=response?.claims??[]; const sourceType:SourceType=response?.source_type??(url.toLowerCase().includes('youtu')?'video':'blog')
  const steps=directAnalyst?4:5, order:AddPhase[]=directAnalyst?['link','processing','review','done']:['link','detect','processing','review','done']; const step=Math.max(1,order.indexOf(phase)+1)
  async function submit(overrides?:{analyst_name?:string;force_new?:boolean}) { setBusy(true);setError(null);try { const isProbe=!directAnalyst&&!overrides?.analyst_name&&!response; const result=await addLink({url,analyst_id:directAnalyst?.id??(!forceNew?response?.matched_analyst?.id:undefined),analyst_name:overrides?.analyst_name,force_new:overrides?.force_new??forceNew});setResponse(result);if(result.status==='requires_analyst_name'||(isProbe&&result.matched_analyst))setPhase('detect');else {setSelected(new Set((result.draft_claims??[]).map(c=>c.id)));setPhase('processing')}} catch(e){setError(message(e))}finally{setBusy(false)} }
  function continueProcessing(){ if(drafts.length)setPhase('review');else setPhase('done') }
  function toggle(id:string){setSelected(old=>{const next=new Set(old);if(next.has(id))next.delete(id);else next.add(id);return next})}
  return <div className="page add-page"><small className="flow-label mono">{directAnalyst?`Add to ${directAnalyst.name}`:'Add a link'} · Step {step} of {steps}</small><div className="progress">{Array.from({length:steps},(_,i)=><i key={i} className={i<step?'active':''}/>)}</div>{error&&<p className="error">{error}</p>}
    {phase==='link'&&<form onSubmit={(e:FormEvent)=>{e.preventDefault();void submit()}}><h1>{directAnalyst?`Add to ${directAnalyst.name}`:'Add a link'}</h1><p>Paste a YouTube video or blog post link{directAnalyst?' to add it to this expert’s history':' — we’ll check whether it is from an expert you already track'}.</p>{directAnalyst&&<><span className="field-label">Source type</span><div className="source-chips"><button type="button" className={sourceHint==='video'?'active':''} onClick={()=>setSourceHint('video')}>▣ Video</button><button type="button" className={sourceHint==='blog'?'active':''} onClick={()=>setSourceHint('blog')}>▤ Blog</button></div></>}<label>Video or blog link<input autoFocus type="url" value={url} onChange={e=>{setUrl(e.target.value);if(e.target.value.includes('youtu'))setSourceHint('video')}} placeholder="https://youtube.com/watch?v=... or https://example.com/post" required/></label><div className="actions"><button type="button" className="secondary" onClick={back}>Back</button><button className="primary" disabled={busy||!url.trim()}>{busy?'Checking…':'Continue'}</button></div></form>}
    {phase==='detect'&&<div><h1>{response?.matched_analyst&&!forceNew?'We recognized this source':'New expert details'}</h1><p className="mono detected">Detected: {sourceType==='video'?'Video':'Blog'} source</p>{response?.matched_analyst&&!forceNew?<><div className="detected-card"><div className="avatar mono">{initials(response.matched_analyst)}</div><div><strong>{response.matched_analyst.name}</strong><p>Recognized — we’ll add this to their existing claim history</p></div></div><button className="text-button underline" onClick={()=>{setForceNew(true);setResponse({...response,matched_analyst:null})}}>Not them? Register as a new expert instead</button></>:<label>Expert name<input autoFocus value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. MacroChartist"/></label>}<div className="actions"><button className="secondary" onClick={()=>setPhase('link')}>Back</button><button className="primary" disabled={busy||(!response?.matched_analyst&&!name.trim())} onClick={()=>void submit(response?.matched_analyst&&!forceNew?{}:{analyst_name:name.trim(),force_new:true})}>{busy?'Adding…':'Continue'}</button></div></div>}
    {phase==='processing'&&<div><h1>Source added</h1><div className="checklist"><div>✓ Matched source to {response?.analyst?.name||response?.matched_analyst?.name||name||directAnalyst?.name||'expert'}</div><div>✓ Fetched and stored source content</div><div>{drafts.length?<>✓ Extracted claims ready for review</>:<><span aria-hidden="true">◌</span> Claim extraction pending</>}</div></div>{!drafts.length&&<p className="pending-copy">The source is safely in the ledger. Claim-finder extraction is not connected yet, so no claims have been invented for this source. Pending claim records will update when that stage runs.</p>}<button className="primary" onClick={continueProcessing}>{drafts.length?'Review claims':'Continue'}</button></div>}
    {phase==='review'&&<div><h1>Review extracted claims</h1><p>Select the claims to carry forward. Selection persistence will be enabled with the claim-finder confirmation endpoint.</p><div className="drafts">{drafts.map(c=><button key={c.id} className="draft" onClick={()=>toggle(c.id)}><span className={`checkbox ${selected.has(c.id)?'checked':''}`}>{selected.has(c.id)?'✓':''}</span><span><strong>{asset(c)}</strong> <i className={`badge horizon ${c.horizon??''}`}>{horizonLabel(c.horizon)}</i><small>{outcome(c)}</small><em>{c.condition??'None — unconditional'}</em></span></button>)}</div><div className="actions"><button className="secondary" onClick={()=>setPhase('processing')}>Back</button><button className="primary" onClick={()=>setPhase('done')}>Continue with {selected.size} {selected.size===1?'claim':'claims'}</button></div></div>}
    {phase==='done'&&<div className="done"><div className="done-icon">✓</div><h1>{drafts.length?`${selected.size} claims reviewed`:`${returned.length||1} source record${returned.length===1?'':'s'} pending`}</h1><p>{drafts.length?'The selected claims are ready for the ledger.':'The claim analyzer will begin checking claims after extraction completes.'}</p><div className="actions"><button className="secondary" onClick={()=>done(directAnalyst??undefined)}>{directAnalyst?'Back to profile':'Back to Watchlist'}</button><button className="primary" onClick={()=>{setUrl('');setName('');setResponse(null);setForceNew(false);setPhase('link')}}>{directAnalyst?'Add another video/post':'Add another link'}</button></div></div>}
  </div>
}

export default function App(){
  const [screen,setScreen]=useState<Screen>('watchlist'), [listScreen,setListScreen]=useState<'watchlist'|'browse'>('watchlist'), [analysts,setAnalysts]=useState<Analyst[]>([]), [loading,setLoading]=useState(true), [error,setError]=useState<string|null>(null), [query,setQuery]=useState(''), [selectedAnalyst,setSelectedAnalyst]=useState<Analyst|null>(null), [claims,setClaims]=useState<Claim[]>([]), [selectedClaim,setSelectedClaim]=useState<Claim|null>(null), [claimFilter,setClaimFilter]=useState('all'), [directAdd,setDirectAdd]=useState<Analyst|null>(null)
  async function loadAnalysts(kind:'watchlist'|'browse'=screen==='browse'?'browse':'watchlist'){setLoading(true);setError(null);try{setAnalysts(await listAnalysts(kind==='watchlist'?true:undefined))}catch(e){setError(message(e))}finally{setLoading(false)}}
  // Initial API synchronization; navigation triggers subsequent list reloads.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(()=>{void loadAnalysts('watchlist')},[])
  function navigate(next:Screen){setScreen(next);setDirectAdd(null);if(next==='watchlist'||next==='browse'){setListScreen(next);void loadAnalysts(next)}}
  function updateAnalyst(next:Analyst){setAnalysts(old=>old.map(g=>g.id===next.id?next:g));if(selectedAnalyst?.id===next.id)setSelectedAnalyst(next)}
  async function selectAnalyst(g:Analyst){setError(null);setSelectedAnalyst(g);setClaims([]);setClaimFilter('all');setScreen('profile');setLoading(true);try{const detail=await getAnalyst(g.id);setSelectedAnalyst(detail);setClaims(detail.detail_claims??await listClaims(g.id))}catch(e){setError(message(e))}finally{setLoading(false)}}
  async function selectClaim(c:Claim){setSelectedClaim(c);setScreen('claim');try{setSelectedClaim(await getClaim(c.id))}catch{setSelectedClaim(c)}}
  const stats=`${analysts.length} experts · ${analysts.reduce((sum,g)=>sum+claimCount(g),0)} claims tracked`
  return <div className="app"><Sidebar screen={screen} stats={stats} navigate={navigate}/><main>{(screen==='watchlist'||screen==='browse')&&<AnalystListPage kind={screen} analysts={analysts} loading={loading} error={error} query={query} setQuery={setQuery} select={selectAnalyst} update={updateAnalyst} navigate={navigate}/>} {screen==='profile'&&selectedAnalyst&&<>{error&&<p className="page error">{error}</p>}<ProfilePage analyst={selectedAnalyst} claims={claims} loading={loading} filter={claimFilter} setFilter={setClaimFilter} back={()=>navigate(listScreen)} add={()=>{setDirectAdd(selectedAnalyst);setScreen('add')}} selectClaim={selectClaim}/></>} {screen==='claim'&&selectedClaim&&<ClaimDetailPage claim={selectedClaim} back={()=>setScreen('profile')}/>} {screen==='add'&&<AddFlow directAnalyst={directAdd} back={()=>directAdd?setScreen('profile'):navigate(listScreen)} done={(analyst)=>{const target=directAdd??analyst;if(target)void selectAnalyst(target);else navigate('watchlist')}}/>}</main></div>
}
