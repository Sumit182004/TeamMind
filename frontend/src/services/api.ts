
import axios from "axios";

const api = axios.create({
  baseURL: "http://127.0.0.1:8000",
  timeout: 180000,
});

export interface Decision {
  id: number;
  title: string;
  problem: string;
  options: string[];
  status: string;
  recommendation: string | null;
  created_at: string;
}

export interface OmiTranscriptResponse {
  status: string;
  source: string;
  decision: Decision;
  related_memories: unknown[];
  memory_saved: boolean;
  message: string;
}

export interface OmiExtractionResponse {
  status: string;
  source: string;
  title: string;
  problem: string;
  options: string[];
  message: string;
}

export interface OmiSession {
  session_id: string;
  started_at: string;
  last_seen: string;
  segment_count: number;
  transcript: string;
}

export interface OmiSegment {
  id: string;
  transcript: string;
  speaker: string | null;
  created_at: string;
}

export interface OmiSessionAnalysisResponse {
  status: string;
  decision_id: number;
  session_id: string;
  title: string;
  problem: string;
  options: string[];
  transcript?: string;
  workflow: {
    decision_id: number;
    status: string;
    agent_outputs: Record<string, unknown>;
    message: string;
  };
  message: string;
}

export async function getDecisions(): Promise<Decision[]> {
  const response = await api.get<Decision[]>("/api/decisions");
  return response.data;
}

export async function createDecision(data: {
  title: string;
  problem: string;
  options: string[];
}): Promise<Decision> {
  const response = await api.post<Decision>("/api/decisions", data);
  return response.data;
}

export async function runDecision(id: number) {
  const response = await api.post(`/api/decisions/${id}/run`);
  return response.data;
}

export async function getDecisionReport(id: number) {
  const response = await api.get(`/api/decisions/${id}/report`);
  return response.data;
}

export async function ingestOmiTranscript(
  transcript: string
): Promise<OmiTranscriptResponse> {
  const response = await api.post<OmiTranscriptResponse>(
    "/api/omi/transcript",
    {
      transcript,
      source: "omi",
    }
  );

  return response.data;
}

export async function extractOmiTranscript(
  transcript: string
): Promise<OmiExtractionResponse> {
  const response = await api.post<OmiExtractionResponse>(
    "/api/omi/extract",
    {
      transcript,
      source: "omi",
    }
  );

  return response.data;
}

export async function saveDecisionSourceTranscript(
  decisionId: number,
  transcript: string
): Promise<{
  status: string;
  decision_id: number;
  message: string;
}> {
  const response = await api.post<{
    status: string;
    decision_id: number;
    message: string;
  }>(`/api/decisions/${decisionId}/source-transcript`, {
    transcript,
    source: "omi",
  });

  return response.data;
}

export async function getOmiSessions(): Promise<OmiSession[]> {
  const response = await api.get<{ sessions: OmiSession[] }>(
    "/api/omi/sessions"
  );

  return response.data.sessions;
}

export async function getOmiSegments(
  sessionId: string
): Promise<OmiSegment[]> {
  const response = await api.get<{ segments: OmiSegment[] }>(
    `/api/omi/session/${encodeURIComponent(sessionId)}/segments`
  );

  return response.data.segments;
}

export async function analyzeOmiSession(
  sessionId: string,
  segmentIds?: string[]
): Promise<OmiSessionAnalysisResponse> {
  const response = await api.post<OmiSessionAnalysisResponse>(
    `/api/omi/session/${encodeURIComponent(sessionId)}/analyze`,
    segmentIds && segmentIds.length > 0
      ? { segment_ids: segmentIds }
      : {}
  );

  return response.data;
}
