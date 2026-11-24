// Shared domain types for the Argus debate system.
// Centralising these removes `any` annotations from hooks and components,
// and gives TypeScript enough information to catch shape mismatches at build time.

export type AgentStatus = 'active' | 'done' | 'idle';
export type HumanSide = 'pro' | 'con' | 'syn' | null;
export type JudgeStatus = 'online' | 'offline' | 'checking';
export type DebateView = 'active' | 'history' | 'logs';

export interface AgentPipelineEntry {
  id: string;
  name: string;
  status: AgentStatus;
}

export interface HumanTurn {
  role: 'pro' | 'con' | 'syn';
  round: number;
  sub_round: number;
}

export interface DebateMessage {
  type:
    | 'pro'
    | 'con'
    | 'syn'
    | 'verdict'
    | 'final_verdict'
    | 'sub_round_divider'
    | 'fact_check'
    | 'debate_end';
  round?: number;
  sub_round?: number;
  text?: string;
  model?: string;
  latency?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: any;
  label?: string;
}

export interface StackInfo {
  model?: string;
  scorer?: string;
  ftOnline?: boolean;
  docs?: number;
}

export interface HistoryEntry {
  id: string;
  topic: string;
  created_at: string;
  rounds: number;
  winner?: string;
  is_tie?: boolean;
  error?: string;
  pro_total?: number;
  con_total?: number;
  syn_total?: number;
  scorer?: string;
}

export interface JudgeLog {
  debate_id: string;
  round: number;
  topic: string;
  pro_total: number;
  con_total: number;
  syn_total?: number;
  winner?: string;
  scorer?: string;
  verification_backend?: string;
  blind_passes?: number;
  label_disagreement?: number;
  pro_coverage?: number;
  con_coverage?: number;
  syn_coverage?: number;
  pro_repetition_penalty?: number;
  con_repetition_penalty?: number;
  syn_repetition_penalty?: number;
  fallacy?: string;
  pro_evidence_cited?: string[];
  con_evidence_cited?: string[];
  syn_evidence_cited?: string[];
}
