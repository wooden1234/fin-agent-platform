import type { Citation, RiskLevel, AgentRoute } from './api'

export type AgentSSEEvent =
  | { type: 'token'; content: string }
  | { type: 'done'; citations?: Citation[]; route?: AgentRoute; risk_level?: RiskLevel }
  | { type: 'interrupt'; conversation_id: string; message?: string }
  | { type: 'meta'; route?: AgentRoute; risk_level?: RiskLevel }
  | { type: 'error'; message: string }
