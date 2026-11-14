import React, { useState, useEffect } from 'react';
import {
  MoreHorizontal,
  RefreshCw,
  Edit2,
  Trash2,
  Check,
  Sun,
  Moon,
  PanelLeft,
  Plus,
  MessageSquare,
  FileText,
} from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useTheme } from '../context/ThemeContext';

interface HeaderProps {
  onToggleMobileMenu?: () => void;
  isSidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
  isScrolled?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  onToggleMobileMenu,
  isSidebarCollapsed = false,
  onToggleSidebar,
}) => {
  const {
    activeConversationTitle,
    activeConversationId,
    renameConversation,
    deleteConversation,
    startNewDraft,
    isBackendConnected,
    currentPage,
    refreshData,
    documents,
  } = useChat();

  const { theme, toggleTheme } = useTheme();

  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleInput, setTitleInput] = useState('');
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    setTitleInput(activeConversationTitle || 'New chat');
  }, [activeConversationTitle]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = () => setIsMenuOpen(false);
    window.addEventListener('click', handleClickOutside);
    return () => window.removeEventListener('click', handleClickOutside);
  }, []);

  const handleSaveTitle = () => {
    if (activeConversationId && titleInput.trim()) {
      renameConversation(activeConversationId, titleInput.trim());
    }
    setIsEditingTitle(false);
  };

  const handleRefresh = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsRefreshing(true);
    await refreshData();
    setTimeout(() => {
      setIsRefreshing(false);
      setIsMenuOpen(false);
    }, 400);
  };

  const handleClearChat = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (activeConversationId) {
      await deleteConversation(activeConversationId);
    }
    startNewDraft();
    setIsMenuOpen(false);
  };

  const displayTitle = currentPage === 'library' ? 'Documents' : (activeConversationTitle || 'New chat');

  return (
    <header
      className="h-16 px-5 sm:px-6 dark:bg-[#141517] bg-[#FAF9F5] flex items-center justify-between shrink-0 transition-colors duration-150 z-30 select-none"
    >
      {/* Left: Mobile Drawer Toggle / Desktop Sidebar Toggle & Breadcrumb Title */}
      <div className="flex items-center gap-2 sm:gap-2.5 min-w-0 max-w-[calc(100%-190px)]">
        {/* Mobile menu button (<900px) */}
        <button
          onClick={onToggleMobileMenu}
          className="min-[900px]:hidden w-8 h-8 rounded-lg dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] flex items-center justify-center dark:text-[#9CA3AF] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] transition shrink-0 cursor-pointer"
          title="Open sidebar (Ctrl+B)"
          aria-label="Open navigation sidebar"
        >
          <PanelLeft className="w-4 h-4 stroke-[1.75]" />
        </button>

        {/* Desktop Open Sidebar button (only visible when sidebar is collapsed on >=900px) */}
        {isSidebarCollapsed && (
          <div className="hidden min-[900px]:flex items-center gap-1.5 shrink-0 animate-fade-in">
            <button
              type="button"
              onClick={onToggleSidebar}
              className="w-8 h-8 rounded-lg dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] flex items-center justify-center dark:text-[#9CA3AF] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] transition cursor-pointer"
              title="Open sidebar (Ctrl+B)"
              aria-label="Open sidebar"
            >
              <PanelLeft className="w-4 h-4 stroke-[1.75]" />
            </button>

            <button
              type="button"
              onClick={startNewDraft}
              className="w-8 h-8 rounded-lg dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] flex items-center justify-center dark:text-[#9CA3AF] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] transition cursor-pointer"
              title="New chat (Ctrl+Shift+O)"
              aria-label="New chat"
            >
              <Plus className="w-4 h-4 stroke-[2]" />
            </button>

            <div className="w-[1px] h-4 dark:bg-[#2D3036] bg-[#EBEAE5] mx-1" />
          </div>
        )}

        {/* Page Breadcrumb / Title preview */}
        {currentPage === 'chat' && isEditingTitle ? (
          <div className="flex items-center gap-1.5 min-w-0">
            <input
              type="text"
              value={titleInput}
              onChange={(e) => setTitleInput(e.target.value)}
              className="text-[14.5px] font-medium dark:text-[#F3F4F6] text-[#2C2D30] dark:bg-[#1E2024] bg-white dark:border-[#2D3036] border-[#E5E4DE] px-2.5 py-1 rounded-lg outline-none ring-1 ring-[#D5D3CB] min-w-0 shadow-xs"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveTitle();
                if (e.key === 'Escape') setIsEditingTitle(false);
              }}
              onBlur={handleSaveTitle}
            />
            <button
              onClick={handleSaveTitle}
              className="p-1.5 rounded-lg dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] text-[#2C2D30] dark:text-[#F3F4F6] transition cursor-pointer shrink-0"
              title="Save title"
            >
              <Check className="w-4 h-4 stroke-[2]" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 min-w-0">
            {/* Category Breadcrumb Prefix */}
            <div className="hidden sm:flex items-center gap-1.5 text-xs font-normal dark:text-[#8E9097] text-[#9CA3AF] shrink-0">
              {currentPage === 'chat' ? (
                <>
                  <MessageSquare className="w-3.5 h-3.5 stroke-[1.75]" />
                  <span>Chats</span>
                </>
              ) : (
                <>
                  <FileText className="w-3.5 h-3.5 stroke-[1.75]" />
                  <span>Workspace</span>
                </>
              )}
              <span className="dark:text-[#424B57] text-[#D1D0C7]">/</span>
            </div>

            {/* Main Title with hover rename trigger */}
            <div
              onClick={() => currentPage === 'chat' && setIsEditingTitle(true)}
              className={`group flex items-center gap-1 min-w-0 ${currentPage === 'chat' ? 'cursor-pointer' : ''
                }`}
              title={currentPage === 'chat' ? 'Click to rename' : undefined}
            >
              <h1 className="text-[15px] sm:text-[15.5px] font-medium dark:text-[#F3F4F6] text-[#2C2D30] tracking-[-0.01em] truncate group-hover:text-[#10B981] transition-colors">
                {displayTitle}
              </h1>

              {currentPage === 'chat' && (
                <Edit2 className="w-3.5 h-3.5 dark:text-[#8E9097] text-[#9CA3AF] opacity-0 group-hover:opacity-100 group-hover:text-[#10B981] transition shrink-0 ml-0.5" />
              )}
            </div>

            {currentPage === 'library' && (
              <span className="ml-1.5 px-2 py-0.5 rounded-full text-[11px] font-normal dark:bg-[#25272C] bg-[#ECEBE5] text-[#5E6066] dark:text-[#A1A1AA] border border-[#E5E4DE] dark:border-[#33363D] shrink-0 hidden sm:inline-block">
                {documents.length} files
              </span>
            )}
          </div>
        )}
      </div>

      {/* Right: Theme Toggle, Status dot & "..." menu */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Quick Theme Toggle in Header */}
        <button
          type="button"
          onClick={toggleTheme}
          className="w-8 h-8 rounded-full dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] dark:text-[#9CA3AF] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] flex items-center justify-center transition cursor-pointer"
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? (
            <Sun className="w-4 h-4 stroke-[1.75] text-amber-400" />
          ) : (
            <Moon className="w-4 h-4 stroke-[1.75] text-[#4B5563]" />
          )}
        </button>

        {/* Status Dot with tooltip */}
        <div className="relative group flex items-center p-2 cursor-default">
          <span
            className={`w-2 h-2 rounded-full transition-colors ${isBackendConnected ? 'bg-[#10B981]' : 'bg-[#EF4444]'
              }`}
          />
          <div className="absolute right-0 top-9 hidden group-hover:block z-50 whitespace-nowrap px-2.5 py-1 rounded-md dark:bg-[#1E2024] bg-white dark:text-[#F3F4F6] text-[#2C2D30] dark:border-[#2D3036] border-[#E5E4DE] text-[11px] shadow-sm pointer-events-none">
            {isBackendConnected ? 'Connected' : 'Offline'}
          </div>
        </div>

        {/* Action Menu (...) */}
        <div className="relative" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="w-8 h-8 rounded-full dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] dark:text-[#9CA3AF] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] flex items-center justify-center transition cursor-pointer"
            title="More actions"
            aria-label="More actions"
          >
            <MoreHorizontal className="w-4 h-4 stroke-[1.75]" />
          </button>

          {isMenuOpen && (
            <div className="absolute right-0 top-9 z-40 w-44 p-1.5 dark:bg-[#1E2024] bg-white rounded-xl shadow-[0_8px_24px_rgba(0,0,0,0.06)] dark:shadow-[0_8px_24px_rgba(0,0,0,0.4)] border dark:border-[#2D3036] border-[#EBEAE5] animate-slide-down">
              <button
                onClick={handleRefresh}
                className="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2.5 dark:text-[#F3F4F6] text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] rounded-lg transition cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 stroke-[1.75] text-[#10B981] ${isRefreshing ? 'animate-spin' : ''}`} />
                <span>Refresh</span>
              </button>

              <button
                onClick={() => {
                  toggleTheme();
                  setIsMenuOpen(false);
                }}
                className="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2.5 dark:text-[#F3F4F6] text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] rounded-lg transition cursor-pointer"
              >
                {theme === 'dark' ? (
                  <>
                    <Sun className="w-3.5 h-3.5 stroke-[1.75] text-amber-400" />
                    <span>Light mode</span>
                  </>
                ) : (
                  <>
                    <Moon className="w-3.5 h-3.5 stroke-[1.75] text-[#6B7280]" />
                    <span>Dark mode</span>
                  </>
                )}
              </button>

              {currentPage === 'chat' && (
                <>
                  <button
                    onClick={() => {
                      setIsEditingTitle(true);
                      setIsMenuOpen(false);
                    }}
                    className="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2.5 dark:text-[#F3F4F6] text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] rounded-lg transition cursor-pointer"
                  >
                    <Edit2 className="w-3.5 h-3.5 stroke-[1.75] dark:text-[#9CA3AF] text-[#6B7280]" />
                    <span>Rename</span>
                  </button>

                  <button
                    onClick={handleClearChat}
                    className="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2.5 text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 rounded-lg transition cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5 stroke-[1.75]" />
                    <span>Clear chat</span>
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
};