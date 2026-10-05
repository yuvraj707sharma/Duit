export interface PendingApproval {
  id: string;
  user_id: string;
  request_id: string;
  query_text: string;
  intent: string;
  risk: 'low' | 'medium' | 'high';
  confidence: number;
  arguments: Record<string, any>;
  status: 'pending' | 'approved' | 'rejected' | 'edited';
  created_at: number;
}

export interface AuditLog {
  request_id: string;
  user_id: string;
  intent: string;
  status: string;
  risk: string;
  confidence: number;
  latencies: Record<string, number>;
}

export interface MetricsData {
  total_requests: number;
  tokens_saved: number;
  cost_saved_usd: number;
  intent_distribution: Record<string, number>;
  stage_latencies_ms: Record<string, {
    avg: number;
    p50: number;
    p95: number;
    min: number;
    max: number;
    count: number;
  }>;
}

const API_BASE = '/api';

export async function fetchPendingApprovals(userId?: string): Promise<PendingApproval[]> {
  const url = userId ? `${API_BASE}/approvals?user_id=${userId}` : `${API_BASE}/approvals`;
  const res = await fetch(url);
  if (!res.ok) return [];
  return res.json();
}

export async function resolveApproval(
  approvalId: string,
  decision: 'approve' | 'edit' | 'reject',
  editedPayload?: Record<string, any>
): Promise<any> {
  const res = await fetch(`${API_BASE}/approvals/${approvalId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, edited_payload: editedPayload })
  });
  return res.json();
}

export async function fetchAuditLogs(userId?: string): Promise<AuditLog[]> {
  const url = userId ? `${API_BASE}/audit-logs?user_id=${userId}` : `${API_BASE}/audit-logs`;
  const res = await fetch(url);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchMetrics(): Promise<MetricsData> {
  const res = await fetch(`${API_BASE}/metrics`);
  if (!res.ok) {
    return {
      total_requests: 0,
      tokens_saved: 0,
      cost_saved_usd: 0,
      intent_distribution: {},
      stage_latencies_ms: {}
    };
  }
  return res.json();
}
