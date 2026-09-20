import {
  TokenResponse,
  User,
  Space,
  Project,
  Material,
  UploadIntent,
  TutorConversation,
  TutorMessage,
  Quiz,
  Question,
  ConceptMastery,
  GrowthSnapshot,
  Recommendation,
  AnalyticsOverview,
  AdminOverview,
  AdminSystemHealth,
  AdminAIUsage,
  AdminJobExecution,
  AdminAuditLog,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

class ApiError extends Error {
  constructor(public status: number, message: string, public data?: any) {
    super(message);
    this.name = 'ApiError';
  }
}

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem('study_access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
    ...options.headers,
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorData: any = null;
    try {
      errorData = await response.json();
    } catch {
      // Ignored non-json
    }
    const message = errorData?.detail || errorData?.title || `Request failed with status ${response.status}`;
    throw new ApiError(response.status, message, errorData);
  }

  return response.json();
}

export const api = {
  // Authentication
  async login(credentials: { email: string; password: string }): Promise<TokenResponse> {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: credentials.email.trim(),
        password: credentials.password,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (res.status === 401) {
        throw new ApiError(401, 'Email or password is incorrect.', err);
      }
      if (res.status === 422) {
        throw new ApiError(422, 'Please enter a valid email and password.', err);
      }
      if (res.status === 429) {
        throw new ApiError(429, 'Too many login attempts. Please wait a moment and try again.', err);
      }
      throw new ApiError(res.status, err.detail || 'Login failed. Please try again.', err);
    }
    const tokenResp: TokenResponse = await res.json();
    localStorage.setItem('study_access_token', tokenResp.access_token);
    return tokenResp;
  },

  async register(data: { email: string; password: string; display_name?: string }): Promise<TokenResponse> {
    const payload: Record<string, any> = {
      email: data.email.trim(),
      password: data.password,
    };
    if (data.display_name && data.display_name.trim()) {
      payload.display_name = data.display_name.trim();
    }
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (res.status === 422) {
        throw new ApiError(422, 'Please enter a valid email and password.', err);
      }
      throw new ApiError(res.status, err.detail || 'Registration failed. Email may already be in use.', err);
    }
    const tokenResp: TokenResponse = await res.json();
    localStorage.setItem('study_access_token', tokenResp.access_token);
    return tokenResp;
  },

  async getCurrentUser(): Promise<User> {
    return request<User>('/auth/me');
  },

  async logout(): Promise<void> {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
        },
      });
    } catch {
      // Best effort
    } finally {
      localStorage.removeItem('study_access_token');
    }
  },

  // Workspace
  async listSpaces(): Promise<{ items: Space[]; total: number }> {
    return request('/spaces');
  },

  async createSpace(data: { name: string; description?: string }): Promise<Space> {
    return request('/spaces', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async listProjects(spaceId?: string): Promise<{ items: Project[]; total: number }> {
    const endpoint = spaceId ? `/spaces/${spaceId}/projects` : '/projects';
    return request(endpoint);
  },

  async createProject(spaceId: string, data: { name: string; description?: string }): Promise<Project> {
    return request(`/spaces/${spaceId}/projects`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async getProject(projectId: string): Promise<Project> {
    return request(`/projects/${projectId}`);
  },

  // Materials
  async listMaterials(projectId: string): Promise<{ items: Material[]; total: number }> {
    const res = await request<Material[] | { items: Material[]; total: number }>(`/projects/${projectId}/materials`);
    if (Array.isArray(res)) {
      return { items: res, total: res.length };
    }
    return res;
  },

  async createUploadIntent(projectId: string, data: { title: string; filename: string; content_type: string; size_bytes: number }): Promise<UploadIntent> {
    return request(`/projects/${projectId}/materials`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async markMaterialCompleted(projectId: string, materialId: string, _pageCount?: number): Promise<Material> {
    return request(`/projects/${projectId}/materials/${materialId}/complete`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  },

  // Tutor
  async listConversations(projectId: string): Promise<{ items: TutorConversation[] }> {
    const res = await request<TutorConversation[] | { items: TutorConversation[] }>(`/projects/${projectId}/tutor/conversations`);
    if (Array.isArray(res)) {
      return { items: res };
    }
    return res;
  },

  async createConversation(projectId: string, title: string = 'New Conversation'): Promise<TutorConversation> {
    return request(`/projects/${projectId}/tutor/conversations`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  },

  async getMessages(projectId: string, conversationId: string): Promise<{ items: TutorMessage[] }> {
    const res = await request<TutorMessage[] | { items: TutorMessage[] }>(`/projects/${projectId}/tutor/conversations/${conversationId}/messages`);
    if (Array.isArray(res)) {
      return { items: res };
    }
    return res;
  },

  async sendTutorMessage(
    projectId: string,
    conversationId: string,
    content: string,
    onToken?: (token: string) => void,
    onCitation?: (citation: any) => void
  ): Promise<TutorMessage> {
    const response = await fetch(`${API_BASE}/projects/${projectId}/tutor/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...getAuthHeader(),
      },
      body: JSON.stringify({
        content,
        idempotency_key: `turn-${Date.now()}`,
      }),
    });

    if (!response.ok) {
      throw new ApiError(response.status, 'Tutor request failed');
    }

    // Check if response is stream or json
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/event-stream') && response.body) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';
      let answerStatus: any = 'grounded';
      const citations: any[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.event === 'token' && data.token) {
                fullContent += data.token;
                onToken?.(data.token);
              } else if (data.event === 'citation' && data.citation) {
                citations.push(data.citation);
                onCitation?.(data.citation);
              } else if (data.event === 'insufficient_evidence') {
                answerStatus = 'insufficient_evidence';
              }
            } catch {
              // Ignore non-json lines
            }
          }
        }
      }

      return {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: fullContent,
        answer_status: answerStatus,
        citations,
        created_at: new Date().toISOString(),
      };
    } else {
      return response.json();
    }
  },

  // Assessment
  async createQuiz(projectId: string, title: string = 'Adaptive Quiz', count: number = 3): Promise<Quiz> {
    return request(`/projects/${projectId}/quizzes`, {
      method: 'POST',
      body: JSON.stringify({ target_question_count: count, mode: 'adaptive' }),
    });
  },

  async getNextQuestion(projectId: string, quizId: string): Promise<Question | null> {
    const res: any = await request(`/projects/${projectId}/quizzes/${quizId}/next`);
    if (!res || res.status === 'completed' || res.message) {
      return null;
    }
    return {
      id: res.id,
      quiz_id: quizId,
      type: res.question_type || 'mcq',
      prompt: res.question_text || '',
      options: (res.options || []).map((o: any) => ({
        id: o.id,
        text: o.text,
      })),
    };
  },

  async submitAnswer(projectId: string, quizId: string, data: { question_id: string; selected_option_id?: string; text_response?: string }): Promise<any> {
    return request(`/projects/${projectId}/quizzes/${quizId}/answers?question_id=${encodeURIComponent(data.question_id)}`, {
      method: 'POST',
      body: JSON.stringify({
        question_id: data.question_id,
        selected_option: data.selected_option_id,
        selected_option_id: data.selected_option_id,
        response_text: data.text_response,
        text_response: data.text_response,
      }),
    });
  },

  // Mastery (BKT)
  async getProjectMastery(projectId: string): Promise<{ items: ConceptMastery[] }> {
    const res = await request<ConceptMastery[] | { items: ConceptMastery[] }>(`/projects/${projectId}/mastery`);
    if (Array.isArray(res)) {
      return { items: res };
    }
    return res;
  },

  // Growth
  async getProjectGrowth(projectId: string): Promise<GrowthSnapshot> {
    return request(`/projects/${projectId}/growth`);
  },

  // Recommendations
  async getRecommendations(projectId: string): Promise<{ items: Recommendation[] }> {
    const res = await request<any>(`/projects/${projectId}/recommendations`);
    if (Array.isArray(res)) {
      return { items: res };
    }
    return res;
  },

  async generateRecommendations(projectId: string): Promise<{ items: Recommendation[] }> {
    const res = await request<any>(`/projects/${projectId}/recommendations/generate`, {
      method: 'POST',
    });
    if (Array.isArray(res)) {
      return { items: res };
    }
    return res;
  },

  // Analytics
  async getProjectAnalytics(projectId: string, range: string = '30d'): Promise<AnalyticsOverview> {
    return request(`/projects/${projectId}/analytics/overview?range=${range}`);
  },

  // Admin
  async getAdminOverview(): Promise<AdminOverview> {
    return request('/admin/overview');
  },

  async getAdminUsers(page: number = 1, pageSize: number = 50, query?: string): Promise<{ items: User[]; total: number }> {
    const q = query ? `&query=${encodeURIComponent(query)}` : '';
    return request(`/admin/users?page=${page}&page_size=${pageSize}${q}`);
  },

  async getAdminUserDetail(userId: string): Promise<any> {
    return request(`/admin/users/${userId}`);
  },

  async getAdminProjects(page: number = 1, pageSize: number = 50): Promise<{ items: Project[]; total: number }> {
    return request(`/admin/projects?page=${page}&page_size=${pageSize}`);
  },

  async getAdminProjectDetail(projectId: string): Promise<any> {
    return request(`/admin/projects/${projectId}`);
  },

  async getAdminMaterialProcessing(): Promise<any> {
    return request('/admin/materials/processing');
  },

  async getAdminAIUsage(range: string = '24h'): Promise<AdminAIUsage> {
    return request(`/admin/ai/usage?range=${range}`);
  },

  async getAdminJobs(limit: number = 50): Promise<{ total_executions: number; succeeded_count: number; failed_count: number; recent_executions: AdminJobExecution[] }> {
    return request(`/admin/jobs?limit=${limit}`);
  },

  async getAdminHealth(): Promise<AdminSystemHealth> {
    return request('/admin/health');
  },

  async getAdminAuditLogs(page: number = 1, pageSize: number = 50): Promise<{ items: AdminAuditLog[]; total: number }> {
    return request(`/admin/audit?page=${page}&page_size=${pageSize}`);
  },
};
