import React, { useState, useEffect } from 'react';
import {
  AdminOverview,
  AdminSystemHealth,
  AdminAIUsage,
  AdminJobExecution,
  AdminAuditLog,
  User,
} from '../types';
import { api } from '../services/api';
import {
  ShieldAlert,
  Activity,
  Users,
  Server,
  Cpu,
  Clock,
  Layers,
  Search,
  CheckCircle2,
  AlertTriangle,
  FileWarning,
} from 'lucide-react';

export const AdminDashboard: React.FC = () => {
  const [activeAdminTab, setActiveAdminTab] = useState('overview');
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [health, setHealth] = useState<AdminSystemHealth | null>(null);
  const [aiUsage, setAiUsage] = useState<AdminAIUsage | null>(null);
  const [jobs, setJobs] = useState<AdminJobExecution[]>([]);
  const [auditLogs, setAuditLogs] = useState<AdminAuditLog[]>([]);
  const [usersList, setUsersList] = useState<User[]>([]);
  const [userSearch, setUserSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadAdminData = async () => {
    setIsLoading(true);
    try {
      const [ov, h, ai, j, a, u] = await Promise.all([
        api.getAdminOverview().catch(() => null),
        api.getAdminHealth().catch(() => null),
        api.getAdminAIUsage().catch(() => null),
        api.getAdminJobs(20).catch(() => ({ recent_executions: [] })),
        api.getAdminAuditLogs(1, 20).catch(() => ({ items: [] })),
        api.getAdminUsers(1, 20).catch(() => ({ items: [] })),
      ]);

      if (ov) setOverview(ov);
      if (h) setHealth(h);
      if (ai) setAiUsage(ai);
      if (j?.recent_executions) setJobs(j.recent_executions);
      if (a?.items) setAuditLogs(a.items);
      if (u?.items) setUsersList(u.items);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAdminData();
  }, []);

  return (
    <div className="page-body animate-fade-in">
      {/* Admin Title Banner */}
      <div style={{ marginBottom: '28px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--danger)', fontSize: '0.875rem', fontWeight: 600, marginBottom: '4px' }}>
            <ShieldAlert size={16} />
            Privileged Operational Console
          </div>
          <h1 style={{ fontSize: '2.25rem' }}>Admin & System Observability</h1>
        </div>
        <button onClick={loadAdminData} className="btn btn-secondary btn-sm">
          Refresh Live Data
        </button>
      </div>

      {/* Admin Tabs */}
      <div className="tabs-nav">
        <button
          onClick={() => setActiveAdminTab('overview')}
          className={`tab-btn ${activeAdminTab === 'overview' ? 'active' : ''}`}
        >
          <Activity size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          System Overview
        </button>
        <button
          onClick={() => setActiveAdminTab('users')}
          className={`tab-btn ${activeAdminTab === 'users' ? 'active' : ''}`}
        >
          <Users size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          User Management
        </button>
        <button
          onClick={() => setActiveAdminTab('ai')}
          className={`tab-btn ${activeAdminTab === 'ai' ? 'active' : ''}`}
        >
          <Cpu size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          AI Gateway & Costs
        </button>
        <button
          onClick={() => setActiveAdminTab('jobs')}
          className={`tab-btn ${activeAdminTab === 'jobs' ? 'active' : ''}`}
        >
          <Clock size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Background Jobs
        </button>
        <button
          onClick={() => setActiveAdminTab('audit')}
          className={`tab-btn ${activeAdminTab === 'audit' ? 'active' : ''}`}
        >
          <Layers size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
          Audit Trail
        </button>
      </div>

      {/* Tab: Overview & Health */}
      {activeAdminTab === 'overview' && (
        <div>
          {/* Dependency Health Grid */}
          <h2 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Dependency Health Checks</h2>
          <div className="metric-grid" style={{ marginBottom: '32px' }}>
            {health?.components &&
              Object.entries(health.components).map(([key, value]) => {
                const isHealthy = value.status === 'ok' || value.status === 'healthy';
                return (
                  <div key={key} className="metric-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div className="metric-title">{key}</div>
                      {isHealthy ? (
                        <CheckCircle2 size={16} color="var(--success)" />
                      ) : (
                        <AlertTriangle size={16} color="var(--warning)" />
                      )}
                    </div>
                    <div className="metric-value" style={{ fontSize: '1.25rem', color: isHealthy ? 'var(--success)' : 'var(--warning)', textTransform: 'capitalize' }}>
                      {value.status}
                    </div>
                    <div className="metric-subtext">Automated readiness probe</div>
                  </div>
                );
              })}
          </div>

          {/* Core Platform Counters */}
          <h2 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Platform Entities</h2>
          <div className="metric-grid">
            <div className="metric-card">
              <div className="metric-title">Registered Users</div>
              <div className="metric-value">{overview?.users?.total || 0}</div>
              <div className="metric-subtext">{overview?.users?.active || 0} active, {overview?.users?.admins || 0} admins</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Total Spaces</div>
              <div className="metric-value">{overview?.spaces?.total || 0}</div>
              <div className="metric-subtext">Isolated workspaces</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Total Projects</div>
              <div className="metric-value">{overview?.projects?.total || 0}</div>
              <div className="metric-subtext">Learning contexts</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Materials Status</div>
              <div className="metric-value" style={{ color: 'var(--success)' }}>{overview?.materials?.ready || 0}</div>
              <div className="metric-subtext">Ready ({overview?.materials?.processing || 0} processing, {overview?.materials?.failed || 0} failed)</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Users */}
      {activeAdminTab === 'users' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '1.25rem' }}>Platform User Directory</h2>
            <div style={{ width: '280px', position: 'relative' }}>
              <input
                type="text"
                className="input"
                placeholder="Search users..."
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
              />
            </div>
          </div>

          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>Email</th>
                  <th>Display Name</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {usersList
                  .filter((u) => !userSearch || u.email.includes(userSearch) || (u.display_name && u.display_name.includes(userSearch)))
                  .map((u) => (
                    <tr key={u.id}>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{u.id.slice(0, 8)}...</td>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{u.email}</td>
                      <td>{u.display_name || '—'}</td>
                      <td>
                        <span className={`badge ${u.role === 'admin' ? 'badge-danger' : 'badge-info'}`}>
                          {u.role}
                        </span>
                      </td>
                      <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: AI Usage */}
      {activeAdminTab === 'ai' && (
        <div>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>AI Gateway Telemetry & Costs</h2>
          <div className="metric-grid">
            <div className="metric-card">
              <div className="metric-title">Total AI Calls</div>
              <div className="metric-value">{aiUsage?.total_requests || 0}</div>
              <div className="metric-subtext">{aiUsage?.failed_requests || 0} failed requests</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Total Tokens</div>
              <div className="metric-value">
                {((aiUsage?.total_input_tokens || 0) + (aiUsage?.total_output_tokens || 0)).toLocaleString()}
              </div>
              <div className="metric-subtext">In: {aiUsage?.total_input_tokens || 0} / Out: {aiUsage?.total_output_tokens || 0}</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Avg Gateway Latency</div>
              <div className="metric-value">{aiUsage?.avg_latency_ms || 0} ms</div>
              <div className="metric-subtext">End-to-end response time</div>
            </div>
            <div className="metric-card">
              <div className="metric-title">Estimated Cost</div>
              <div className="metric-value" style={{ color: 'var(--warning)' }}>
                ${aiUsage?.estimated_cost_usd?.toFixed(4) || '0.0000'}
              </div>
              <div className="metric-subtext">USD model usage cost</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Background Jobs */}
      {activeAdminTab === 'jobs' && (
        <div>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Celery Background Tasks</h2>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Task Name</th>
                  <th>Queue</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Attempt</th>
                  <th>Executed At</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '24px' }}>
                      No background job records found.
                    </td>
                  </tr>
                ) : (
                  jobs.map((j) => (
                    <tr key={j.id}>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{j.task_name}</td>
                      <td><span className="badge badge-neutral">{j.queue}</span></td>
                      <td>
                        <span className={`badge ${j.status === 'SUCCEEDED' ? 'badge-success' : 'badge-danger'}`}>
                          {j.status}
                        </span>
                      </td>
                      <td>{j.duration_ms ? `${j.duration_ms} ms` : '—'}</td>
                      <td>#{j.attempt}</td>
                      <td>{new Date(j.created_at).toLocaleTimeString()}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Audit Log */}
      {activeAdminTab === 'audit' && (
        <div>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Administrative Audit Log Trail</h2>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Timestamp (UTC)</th>
                  <th>Action</th>
                  <th>Target Type</th>
                  <th>Target ID</th>
                  <th>Actor Role</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '24px' }}>
                      No audit log records found.
                    </td>
                  </tr>
                ) : (
                  auditLogs.map((a) => (
                    <tr key={a.id}>
                      <td>{new Date(a.occurred_at).toLocaleString()}</td>
                      <td style={{ fontWeight: 600, color: 'var(--accent-light)' }}>{a.action}</td>
                      <td><span className="badge badge-neutral">{a.target_type}</span></td>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{a.target_id || '—'}</td>
                      <td><span className="badge badge-info">{a.actor_role}</span></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
