import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, setOnUnauthorized } from '../api/client';
import type { MeResponse, UserRole } from '../api/types';

interface AuthContextType {
  user: MeResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  hasRole: (...roles: UserRole[]) => boolean;
  hasGroupAccess: (groupId: string) => boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      // Ignore errors on logout
    } finally {
      setUser(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await api.auth.me();
      setUser(profile);
    } catch {
      setUser(null);
    }
  }, []);

  const login = async (email: string, password: string) => {
    await api.auth.login({ email, password });
    const profile = await api.auth.me();
    setUser(profile);
  };

  useEffect(() => {
    // Setup 401 callback to log out cleanly
    setOnUnauthorized(() => {
      setUser(null);
    });

    // Initial session bootstrap: try silent refresh via cookie
    const initSession = async () => {
      try {
        await api.auth.refresh();
        const profile = await api.auth.me();
        setUser(profile);
      } catch {
        // No active session or cookie expired
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    initSession();
  }, []);

  const hasRole = useCallback((...roles: UserRole[]) => {
    if (!user) return false;
    return roles.includes(user.role);
  }, [user]);

  const hasGroupAccess = useCallback((groupId: string) => {
    if (!user) return false;
    if (user.role === 'ADMIN') return true;
    return user.group_access.some((g) => g.group_id === groupId);
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
        refreshProfile,
        hasRole,
        hasGroupAccess,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
