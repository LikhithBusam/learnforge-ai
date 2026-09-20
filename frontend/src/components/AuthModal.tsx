import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { LogIn, UserPlus, Eye, EyeOff, AlertCircle, Sparkles } from 'lucide-react';

export const AuthModal: React.FC = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login, register } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim();
    if (!cleanEmail || !cleanEmail.includes('@')) {
      setError('Please enter a valid email address.');
      return;
    }
    if (!password) {
      setError('Password is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      if (isLogin) {
        await login({ email: cleanEmail, password });
      } else {
        await register({
          email: cleanEmail,
          password,
          display_name: displayName.trim() || undefined,
        });
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const setDemoCredentials = (role: 'learner' | 'admin') => {
    setError(null);
    if (role === 'admin') {
      setEmail('admin@studycompanion.app');
      setPassword('AdminSecurePass123!');
    } else {
      setEmail('learner@studycompanion.app');
      setPassword('LearnerSecurePass123!');
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'radial-gradient(ellipse at 50% 15%, rgba(79, 70, 229, 0.08), transparent 60%), var(--bg-app)',
        padding: 'var(--space-6)',
      }}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: '420px',
          padding: 'var(--space-8) var(--space-6)',
          boxShadow: 'var(--shadow-lg)',
          borderColor: 'var(--border-default)',
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--accent-primary)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
              marginBottom: 'var(--space-3)',
              boxShadow: '0 0 16px var(--accent-subtle)',
            }}
          >
            <Sparkles size={22} />
          </div>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: 'var(--space-1)' }}>
            AI Study Companion
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem' }}>
            {isLogin
              ? 'Sign in to access your evidence-grounded workspace'
              : 'Create your account to begin adaptive learning'}
          </p>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: 'flex',
            background: 'var(--surface-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '3px',
            marginBottom: 'var(--space-5)',
          }}
        >
          <button
            type="button"
            onClick={() => {
              setIsLogin(true);
              setError(null);
            }}
            style={{
              flex: 1,
              height: '32px',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              background: isLogin ? 'var(--accent-primary)' : 'transparent',
              color: isLogin ? '#ffffff' : 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '0.8125rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setIsLogin(false);
              setError(null);
            }}
            style={{
              flex: 1,
              height: '32px',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              background: !isLogin ? 'var(--accent-primary)' : 'transparent',
              color: !isLogin ? '#ffffff' : 'var(--text-secondary)',
              fontWeight: 500,
              fontSize: '0.8125rem',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            Create Account
          </button>
        </div>

        {/* Error Alert Box */}
        {error && (
          <div className="alert alert-danger" role="alert" style={{ marginBottom: 'var(--space-4)' }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {!isLogin && (
            <div>
              <label htmlFor="auth-display-name" className="form-label">
                Full Name (Optional)
              </label>
              <input
                id="auth-display-name"
                type="text"
                className="input"
                placeholder="Alex Mercer"
                autoComplete="name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={isSubmitting}
              />
            </div>
          )}

          <div>
            <label htmlFor="auth-email" className="form-label">
              Email Address
            </label>
            <input
              id="auth-email"
              type="email"
              className="input"
              placeholder="alex@university.edu"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isSubmitting}
            />
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-1)' }}>
              <label htmlFor="auth-password" className="form-label" style={{ marginBottom: 0 }}>
                Password
              </label>
            </div>
            <div style={{ position: 'relative' }}>
              <input
                id="auth-password"
                type={showPassword ? 'text' : 'password'}
                className="input"
                style={{ paddingRight: '36px' }}
                placeholder="••••••••"
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                style={{
                  position: 'absolute',
                  right: '8px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: '4px',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg"
            disabled={isSubmitting}
            style={{ marginTop: 'var(--space-2)' }}
          >
            {isSubmitting ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                <span className="animate-spin" style={{ width: '14px', height: '14px', border: '2px solid #ffffff', borderTopColor: 'transparent', borderRadius: '50%' }} />
                {isLogin ? 'Signing In...' : 'Creating Account...'}
              </span>
            ) : isLogin ? (
              <>
                <LogIn size={16} /> Sign In
              </>
            ) : (
              <>
                <UserPlus size={16} /> Create Account
              </>
            )}
          </button>
        </form>

        {/* Fast Fill Demo Credentials */}
        <div style={{ marginTop: 'var(--space-6)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--border-subtle)', textAlign: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 'var(--space-2)' }}>
            Quick sign in with seeded credentials:
          </span>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button
              type="button"
              onClick={() => setDemoCredentials('learner')}
              className="btn btn-secondary btn-sm"
              style={{ flex: 1 }}
              disabled={isSubmitting}
            >
              Learner Account
            </button>
            <button
              type="button"
              onClick={() => setDemoCredentials('admin')}
              className="btn btn-secondary btn-sm"
              style={{ flex: 1 }}
              disabled={isSubmitting}
            >
              Admin Account
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
