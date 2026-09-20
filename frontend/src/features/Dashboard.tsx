import React, { useState } from 'react';
import { Space, Project } from '../types';
import { api } from '../services/api';
import {
  FolderPlus,
  Plus,
  BookOpen,
  ArrowRight,
  TrendingUp,
  Award,
  Sparkles,
  Layers,
} from 'lucide-react';

interface DashboardProps {
  spaces: Space[];
  projects: Project[];
  onSelectProject: (project: Project, view?: string) => void;
  onRefreshData: () => Promise<void>;
}

export const Dashboard: React.FC<DashboardProps> = ({
  spaces,
  projects,
  onSelectProject,
  onRefreshData,
}) => {
  const [isCreatingSpace, setIsCreatingSpace] = useState(false);
  const [newSpaceName, setNewSpaceName] = useState('');
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [selectedSpaceId, setSelectedSpaceId] = useState<string>('');

  const handleCreateSpace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSpaceName.trim()) return;
    try {
      await api.createSpace({ name: newSpaceName.trim() });
      setNewSpaceName('');
      setIsCreatingSpace(false);
      await onRefreshData();
    } catch (err: any) {
      alert(err.message || 'Failed to create space');
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim() || !selectedSpaceId) return;
    try {
      await api.createProject(selectedSpaceId, { name: newProjectName.trim() });
      setNewProjectName('');
      setIsCreatingProject(false);
      await onRefreshData();
    } catch (err: any) {
      alert(err.message || 'Failed to create project');
    }
  };

  return (
    <div className="page-body animate-fade-in">
      {/* Header Banner */}
      <div style={{ marginBottom: '32px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '2.25rem', marginBottom: '8px', background: 'linear-gradient(135deg, #fff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Learning Workspace
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1rem' }}>
            Select or create a study space and project to activate evidence-grounded AI learning.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={() => setIsCreatingSpace(true)} className="btn btn-secondary">
            <FolderPlus size={18} />
            New Space
          </button>
          <button
            onClick={() => {
              if (spaces.length > 0) {
                setSelectedSpaceId(spaces[0].id);
                setIsCreatingProject(true);
              } else {
                alert('Please create a Space first before adding a Project.');
              }
            }}
            className="btn btn-primary"
          >
            <Plus size={18} />
            New Project
          </button>
        </div>
      </div>

      {/* Overview Stat Cards */}
      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-title">Study Spaces</div>
          <div className="metric-value" style={{ color: 'var(--accent-light)' }}>{spaces.length}</div>
          <div className="metric-subtext">Active domain containers</div>
        </div>
        <div className="metric-card">
          <div className="metric-title">Total Projects</div>
          <div className="metric-value" style={{ color: 'var(--info)' }}>{projects.length}</div>
          <div className="metric-subtext">Scoped learning sandboxes</div>
        </div>
        <div className="metric-card">
          <div className="metric-title">AI Grounding Level</div>
          <div className="metric-value" style={{ color: 'var(--success)' }}>100%</div>
          <div className="metric-subtext">Zero hallucination citation guarantee</div>
        </div>
        <div className="metric-card">
          <div className="metric-title">Mastery Algorithm</div>
          <div className="metric-value" style={{ color: 'var(--warning)' }}>BKT</div>
          <div className="metric-subtext">Deterministic Bayesian model</div>
        </div>
      </div>

      {/* Create Space Form Modal */}
      {isCreatingSpace && (
        <div className="card" style={{ marginBottom: '24px', border: '1px solid var(--accent)' }}>
          <h3 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FolderPlus size={20} color="var(--accent-light)" />
            Create Study Space
          </h3>
          <form onSubmit={handleCreateSpace} style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <input
              type="text"
              className="input"
              placeholder="e.g. Computer Science & AI"
              value={newSpaceName}
              onChange={(e) => setNewSpaceName(e.target.value)}
              autoFocus
              required
            />
            <button type="submit" className="btn btn-primary">Create</button>
            <button type="button" onClick={() => setIsCreatingSpace(false)} className="btn btn-secondary">Cancel</button>
          </form>
        </div>
      )}

      {/* Create Project Form Modal */}
      {isCreatingProject && (
        <div className="card" style={{ marginBottom: '24px', border: '1px solid var(--accent)' }}>
          <h3 style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Plus size={20} color="var(--accent-light)" />
            Create Learning Project
          </h3>
          <form onSubmit={handleCreateProject} style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              className="select"
              style={{ width: '220px' }}
              value={selectedSpaceId}
              onChange={(e) => setSelectedSpaceId(e.target.value)}
            >
              {spaces.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
            <input
              type="text"
              className="input"
              style={{ flex: 1, minWidth: '240px' }}
              placeholder="e.g. Machine Learning Foundations"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              autoFocus
              required
            />
            <button type="submit" className="btn btn-primary">Create</button>
            <button type="button" onClick={() => setIsCreatingProject(false)} className="btn btn-secondary">Cancel</button>
          </form>
        </div>
      )}

      {/* Active Projects Grid */}
      <h2 style={{ fontSize: '1.35rem', marginBottom: '16px' }}>Your Learning Projects</h2>
      {projects.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <Layers size={40} color="var(--text-muted)" style={{ margin: '0 auto 16px' }} />
          <h3 style={{ marginBottom: '8px' }}>No Projects Created Yet</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '20px', maxWidth: '480px', margin: '0 auto 20px' }}>
            Spaces hold projects, and projects hold materials, AI tutor conversations, and mastery tracking.
          </p>
          <button
            onClick={() => {
              if (spaces.length === 0) setIsCreatingSpace(true);
              else {
                setSelectedSpaceId(spaces[0].id);
                setIsCreatingProject(true);
              }
            }}
            className="btn btn-primary"
          >
            <Plus size={18} />
            {spaces.length === 0 ? 'Create Your First Space' : 'Create Your First Project'}
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '20px' }}>
          {projects.map((proj) => (
            <div key={proj.id} className="card card-interactive" style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '10px', background: 'rgba(99, 102, 241, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <BookOpen size={20} color="var(--accent-light)" />
                </div>
                <span className="badge badge-info">Active</span>
              </div>
              <h3 style={{ fontSize: '1.2rem', marginBottom: '6px' }}>{proj.name}</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', flex: 1, marginBottom: '20px' }}>
                Context-scoped RAG materials, adaptive quizzes, and BKT mastery analytics.
              </p>

              {/* Quick Actions inside card */}
              <div style={{ display: 'flex', gap: '8px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                <button
                  onClick={() => onSelectProject(proj, 'tutor')}
                  className="btn btn-primary btn-sm"
                  style={{ flex: 1 }}
                >
                  <Sparkles size={14} />
                  AI Tutor
                </button>
                <button
                  onClick={() => onSelectProject(proj, 'materials')}
                  className="btn btn-secondary btn-sm"
                  style={{ flex: 1 }}
                >
                  Materials
                </button>
                <button
                  onClick={() => onSelectProject(proj, 'overview')}
                  className="btn btn-secondary btn-sm"
                  title="Open Project"
                >
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
