import React, { useState, useEffect } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { ChatProvider, useChat } from './context/ChatContext';
import { UploadProvider } from './context/UploadContext';
import { Sidebar, Header, ChatArea, DocumentLibrary } from './components';
import { UploadTray } from './components/UploadTray';
import { AlertCircle, X, CheckCircle, Info } from 'lucide-react';
import { getApiBaseUrl } from './services/api';

const AppContent: React.FC = () => {
  const { currentPage, isBackendConnected, toasts, removeToast, startNewDraft, setCurrentPage } = useChat();

  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('sidebar') === 'closed') return true;
      if (params.get('sidebar') === 'open') return false;
      return (
        localStorage.getItem('rag_qa_sidebar_collapsed') === 'true' ||
        localStorage.getItem('doc_chat_sidebar_collapsed') === 'true'
      );
    } catch {
      return false;
    }
  });

  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScrollCapture = (e: Event) => {
      const target = e.target as HTMLElement;
      if (target && target.classList && target.classList.contains('overflow-y-auto')) {
        setIsScrolled(target.scrollTop > 0);
      }
    };
    window.addEventListener('scroll', handleScrollCapture, { capture: true, passive: true });
    return () => window.removeEventListener('scroll', handleScrollCapture, { capture: true });
  }, []);

  const handleToggleCollapse = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('rag_qa_sidebar_collapsed', String(next));
        localStorage.setItem('doc_chat_sidebar_collapsed', String(next));
      } catch { }
      return next;
    });
  };

  // Keyboard shortcut: Ctrl/Cmd + Shift + O (New Chat), Ctrl/Cmd + B (Toggle Sidebar), Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault();
        startNewDraft();
        if (window.innerWidth < 900) {
          setMobileDrawerOpen(false);
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (window.innerWidth < 900) {
          setMobileDrawerOpen((prev) => !prev);
        } else {
          handleToggleCollapse();
        }
      } else if (e.key === 'Escape') {
        if (mobileDrawerOpen) {
          setMobileDrawerOpen(false);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mobileDrawerOpen, startNewDraft]);

  return (
    <div className="flex h-[100dvh] w-screen overflow-hidden dark:bg-[#141517] bg-[#FAF9F5] dark:text-[#F3F4F6] text-[#2C2D30] relative transition-colors duration-150">
      {/* Mobile Backdrop Overlay (<900px) */}
      {mobileDrawerOpen && (
        <div
          onClick={() => setMobileDrawerOpen(false)}
          className="fixed inset-0 bg-black/40 backdrop-blur-xs z-[70] min-[900px]:hidden animate-fade-in"
        />
      )}

      {/* Sidebar: Desktop static (z-20) / Mobile slide-over drawer (z-[75]) */}
      <div
        className={`fixed inset-y-0 left-0 transition-all duration-200 ease-premium min-[900px]:static min-[900px]:z-20 ${mobileDrawerOpen
            ? 'translate-x-0 shadow-floating z-[75]'
            : '-translate-x-full min-[900px]:translate-x-0 z-20'
          } ${sidebarCollapsed && !mobileDrawerOpen
            ? 'min-[900px]:w-0 min-[900px]:opacity-0 min-[900px]:pointer-events-none min-[900px]:overflow-hidden'
            : 'min-[900px]:w-[260px] min-[900px]:opacity-100'
          }`}
      >
        <Sidebar
          isCollapsed={sidebarCollapsed && !mobileDrawerOpen}
          onToggleCollapse={() => {
            if (window.innerWidth < 900) {
              setMobileDrawerOpen(false);
            } else {
              handleToggleCollapse();
            }
          }}
          onOpenSettings={() => {
            if (window.innerWidth < 900) {
              setMobileDrawerOpen(false);
            }
          }}
          onSelectChat={() => {
            if (window.innerWidth < 900) {
              setMobileDrawerOpen(false);
            }
          }}
        />
      </div>

      {/* Main App Container */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden dark:bg-[#141517] bg-[#FAF9F5] transition-colors duration-150">
        {/* Disconnection Warning Banner */}
        {!isBackendConnected && (
          <div className="bg-red-950/90 border-b border-red-800/60 text-red-200 px-4 py-2 text-xs font-medium flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>
                Backend disconnected: Unable to reach FastAPI server at <code className="bg-red-900/40 px-1 py-0.5 rounded font-mono">{getApiBaseUrl() || 'configured backend'}</code>.
              </span>
            </div>
            <button
              onClick={() => window.location.reload()}
              className="text-[11px] text-red-300 underline hover:text-white cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}

        {/* Global Navigation Header */}
        <Header
          onToggleMobileMenu={() => setMobileDrawerOpen(true)}
          isSidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={handleToggleCollapse}
          isScrolled={isScrolled}
        />

        {/* Dynamic View Content */}
        <main className="flex-1 overflow-hidden flex flex-col min-w-0">
          {currentPage === 'library' ? <DocumentLibrary /> : <ChatArea />}
        </main>
      </div>

      {/* Upload Tray: Floating panel anchored bottom-right on desktop / above composer on mobile */}
      <UploadTray onNavigateToDocuments={() => setCurrentPage('library')} />

      {/* Floating Toast Notification Stack */}
      <div className="fixed bottom-5 right-5 z-[90] flex flex-col gap-2 max-w-sm pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto p-3 rounded-lg shadow-md dark:shadow-floating text-xs flex items-center justify-between gap-3 animate-fade-in border ${t.type === 'success'
                ? 'dark:bg-[#1C2025] bg-white dark:text-[#F3F4F6] text-[#1F2937] border-emerald-500/40 ring-1 ring-emerald-500/20'
                : t.type === 'error'
                  ? 'dark:bg-red-950/90 bg-red-50 dark:text-red-100 text-red-800 border-red-300 dark:border-red-800'
                  : 'dark:bg-[#1C2025] bg-white dark:text-[#F3F4F6] text-[#1F2937] dark:border-[#30363D] border-[#E5E7EB]'
              }`}
          >
            <div className="flex items-center gap-2.5">
              {t.type === 'success' && <CheckCircle className="w-4 h-4 text-[#10B981] shrink-0" />}
              {t.type === 'error' && <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />}
              {t.type === 'info' && <Info className="w-4 h-4 text-[#10B981] shrink-0" />}
              <span className="font-medium text-[12.5px] leading-snug">{t.message}</span>
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="dark:text-[#71717A] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] transition ml-2 shrink-0 cursor-pointer"
              title="Dismiss notification"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

const UploadBridge: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { documents, refreshData, addToast } = useChat();
  return (
    <UploadProvider
      existingDocuments={documents}
      onRefreshNeeded={refreshData}
      addToast={addToast}
    >
      {children}
    </UploadProvider>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <ChatProvider>
        <UploadBridge>
          <AppContent />
        </UploadBridge>
      </ChatProvider>
    </ThemeProvider>
  );
};

export default App;