import { createBrowserRouter, Navigate } from 'react-router-dom';
import { LoginPage } from '../features/auth/LoginPage';
import { ProtectedRoute } from '../lib/auth/ProtectedRoute';
import { AppLayout } from '../components/layout/AppLayout';
import { GroupsListPage } from '../features/groups/GroupsListPage';
import { GroupDetailPage } from '../features/groups/GroupDetailPage';
import { MembersListPage } from '../features/members/MembersListPage';
import { MemberDetailPage } from '../features/members/MemberDetailPage';
import { UsersListPage } from '../features/users/UsersListPage';
import { AuditLogPage } from '../features/audit/AuditLogPage';
import { StyleguidePage } from '../features/styleguide/StyleguidePage';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            path: '/',
            element: <Navigate to="/groups" replace />,
          },
          {
            path: '/groups',
            element: <GroupsListPage />,
          },
          {
            path: '/groups/:id',
            element: <GroupDetailPage />,
          },
          {
            path: '/members',
            element: <MembersListPage />,
          },
          {
            path: '/members/:id',
            element: <MemberDetailPage />,
          },
          {
            path: '/users',
            element: <ProtectedRoute allowedRoles={['ADMIN']} />,
            children: [
              {
                path: '',
                element: <UsersListPage />,
              },
            ],
          },
          {
            path: '/audit',
            element: <ProtectedRoute allowedRoles={['ADMIN', 'AUDITOR']} />,
            children: [
              {
                path: '',
                element: <AuditLogPage />,
              },
            ],
          },
          {
            path: '/styleguide',
            element: <StyleguidePage />,
          },
        ],
      },
    ],
  },
  {
    path: '*',
    element: (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center bg-[var(--surface-muted)] text-[var(--ink)]">
        <h1 className="font-serif text-3xl font-bold">404 - Page Not Found</h1>
        <p className="mt-2 text-xs text-[var(--muted-ink)]">
          The requested page or route does not exist.
        </p>
        <a
          href="/"
          className="mt-4 inline-flex items-center text-xs font-semibold text-[var(--primary)] hover:underline"
        >
          Return to Dashboard
        </a>
      </div>
    ),
  },
]);
