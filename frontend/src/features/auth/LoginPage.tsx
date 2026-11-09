import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../lib/auth/AuthContext';
import { ApiException } from '../../lib/api/client';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { ThemeToggle } from '../../components/ui/ThemeToggle';

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export const LoginPage: React.FC = () => {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // If already logged in, redirect
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/groups';
  React.useEffect(() => {
    if (isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, from]);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
  });

  const onSubmit = async (data: LoginFormData) => {
    setErrorMessage(null);
    try {
      await login(data.email, data.password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.code === 'ACCOUNT_LOCKED') {
          setErrorMessage('Account locked due to 5 consecutive failed attempts. Try again in 15 minutes.');
        } else if (err.code === 'INVALID_CREDENTIALS') {
          setErrorMessage('Invalid email or password.');
        } else {
          setErrorMessage(err.message || 'Login failed. Please check credentials.');
        }
      } else {
        setErrorMessage('Unable to connect to service. Please check your network.');
      }
    }
  };

  const handleQuickFill = (email: string, pass: string) => {
    setValue('email', email, { shouldValidate: true });
    setValue('password', pass, { shouldValidate: true });
    setErrorMessage(null);
  };

  return (
    <div className="min-h-screen bg-[var(--surface-muted)] flex flex-col justify-between p-6">
      <header className="flex justify-between items-center max-w-5xl w-full mx-auto">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-[var(--primary)] text-[var(--surface)] flex items-center justify-center font-serif font-bold text-lg">
            S
          </div>
          <span className="font-serif font-semibold text-base text-[var(--ink)]">
            SHG Credit Manager
          </span>
        </div>
        <ThemeToggle />
      </header>

      <main className="flex-1 flex items-center justify-center py-12">
        <div className="w-full max-w-md bg-[var(--surface)] border border-[var(--border)] rounded p-8 shadow-sm">
          <div className="mb-6">
            <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
              Sign In
            </h1>
            <p className="text-sm text-[var(--muted-ink)] mt-1">
              Access the Self-Help Group Credit & Ledger Management System
            </p>
          </div>

          {errorMessage && (
            <div
              role="alert"
              className="mb-6 p-3 rounded bg-[var(--accent-subtle)] border border-[var(--danger)] text-xs text-[var(--danger)] font-medium flex items-center gap-2"
            >
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <Input
              label="Email Address"
              type="email"
              autoComplete="email"
              placeholder="e.g. leader@shg.org"
              error={errors.email?.message}
              {...register('email')}
            />

            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              error={errors.password?.message}
              {...register('password')}
            />

            <div className="pt-2">
              <Button
                type="submit"
                variant="primary"
                className="w-full justify-center"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Verifying...' : 'Sign In'}
              </Button>
            </div>
          </form>

          {/* Quick Seed Login Section */}
          <div className="mt-8 pt-6 border-t border-[var(--border)] text-xs">
            <p className="font-medium text-[var(--muted-ink)] mb-3 uppercase tracking-wider text-[10px]">
              Fast Login (Seed Profiles)
            </p>
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleQuickFill('admin@shg.org', 'AdminPass123!')}
              >
                Admin
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleQuickFill('leader@shg.org', 'LeaderPass123!')}
              >
                Group Leader
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleQuickFill('auditor@shg.org', 'AuditorPass123!')}
              >
                Auditor
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleQuickFill('member@shg.org', 'MemberPass123!')}
              >
                Member
              </Button>
            </div>
          </div>
        </div>
      </main>

      <footer className="text-center text-xs text-[var(--muted-ink)] py-4 font-mono">
        SHG Credit Manager · Tamper-evident ledger & group accounting
      </footer>
    </div>
  );
};
