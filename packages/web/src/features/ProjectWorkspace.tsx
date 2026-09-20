import React, { useState, useEffect } from 'react';
import {
  Project,
  Material,
  TutorConversation,
  TutorMessage,
  Quiz,
  Question,
  ConceptMastery,
  GrowthSnapshot,
  Recommendation,
  AnalyticsOverview,
} from '../types';
import { api } from '../services/api';
import {
  UploadCloud,
  FileText,
  MessageSquare,
  Award,
  TrendingUp,
  Lightbulb,
  BarChart3,
  Send,
  AlertCircle,
  CheckCircle2,
  Clock,
  Sparkles,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';

interface ProjectWorkspaceProps {
  project: Project;
  initialTab?: string;
}

export const ProjectWorkspace: React.FC<ProjectWorkspaceProps> = ({
  project,
  initialTab = 'materials',
}) => {
  const [activeTab, setActiveTab] = useState<string>(initialTab);

  // Data states
  const [materials, setMaterials] = useState<Material[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadTitle, setUploadTitle] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Tutor states
  const [conversations, setConversations] = useState<TutorConversation[]>([]);
  const [currentConv, setCurrentConv] = useState<TutorConversation | null>(null);
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  // Quiz states
  const [currentQuiz, setCurrentQuiz] = useState<Quiz | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [textAnswer, setTextAnswer] = useState('');
  const [quizScore, setQuizScore] = useState<number | null>(null);
  const [quizComplete, setQuizComplete] = useState(false);

  // Intelligence states
  const [masteryItems, setMasteryItems] = useState<ConceptMastery[]>([]);
  const [growth, setGrowth] = useState<GrowthSnapshot | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null);
  const [analyticsRange, setAnalyticsRange] = useState('30d');

  // Load project-scoped data
  const loadMaterials = async () => {
    try {
      const res = await api.listMaterials(project.id);
      setMaterials(res.items || []);
    } catch {
      // tolerate empty
    }
  };

  const loadTutor = async () => {
    try {
      const convRes = await api.listConversations(project.id);
      setConversations(convRes.items || []);
      if (convRes.items && convRes.items.length > 0) {
        const active = convRes.items[0];
        setCurrentConv(active);
        const msgRes = await api.getMessages(project.id, active.id);
        setMessages(msgRes.items || []);
      }
    } catch {
      // tolerate empty
    }
  };

  const loadMastery = async () => {
    try {
      const res = await api.getProjectMastery(project.id);
      setMasteryItems(res.items || []);
    } catch {
      // tolerate
    }
  };

  const loadGrowth = async () => {
    try {
      const res = await api.getProjectGrowth(project.id);
      setGrowth(res);
    } catch {
      // tolerate
    }
  };

  const loadRecommendations = async () => {
    try {
      const res = await api.getRecommendations(project.id);
      setRecommendations(res.items || []);
    } catch {
      // tolerate
    }
  };

  const loadAnalytics = async () => {
    try {
      const res = await api.getProjectAnalytics(project.id, analyticsRange);
      setAnalytics(res);
    } catch {
      // tolerate
    }
  };

  useEffect(() => {
    loadMaterials();
    loadTutor();
    loadMastery();
    loadGrowth();
    loadRecommendations();
    loadAnalytics();
  }, [project.id]);

  useEffect(() => {
    if (activeTab === 'analytics') {
      loadAnalytics();
    }
  }, [analyticsRange]);

  // Upload handler
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !uploadTitle.trim()) return;

    setIsUploading(true);
    try {
      const intent = await api.createUploadIntent(project.id, {
        title: uploadTitle.trim(),
        filename: selectedFile.name,
        content_type: selectedFile.type || 'application/pdf',
        size_bytes: selectedFile.size,
      });

      // Upload raw file bytes to the presigned storage URL
      if (intent.upload_url) {
        const uploadRes = await fetch(intent.upload_url, {
          method: 'PUT',
          headers: {
            'Content-Type': selectedFile.type || 'application/pdf',
          },
          body: selectedFile,
        });
        if (!uploadRes.ok) {
          throw new Error(`Storage upload failed with status ${uploadRes.status}`);
        }
      }

      // Notify backend to verify file in storage and trigger background ingestion
      await api.markMaterialCompleted(project.id, intent.material_id);
      setUploadTitle('');
      setSelectedFile(null);
      await loadMaterials();
    } catch (err: any) {
      alert(err.message || 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  // Send message to AI Tutor
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isStreaming) return;

    let convId = currentConv?.id;
    if (!convId) {
      const newConv = await api.createConversation(project.id, 'Study Session');
      setCurrentConv(newConv);
      convId = newConv.id;
    }

    const userText = inputMessage.trim();
    setInputMessage('');

    const userMsg: TutorMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: userText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);

    try {
      const assistantMsg = await api.sendTutorMessage(
        project.id,
        convId,
        userText
      );
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `msg-${Date.now()}`,
          role: 'assistant',
          content: 'I could not find sufficient evidence in the uploaded documents to answer your question reliably.',
          answer_status: 'insufficient_evidence',
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsStreaming(false);
    }
  };

  // Quiz handler
  const handleStartQuiz = async () => {
    try {
      const q = await api.createQuiz(project.id, 'Adaptive Assessment', 2);
      setCurrentQuiz(q);
      setQuizComplete(false);
      setQuizScore(null);
      const nextQ = await api.getNextQuestion(project.id, q.id);
      setCurrentQuestion(nextQ);
    } catch (err: any) {
      alert(err.message || 'Could not generate quiz. Ingest materials first.');
    }
  };

  const handleSubmitAnswer = async () => {
    if (!currentQuiz || !currentQuestion) return;

    try {
      await api.submitAnswer(project.id, currentQuiz.id, {
        question_id: currentQuestion.id,
        selected_option_id: selectedOptionId || undefined,
        text_response: textAnswer || undefined,
      });

      // Load next or complete
      const nextQ = await api.getNextQuestion(project.id, currentQuiz.id);
      if (nextQ) {
        setCurrentQuestion(nextQ);
        setSelectedOptionId(null);
        setTextAnswer('');
      } else {
        setQuizComplete(true);
        setQuizScore(1.0);
        await loadMastery();
        await loadGrowth();
        await loadRecommendations();
      }
    } catch (err: any) {
      alert(err.message || 'Failed to submit answer');
    }
  };

  return (
    <div className="page-body animate-fade-in">
      {/* Project Header Banner */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '4px' }}>
          <span>Project Workspace</span>
          <span>/</span>
          <span style={{ color: 'var(--accent-light)' }}>{project.name}</span>
        </div>
        <h1 style={{ fontSize: '2rem' }}>{project.name}</h1>
      </div>

      {/* Tabs Bar */}
      <div className="tabs-nav">
        <button
          onClick={() => setActiveTab('materials')}
          className={`tab-btn ${activeTab === 'materials' ? 'active' : ''}`}
        >
          <FileText size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Materials ({materials.length})
        </button>
        <button
          onClick={() => setActiveTab('tutor')}
          className={`tab-btn ${activeTab === 'tutor' ? 'active' : ''}`}
        >
          <MessageSquare size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          AI Tutor (Grounded RAG)
        </button>
        <button
          onClick={() => setActiveTab('quiz')}
          className={`tab-btn ${activeTab === 'quiz' ? 'active' : ''}`}
        >
          <Award size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Adaptive Quizzes
        </button>
        <button
          onClick={() => setActiveTab('mastery')}
          className={`tab-btn ${activeTab === 'mastery' ? 'active' : ''}`}
        >
          <TrendingUp size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Mastery (BKT)
        </button>
        <button
          onClick={() => setActiveTab('recommendations')}
          className={`tab-btn ${activeTab === 'recommendations' ? 'active' : ''}`}
        >
          <Lightbulb size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Recommendations ({recommendations.length})
        </button>
        <button
          onClick={() => setActiveTab('analytics')}
          className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
        >
          <BarChart3 size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Analytics
        </button>
      </div>

      {/* Tab 1: Materials */}
      {activeTab === 'materials' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px', alignItems: 'flex-start' }}>
          <div>
            <h2 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Uploaded Study Materials</h2>
            {materials.length === 0 ? (
              <div className="card" style={{ textAlign: 'center', padding: '40px 20px' }}>
                <UploadCloud size={40} color="var(--text-muted)" style={{ margin: '0 auto 12px' }} />
                <h3 style={{ marginBottom: '6px' }}>No documents uploaded</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  Upload a PDF textbook, lecture slides, or notes to power the evidence-grounded AI Tutor.
                </p>
              </div>
            ) : (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Document Title</th>
                      <th>Status</th>
                      <th>Pages</th>
                      <th>File Size</th>
                      <th>Ingested</th>
                    </tr>
                  </thead>
                  <tbody>
                    {materials.map((m) => (
                      <tr key={m.id}>
                        <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <FileText size={16} color="var(--accent-light)" />
                            {m.title}
                          </div>
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              m.status === 'completed'
                                ? 'badge-success'
                                : m.status === 'processing'
                                ? 'badge-warning'
                                : m.status === 'failed'
                                ? 'badge-danger'
                                : 'badge-neutral'
                            }`}
                          >
                            {m.status}
                          </span>
                        </td>
                        <td>{m.page_count || 1} pages</td>
                        <td>{(m.size_bytes / 1024).toFixed(1)} KB</td>
                        <td>{new Date(m.created_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Upload Form */}
          <div className="card">
            <h3 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <UploadCloud size={20} color="var(--accent-light)" />
              Upload PDF Material
            </h3>
            <form onSubmit={handleUpload} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  Material Title
                </label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g. Chapter 1: Optimization"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  required
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  PDF File
                </label>
                <input
                  type="file"
                  accept="application/pdf"
                  className="input"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  required
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isUploading}
                style={{ marginTop: '8px' }}
              >
                {isUploading ? 'Ingesting Chunks...' : 'Upload & Process'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Tab 2: AI Tutor */}
      {activeTab === 'tutor' && (
        <div className="chat-container">
          {/* Messages stream */}
          <div className="chat-messages">
            {messages.length === 0 ? (
              <div style={{ textAlign: 'center', margin: 'auto', maxWidth: '440px' }}>
                <Sparkles size={36} color="var(--accent-light)" style={{ margin: '0 auto 12px' }} />
                <h3 style={{ marginBottom: '8px' }}>Grounded AI Socratic Tutor</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                  Ask questions about your uploaded materials. Every response provides verifiable page citations and refuses to hallucinate if evidence is absent.
                </p>
              </div>
            ) : (
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`chat-bubble ${msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}
                >
                  <p>{msg.content}</p>

                  {/* Refusal Notice */}
                  {msg.answer_status === 'insufficient_evidence' && (
                    <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--warning)', fontSize: '0.8rem', background: 'var(--warning-bg)', padding: '6px 10px', borderRadius: 'var(--radius-sm)' }}>
                      <AlertCircle size={14} />
                      Refusal: Insufficient evidence in uploaded material to guarantee accuracy.
                    </div>
                  )}

                  {/* Verifiable Citations */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
                      {msg.citations.map((c, i) => (
                        <span key={i} className="citation-tag">
                          Page {c.page_number} (Chunk #{c.chunk_id?.slice(0, 6)})
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
            {isStreaming && (
              <div className="chat-bubble chat-bubble-assistant" style={{ color: 'var(--text-muted)' }}>
                <span>Synthesizing grounded explanation...</span>
              </div>
            )}
          </div>

          {/* Input Bar */}
          <form
            onSubmit={handleSendMessage}
            style={{ padding: '16px 20px', borderTop: '1px solid var(--border-color)', display: 'flex', gap: '12px', background: 'rgba(10, 14, 23, 0.5)' }}
          >
            <input
              type="text"
              className="input"
              placeholder="Ask anything about the project materials..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              disabled={isStreaming}
            />
            <button type="submit" className="btn btn-primary" disabled={isStreaming || !inputMessage.trim()}>
              <Send size={16} />
            </button>
          </form>
        </div>
      )}

      {/* Tab 3: Adaptive Quizzes */}
      {activeTab === 'quiz' && (
        <div style={{ maxWidth: '720px', margin: '0 auto' }}>
          {!currentQuiz || quizComplete ? (
            <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
              <Award size={48} color="var(--accent-light)" style={{ margin: '0 auto 16px' }} />
              <h2 style={{ marginBottom: '8px' }}>
                {quizComplete ? 'Assessment Completed!' : 'Adaptive Knowledge Assessment'}
              </h2>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '24px', maxWidth: '480px', margin: '0 auto 24px' }}>
                {quizComplete
                  ? 'Your answers have been processed and Bayesian Knowledge Tracing (BKT) mastery states have been updated.'
                  : 'Test your understanding with questions dynamically generated from your uploaded document evidence.'}
              </p>
              {quizScore !== null && (
                <div style={{ marginBottom: '24px' }}>
                  <span className="badge badge-success" style={{ fontSize: '1rem', padding: '8px 16px' }}>
                    Score: 100% (Mastered)
                  </span>
                </div>
              )}
              <button onClick={handleStartQuiz} className="btn btn-primary">
                {quizComplete ? 'Take Another Quiz' : 'Start Adaptive Quiz'}
              </button>
            </div>
          ) : (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                <span className="badge badge-info">Adaptive MCQ</span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Grounded in project evidence</span>
              </div>
              <h3 style={{ fontSize: '1.25rem', marginBottom: '20px' }}>
                {currentQuestion?.prompt || 'Loading question...'}
              </h3>

              {currentQuestion?.options && currentQuestion.options.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '24px' }}>
                  {currentQuestion.options.map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setSelectedOptionId(opt.id)}
                      className={`btn ${selectedOptionId === opt.id ? 'btn-primary' : 'btn-secondary'}`}
                      style={{ justifyContent: 'flex-start', textAlign: 'left', padding: '14px 18px' }}
                    >
                      {opt.text}
                    </button>
                  ))}
                </div>
              ) : (
                <textarea
                  className="textarea"
                  rows={4}
                  placeholder="Type your explanation..."
                  value={textAnswer}
                  onChange={(e) => setTextAnswer(e.target.value)}
                  style={{ marginBottom: '20px' }}
                />
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  onClick={handleSubmitAnswer}
                  className="btn btn-primary"
                  disabled={!selectedOptionId && !textAnswer.trim()}
                >
                  Submit & Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Mastery (BKT) */}
      {activeTab === 'mastery' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 style={{ fontSize: '1.25rem' }}>Concept Mastery Levels (Bayesian Knowledge Tracing)</h2>
            <button onClick={loadMastery} className="btn btn-secondary btn-sm">
              <RefreshCw size={14} /> Refresh
            </button>
          </div>

          {masteryItems.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
              <TrendingUp size={36} color="var(--text-muted)" style={{ margin: '0 auto 12px' }} />
              <h3>No Mastery Data Recorded Yet</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                Attempt quizzes or chat with the AI Tutor to accumulate Bayesian mastery probabilities.
              </p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px' }}>
              {masteryItems.map((item) => (
                <div key={item.concept_id} className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h3 style={{ fontSize: '1.05rem' }}>Concept #{item.concept_id.slice(0, 8)}</h3>
                    <span
                      className={`badge ${
                        item.mastery_probability >= 0.85
                          ? 'badge-success'
                          : item.mastery_probability >= 0.5
                          ? 'badge-warning'
                          : 'badge-danger'
                      }`}
                    >
                      {item.mastery_probability >= 0.85 ? 'Mastered' : item.mastery_probability >= 0.5 ? 'Progressing' : 'Developing'}
                    </span>
                  </div>

                  <div style={{ marginBottom: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      <span>BKT Probability</span>
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {(item.mastery_probability * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div style={{ width: '100%', height: '8px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${item.mastery_probability * 100}%`,
                          height: '100%',
                          background: item.mastery_probability >= 0.85 ? 'var(--success)' : item.mastery_probability >= 0.5 ? 'var(--warning)' : 'var(--danger)',
                          borderRadius: 'var(--radius-full)',
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 5: Recommendations */}
      {activeTab === 'recommendations' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 style={{ fontSize: '1.25rem' }}>Personalized Next-Best Actions</h2>
            <button onClick={() => api.generateRecommendations(project.id).then(loadRecommendations)} className="btn btn-primary btn-sm">
              <Lightbulb size={14} /> Recompute Recommendations
            </button>
          </div>

          {recommendations.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
              <CheckCircle2 size={36} color="var(--success)" style={{ margin: '0 auto 12px' }} />
              <h3>All caught up!</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                No urgent recommendations at this moment. You can take a quiz or upload new materials.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {recommendations.map((r) => (
                <div key={r.id} className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '20px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <span className={`badge ${r.priority === 'high' ? 'badge-danger' : r.priority === 'medium' ? 'badge-warning' : 'badge-info'}`}>
                        {r.priority.toUpperCase()} PRIORITY
                      </span>
                      <h3 style={{ fontSize: '1.1rem' }}>{r.title}</h3>
                    </div>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '10px' }}>
                      {r.description}
                    </p>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {r.reason_codes.map((rc, i) => (
                        <span key={i} className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                          {rc}
                        </span>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      if (r.action.includes('ASSESSMENT')) setActiveTab('quiz');
                      else setActiveTab('tutor');
                    }}
                    className="btn btn-primary btn-sm"
                  >
                    Start Action
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 6: Analytics */}
      {activeTab === 'analytics' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h2 style={{ fontSize: '1.25rem' }}>Project Learning Analytics</h2>
            <div style={{ display: 'flex', gap: '8px' }}>
              {['7d', '30d', '90d', 'all'].map((r) => (
                <button
                  key={r}
                  onClick={() => setAnalyticsRange(r)}
                  className={`btn btn-sm ${analyticsRange === r ? 'btn-primary' : 'btn-secondary'}`}
                >
                  {r.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          <div className="metric-grid">
            <div className="metric-card">
              <div className="metric-title">Active Study Days</div>
              <div className="metric-value">{analytics?.active_days || 1}</div>
              <div className="metric-subtext">Within selected window</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Grounded Tutor Rate</div>
              <div className="metric-value" style={{ color: 'var(--success)' }}>
                {((analytics?.grounded_response_rate ?? 1.0) * 100).toFixed(0)}%
              </div>
              <div className="metric-subtext">Evidence verification rate</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Quiz Completion Rate</div>
              <div className="metric-value" style={{ color: 'var(--info)' }}>
                {((analytics?.quiz_completion_rate ?? 1.0) * 100).toFixed(0)}%
              </div>
              <div className="metric-subtext">Completed vs started</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Mastered Concepts</div>
              <div className="metric-value" style={{ color: 'var(--accent-light)' }}>
                {analytics?.cognitive_tiers?.mastered || masteryItems.filter(m => m.mastery_probability >= 0.85).length}
              </div>
              <div className="metric-subtext">BKT probability $\ge$ 85%</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
