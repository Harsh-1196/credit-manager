import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { CommandPalette } from './CommandPalette';
import { AssistantProvider } from '../../features/ai/AssistantContext';
import { AssistantDrawer } from '../../features/ai/AssistantDrawer';

export const AppLayout: React.FC = () => {
  return (
    <AssistantProvider>
      <div className="min-h-screen flex bg-[var(--surface-muted)]">
        <CommandPalette />
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <main className="flex-1 p-6 overflow-y-auto">
            <Outlet />
          </main>
        </div>
        <AssistantDrawer />
      </div>
    </AssistantProvider>
  );
};
