export type SourceType = 'video' | 'blog'
export type ClaimStatus = 'open' | 'resolved' | 'expired' | 'pending'
export type Verdict = 'good' | 'bad' | null
export type Horizon = 'short' | 'swing' | 'long'

export interface Category { label: string; score?: number; pct?: number }
export interface Analyst {
  id: string
  name: string
  initials?: string
  reliability_score?: number | null
  score?: number | null
  claim_count?: number
  claims?: number | Claim[]
  resolved_count?: number
  resolved?: number
  open_count?: number
  open?: number
  last_active_at?: string | null
  last_active?: string
  primary_source_type?: SourceType | null
  followed?: boolean
  categories?: Category[]
  score_delta_90d?: number | null
  score_history_90d?: number[]
  sources?: Source[]
  detail_claims?: Claim[]
}

export interface Benchmark { label: string; ticker: string; value: number; display?: string }
export interface Resolution {
  rationale: string
  evaluated_at: string
  trade_return_value?: number | null
  benchmarks?: Benchmark[]
}
export interface Source {
  id?: string
  type: SourceType
  url: string
  title?: string | null
  published_at?: string | null
}
export interface Claim {
  id: string
  source_id?: string
  extraction_status?: 'pending' | 'complete' | 'failed'
  analyst_id?: string
  analyst?: { id: string; name: string }
  analyst_name?: string
  source?: Source
  asset_description?: string
  asset?: string
  suggested_ticker?: string | null
  ticker?: string | null
  condition?: string | null
  condition_type?: 'unconditional' | 'price_trigger' | 'event_trigger' | string
  expected_outcome?: string
  outcome?: string
  horizon?: Horizon
  timeframe_text?: string | null
  target_window_start?: string | null
  target_window_end?: string | null
  trigger_status?: 'waiting' | 'triggered' | 'expired' | null
  trigger_observed_at?: string | null
  trigger_deadline?: string | null
  status: ClaimStatus
  verdict?: Verdict
  resolution?: Resolution | null
  rationale?: string | null
  evaluated_at?: string | null
  created_at?: string
  pending_message?: string
}

export interface LinkResponse {
  status: 'requires_analyst_name' | 'matched' | 'pending' | 'review_ready' | 'created'
  source_type?: SourceType
  matched_analyst?: Analyst | null
  analyst?: Analyst
  source_id?: string
  claims?: Claim[]
  draft_claims?: Claim[]
  message?: string
}
