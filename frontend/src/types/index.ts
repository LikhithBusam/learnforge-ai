export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: 'learner' | 'admin' | string;
  status?: string;
  created_at?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Space {
  id: string;
  owner_id: string;
  name: string;
  description?: string;
  created_at: string;
}

export interface Project {
  id: string;
  space_id: string;
  owner_id: string;
  name: string;
  description?: string;
  created_at: string;
}

export interface Material {
  id: string;
  project_id: string;
  title: string;
  filename: string;
  status: 'upload_pending' | 'processing' | 'completed' | 'failed';
  page_count: number;
  size_bytes: number;
  failure_reason?: string | null;
  created_at: string;
}

export interface UploadIntent {
  material_id: string;
  storage_key: string;
  upload_url?: string;
}

export interface Citation {
  material_id: string;
  page_number: number;
  chunk_id: string;
  document_title?: string;
}

export interface TutorMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  answer_status?: 'grounded' | 'insufficient_evidence' | 'error';
  citations?: Citation[];
  created_at: string;
}

export interface TutorConversation {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
}

export interface QuestionOption {
  id: string;
  text: string;
  is_correct?: boolean;
}

export interface Question {
  id: string;
  quiz_id: string;
  type: 'mcq' | 'open_ended';
  prompt: string;
  options?: QuestionOption[];
}

export interface Quiz {
  id: string;
  project_id: string;
  title: string;
  status: 'draft' | 'active' | 'completed';
  question_count: number;
  score?: number;
  created_at: string;
}

export interface ConceptMastery {
  concept_id: string;
  name?: string;
  mastery_probability: number;
  confidence: number;
  tier: 'Developing' | 'Progressing' | 'Mastered';
  updated_at: string;
}

export interface GrowthSnapshot {
  project_id: string;
  trend: 'improving' | 'stable' | 'declining' | 'attention_required';
  velocity: number;
  attention_concepts: string[];
  evaluated_at: string;
}

export interface Recommendation {
  id: string;
  project_id: string;
  concept_id?: string;
  title: string;
  description: string;
  action: string;
  priority: 'low' | 'medium' | 'high';
  score: number;
  reason_codes: string[];
  status: string;
  created_at: string;
}

export interface AnalyticsOverview {
  project_id: string;
  active_days: number;
  grounded_response_rate: number;
  quiz_completion_rate: number;
  total_study_events: number;
  cognitive_tiers: {
    developing: number;
    progressing: number;
    mastered: number;
  };
}

export interface AdminOverview {
  users: { total: number; active: number; admins: number };
  spaces: { total: number };
  projects: { total: number };
  materials: { total: number; ready: number; processing: number; failed: number; upload_pending?: number };
  learning: { total_events: number; active_projects: number };
  ai: { total_requests: number; failed_requests: number };
  jobs: { total_executions: number; failed_executions: number };
  timestamp: string;
}

export interface AdminSystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  checked_at: string;
  components: Record<string, { status: string; [key: string]: any }>;
}

export interface AdminAIUsage {
  range: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  avg_latency_ms: number;
  by_feature: Record<string, number>;
  by_model: Record<string, number>;
  estimated_cost_usd?: number | null;
}

export interface AdminJobExecution {
  id: string;
  task_name: string;
  queue: string;
  status: string;
  duration_ms: number | null;
  attempt: number;
  error_message?: string | null;
  created_at: string;
}

export interface AdminAuditLog {
  id: string;
  actor_user_id: string;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string | null;
  occurred_at: string;
  correlation_id: string | null;
  metadata_payload: Record<string, any>;
}
