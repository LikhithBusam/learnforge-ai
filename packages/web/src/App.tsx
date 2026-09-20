import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Navigation } from './components/Navigation';
import { AuthModal } from './components/AuthModal';
import { Dashboard } from './features/Dashboard';
import { ProjectWorkspace } from './features/ProjectWorkspace';
import { AdminDashboard } from './features/AdminDashboard';
import { Space, Project } from './types';
import { api } from './services/api';

const AppContent: React.FC = () => {
  const { user, isLoading, isAdmin } = useAuth();
  const [currentView, setCurrentView] = useState<string>('dashboard');
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  const loadWorkspaceData = async () => {
    if (!user) return;
    try {
      const [spaceRes, projRes] = await Promise.all([
        api.listSpaces().catch(() => ({ items: [], total: 0 })),
        api.listProjects().catch(() => ({ items: [], total: 0 })),
      ]);
      setSpaces(spaceRes.items || []);
      setProjects(projRes.items || []);
      if (projRes.items && projRes.items.length > 0 && !selectedProject) {
        setSelectedProject(projRes.items[0]);
      }
    } catch {
      // tolerate initial empty
    }
  };

  useEffect(() => {
    loadWorkspaceData();
  }, [user]);

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-primary)' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ width: '40px', height: '40px', border: '3px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 16px' }} />
          <p style={{ color: 'var(--text-secondary)' }}>Loading Study Companion...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <AuthModal />;
  }

  const handleSelectProject = (project: Project, view: string = 'materials') => {
    setSelectedProject(project);
    setCurrentView(view);
  };

  return (
    <div className="app-container">
      <Navigation
        currentView={currentView}
        onNavigate={(view) => setCurrentView(view)}
        projects={projects}
        selectedProject={selectedProject}
        onSelectProject={(p) => setSelectedProject(p)}
      />

      <main className="main-content">
        {currentView === 'dashboard' && (
          <Dashboard
            spaces={spaces}
            projects={projects}
            onSelectProject={handleSelectProject}
            onRefreshData={loadWorkspaceData}
          />
        )}

        {currentView === 'admin' && isAdmin && <AdminDashboard />}

        {['overview', 'materials', 'tutor', 'quiz', 'mastery', 'recommendations', 'analytics'].includes(currentView) && (
          selectedProject ? (
            <ProjectWorkspace
              project={selectedProject}
              initialTab={currentView === 'overview' ? 'materials' : currentView}
            />
          ) : (
            <Dashboard
              spaces={spaces}
              projects={projects}
              onSelectProject={handleSelectProject}
              onRefreshData={loadWorkspaceData}
            />
          )
        )}
      </main>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
