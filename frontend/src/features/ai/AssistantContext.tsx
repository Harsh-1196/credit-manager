import React, { createContext, useContext, useState, useCallback } from 'react';

interface AssistantContextType {
  isOpen: boolean;
  openAssistant: (initialPrompt?: string) => void;
  closeAssistant: () => void;
  toggleAssistant: () => void;
  activeShgId: string | null;
  setActiveShgId: (id: string | null) => void;
  initialPrompt: string | null;
  clearInitialPrompt: () => void;
}

const AssistantContext = createContext<AssistantContextType | undefined>(undefined);

export const AssistantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeShgId, setActiveShgId] = useState<string | null>(null);
  const [initialPrompt, setInitialPrompt] = useState<string | null>(null);

  const openAssistant = useCallback((prompt?: string) => {
    if (prompt) {
      setInitialPrompt(prompt);
    }
    setIsOpen(true);
  }, []);

  const closeAssistant = useCallback(() => {
    setIsOpen(false);
  }, []);

  const toggleAssistant = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const clearInitialPrompt = useCallback(() => {
    setInitialPrompt(null);
  }, []);

  return (
    <AssistantContext.Provider
      value={{
        isOpen,
        openAssistant,
        closeAssistant,
        toggleAssistant,
        activeShgId,
        setActiveShgId,
        initialPrompt,
        clearInitialPrompt,
      }}
    >
      {children}
    </AssistantContext.Provider>
  );
};

export function useAssistant(): AssistantContextType {
  const context = useContext(AssistantContext);
  if (!context) {
    throw new Error('useAssistant must be used within an AssistantProvider');
  }
  return context;
}
