import React from 'react';
import {
  LayoutDashboard,
  FolderKanban,
  FileText,
  MessageSquare,
  Award,
  TrendingUp,
  Lightbulb,
  BarChart3,
  ShieldAlert,
  LogOut,
  UserCheck,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Project } from '../types';

interface NavigationProps {
  currentView: string;
  onNavigate: (view: string) => void;
  projects: Project[];
  selectedProject: Project | null;
  onSelectProject: (project: Project) => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  currentView,
  onNavigate,
  projects,
  selectedProject,
  onSelectProject,
}) => {
  const { user, logout, isAdmin } = useAuth();

  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div style={{ padding: '24px 20px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'linear-gradient(135deg, var(--accent), var(--accent-secondary))', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 'bold', fontSize: '18px' }}>
          AI
        </div>
        <div>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, lineHeight: 1.2 }}>StudyCompanion</h2>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>AI Learning Workspace</span>
        </div>
      </div>

      {/* Project Selector */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-color)' }}>
        <label style={{ fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>
          Active Project
        </label>
        <select
          className="select"
          value={selectedProject?.id || ''}
          onChange={(e) => {
            const p = projects.find((item) => item.id === e.target.value);
            if (p) onSelectProject(p);
          }}
          disabled={projects.length === 0}
        >
          {projects.length === 0 ? (
            <option value="">No projects available</option>
          ) : (
            projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))
          )}
        </select>
      </div>

      {/* Nav Menu */}
      <nav style={{ flex: 1, padding: '16px 12px', display: 'flex', flexDirection: 'column', gap: '4px', overflowY: 'auto' }}>
        <button
          onClick={() => onNavigate('dashboard')}
          className={`btn ${currentView === 'dashboard' ? 'btn-primary' : 'btn-secondary'}`}
          style={{ justifyContent: 'flex-start', border: 'none' }}
        >
          <LayoutDashboard size={18} />
          Dashboard
        </button>

        {selectedProject && (
          <>
            <div style={{ fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', margin: '16px 8px 6px' }}>
              Learning Tools
            </div>

            <button
              onClick={() => onNavigate('materials')}
              className={`btn ${currentView === 'materials' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none' }}
            >
              <FileText size={18} />
              Materials
            </button>

            <button
              onClick={() => onNavigate('tutor')}
              className={`btn ${currentView === 'tutor' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none' }}
            >
              <MessageSquare size={18} />
              AI Tutor
            </button>

            <button
              onClick={() => onNavigate('quiz')}
              className={`btn ${currentView === 'quiz' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none' }}
            >
              <Award size={18} />
              Quizzes
            </button>

            <button
              onClick={() => onNavigate('mastery')}
              className={`btn ${currentView === 'mastery' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none' }}
            >
              <TrendingUp size={18} />
              Mastery (BKT)
            </button>

            <button
              onClick={() => onNavigate('recommendations')}
              className={`btn ${currentView === 'recommendations' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none' }}
            >
              <Lightbulb size={18} />
              Recommendations
            </button>

            <button
              onClick={() => onNavigate('analytics')}
              className={`btn ${currentView === 'analytics' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none' }}
            >
              <BarChart3 size={18} />
              Analytics
            </button>
          </>
        )}

        {isAdmin && (
          <>
            <div style={{ fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', margin: '16px 8px 6px' }}>
              Operations
            </div>

            <button
              onClick={() => onNavigate('admin')}
              className={`btn ${currentView === 'admin' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ justifyContent: 'flex-start', border: 'none', color: '#f43f5e' }}
            >
              <ShieldAlert size={18} />
              Admin Portal
            </button>
          </>
        )}
      </nav>

      {/* User Footer */}
      <div style={{ padding: '16px', borderTop: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
          <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(255, 255, 255, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <UserCheck size={16} color="var(--accent-light)" />
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {user?.display_name || user?.email}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
              {user?.role}
            </div>
          </div>
        </div>
        <button onClick={logout} title="Logout" style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '6px' }}>
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  );
};
