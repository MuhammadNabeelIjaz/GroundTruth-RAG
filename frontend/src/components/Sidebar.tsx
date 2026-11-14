import React, { useState, useEffect } from 'react';
import {
  MessageSquare,
  FileText,
  Plus,
  MoreHorizontal,
  Trash2,
  Edit2,
  Check,
  PanelLeft,
  Settings,
} from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useUpload } from '../context/UploadContext';
import { SettingsModal } from './SettingsModal';
import { BrandLogoIcon } from './BrandLogoIcon';
import type { ConversationResponse } from '../types';

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onOpenSettings?: () => void;
  onSelectChat?: () => void;
}

function groupConversations(convs: ConversationResponse[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;

  const today: ConversationResponse[] = [];
  const yesterday: ConversationResponse[] = [];
  const earlier: ConversationResponse[] = [];

  for (const c of convs) {
    const time = new Date(c.updated_at || c.created_at || Date.now()).getTime();
    if (time >= todayStart) {
      today.push(c);
    } else if (time >= yesterdayStart) {
      yesterday.push(c);
    } else {
      earlier.push(c);
    }
  }

  return { today, yesterday, earlier };
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggleCollapse, onOpenSettings, onSelectChat }) => {
  const {
    documents,
    conversations,
    activeConversationId,
    selectConversation,
    startNewDraft,
    deleteConversation,
    renameConversation,
    currentPage,
    setCurrentPage,
    isInitialLoading,
  } = useChat();

  const { hasActiveUploads } = useUpload();

  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editTitleInput, setEditTitleInput] = useState('');
  const [isSettingsOpen, setIsSettingsOpen] = useState(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get('settings') === 'true';
    } catch {
      return false;
    }
  });

  // Close menus on click outside
  useEffect(() => {
    const handleClickOutside = () => setActiveMenuId(null);
    window.addEventListener('click', handleClickOutside);
    return () => window.removeEventListener('click', handleClickOutside);
  }, []);

  const handleStartRename = (id: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingChatId(id);
    setEditTitleInput(currentTitle);
    setActiveMenuId(null);
  };

  const handleSaveRename = (id: string) => {
    if (editTitleInput.trim()) {
      renameConversation(id, editTitleInput.trim());
    }
    setEditingChatId(null);
  };

  const { today, yesterday, earlier } = groupConversations(conversations);

  const renderConversationGroup = (title: string, list: ConversationResponse[]) => {
    if (list.length === 0) return null;
    return (
      <div key={title} className="space-y-1">
        <div className="pt-4 px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-[#8E9096] dark:text-[#71737A]">
          {title}
        </div>
        {list.map((conv) => {
          const isActive = conv.conversation_id === activeConversationId && currentPage === 'chat';
          const isEditing = editingChatId === conv.conversation_id;

          if (isEditing) {
            return (
              <div
                key={conv.conversation_id}
                className="flex items-center gap-1.5 h-9 px-3 dark:bg-[#1E2024] bg-white rounded-lg border dark:border-[#2D3036] border-[#E5E4DE] shadow-xs"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  type="text"
                  value={editTitleInput}
                  onChange={(e) => setEditTitleInput(e.target.value)}
                  className="flex-1 text-[13.5px] bg-transparent outline-none dark:text-[#F3F4F6] text-[#2C2D30] font-medium"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveRename(conv.conversation_id);
                    if (e.key === 'Escape') setEditingChatId(null);
                  }}
                />
                <button
                  onClick={() => handleSaveRename(conv.conversation_id)}
                  className="p-1 dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] rounded text-[#5E6066] dark:text-[#A1A3A8] hover:text-[#2C2D30] cursor-pointer"
                >
                  <Check className="w-3.5 h-3.5 stroke-[2]" />
                </button>
              </div>
            );
          }

          return (
            <div
              key={conv.conversation_id}
              onClick={() => {
                selectConversation(conv.conversation_id);
                onSelectChat?.();
              }}
              className={`group relative flex items-center justify-between h-9 px-3 rounded-lg text-[13.5px] cursor-pointer transition-colors duration-150 select-none ${isActive
                ? 'dark:bg-[#25272C] bg-[#F4F3EE] dark:text-[#F3F4F6] text-[#1F2022] font-medium'
                : 'dark:text-[#A1A3A8] text-[#5E6066] dark:hover:bg-[#25272C]/60 hover:bg-[#F4F3EE]/80 dark:hover:text-[#F3F4F6] hover:text-[#1F2022]'
                }`}
            >
              <div className="flex items-center gap-2.5 min-w-0 flex-1 pr-2">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 transition-opacity ${isActive ? 'bg-[#5E6066] dark:bg-[#A1A3A8] opacity-80' : 'bg-[#8E9096] dark:bg-[#5E6066] opacity-0 group-hover:opacity-40'
                  }`} />
                <span className="truncate flex-1">
                  {conv.title || 'Untitled chat'}
                </span>
              </div>

              {/* Overflow action menu on hover only */}
              <div className="shrink-0 relative" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveMenuId(activeMenuId === conv.conversation_id ? null : conv.conversation_id);
                  }}
                  className={`w-6 h-6 rounded flex items-center justify-center transition cursor-pointer ${activeMenuId === conv.conversation_id
                    ? 'opacity-100 dark:text-[#F3F4F6] text-[#2C2D30] dark:bg-[#1E2024] bg-white'
                    : 'opacity-0 group-hover:opacity-100 dark:text-[#A1A3A8] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] dark:hover:bg-[#1E2024] hover:bg-white'
                    }`}
                  title="Chat options"
                  aria-label="Chat options"
                >
                  <MoreHorizontal className="w-3.5 h-3.5 stroke-[1.75]" />
                </button>

                {activeMenuId === conv.conversation_id && (
                  <div className="absolute right-0 top-7 z-[60] w-32 p-1.5 dark:bg-[#1E2024] bg-white rounded-xl shadow-[0_8px_30px_rgba(0,0,0,0.06)] dark:shadow-[0_8px_30px_rgba(0,0,0,0.4)] border dark:border-[#2D3036] border-[#EBEAE5] animate-slide-down">
                    <button
                      onClick={(e) => handleStartRename(conv.conversation_id, conv.title, e)}
                      className="w-full px-2.5 py-1.5 text-left text-xs flex items-center gap-2 dark:text-[#F3F4F6] text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] rounded-lg transition cursor-pointer"
                    >
                      <Edit2 className="w-3.5 h-3.5 stroke-[1.75] dark:text-[#A1A3A8] text-[#6B7280]" />
                      <span>Rename</span>
                    </button>
                    <button
                      onClick={() => {
                        deleteConversation(conv.conversation_id);
                        setActiveMenuId(null);
                      }}
                      className="w-full px-2.5 py-1.5 text-left text-xs flex items-center gap-2 text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 rounded-lg transition cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5 stroke-[1.75]" />
                      <span>Delete</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <>
      <aside
        className={`h-[100dvh] flex flex-col justify-between select-none shrink-0 relative transition-all duration-200 ease-premium overflow-hidden z-20 ${isCollapsed
            ? 'w-0 opacity-0 pointer-events-none'
            : 'w-[260px] dark:bg-[#1E2024] bg-white opacity-100'
          }`}
        aria-hidden={isCollapsed}
      >
        {/* Top Section: Logo, New Chat, Nav Links */}
        <div className="shrink-0 flex flex-col w-[260px]">
          {/* Header Row: Clean, balanced executive proportions */}
          <div className="h-14 flex items-center justify-between px-3.5 shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-[18px] h-[18px] flex items-center justify-center shrink-0">
                <BrandLogoIcon className="w-[18px] h-[18px] text-[#10B981] stroke-[1.75]" />
              </div>
              <span className="font-semibold text-[14px] leading-none dark:text-[#F3F4F6] text-[#1F2022] tracking-[-0.01em] truncate whitespace-nowrap select-none">
                GroundTruth
              </span>
            </div>
            {/* Clean, Refined Sidebar Toggle Button (Compact, delicate size) */}
            <button
              onClick={onToggleCollapse}
              className="w-7 h-7 rounded-md dark:text-[#8E9097] text-[#8E9097] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] flex items-center justify-center transition cursor-pointer"
              title="Close sidebar (Ctrl+B)"
              aria-label="Close sidebar"
              aria-expanded={true}
            >
              <PanelLeft className="w-4 h-4 stroke-[1.6]" />
            </button>
          </div>

          {/* New Chat Button & Nav Links */}
          <div className="px-3 pt-1 space-y-2">
            {/* Primary New Chat Button (Clean, elevated pill on white background) */}
            <button
              onClick={() => {
                startNewDraft();
                onSelectChat?.();
              }}
              className="w-full h-9 bg-[#F4F3EE] hover:bg-[#ECEBE5] dark:bg-[#25272C] dark:hover:bg-[#2E3137] text-[#2C2D30] dark:text-[#F3F4F6] border border-[#EBEAE5] dark:border-[#33363D] rounded-xl font-medium text-[13.5px] flex items-center justify-center gap-2 transition active:scale-[0.99] cursor-pointer shadow-xs"
              title="New chat (Ctrl+Shift+O)"
            >
              <Plus className="w-4 h-4 stroke-[2] text-[#5E6066] dark:text-[#A1A3A8]" />
              <span className="whitespace-nowrap">New chat</span>
            </button>

            {/* Navigation links with breathing room */}
            <div className="space-y-1 pt-1">
              <button
                onClick={() => {
                  setCurrentPage('chat');
                  onSelectChat?.();
                }}
                className={`w-full h-9 px-3 rounded-lg text-[13.5px] flex items-center gap-2.5 transition cursor-pointer ${currentPage === 'chat'
                  ? 'dark:bg-[#25272C] bg-[#F4F3EE] dark:text-[#F3F4F6] text-[#1F2022] font-medium'
                  : 'dark:text-[#A1A3A8] text-[#5E6066] dark:hover:bg-[#25272C]/60 hover:bg-[#F4F3EE]/80 dark:hover:text-[#F3F4F6] hover:text-[#1F2022]'
                  }`}
              >
                <MessageSquare className="w-4 h-4 stroke-[1.75] shrink-0 text-[#5E6066] dark:text-[#A1A3A8]" />
                <span className="whitespace-nowrap">Chats</span>
              </button>

              <button
                onClick={() => {
                  setCurrentPage('library');
                  onSelectChat?.();
                }}
                className={`w-full h-9 px-3 rounded-lg text-[13.5px] flex items-center justify-between transition cursor-pointer ${currentPage === 'library'
                  ? 'dark:bg-[#25272C] bg-[#F4F3EE] dark:text-[#F3F4F6] text-[#1F2022] font-medium'
                  : 'dark:text-[#A1A3A8] text-[#5E6066] dark:hover:bg-[#25272C]/60 hover:bg-[#F4F3EE]/80 dark:hover:text-[#F3F4F6] hover:text-[#1F2022]'
                  }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <FileText className="w-4 h-4 stroke-[1.75] shrink-0 text-[#5E6066] dark:text-[#A1A3A8]" />
                  <span className="whitespace-nowrap">Documents</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {hasActiveUploads && (
                    <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse" />
                  )}
                  {documents.length > 0 && (
                    <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-full dark:bg-[#1E2024] bg-[#F4F3EE] text-[#5E6066] dark:text-[#A1A3A8] border border-[#EBEAE5] dark:border-[#33363D]">
                      {documents.length}
                    </span>
                  )}
                </div>
              </button>
            </div>
          </div>
        </div>

        {/* Middle Section: Recent Chats List (Hidden scrollbar to prevent any vertical track line) */}
        <div className="flex-1 min-h-0 overflow-y-auto px-2 py-2 space-y-2.5 mt-2 w-[260px] [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          {isInitialLoading ? (
            <div className="space-y-3 px-1 pt-1" aria-label="Loading recent conversations">
              <div className="px-1.5 flex items-center justify-between">
                <div className="h-2.5 w-16 rounded bg-[#E5E4DE] dark:bg-[#25272C] animate-shimmer" />
              </div>
              <div className="space-y-1.5">
                {[88, 72, 92, 65, 80].map((widthPct, idx) => (
                  <div
                    key={idx}
                    className="h-9 px-3 rounded-lg dark:bg-[#1E2024] bg-[#ECEBE5] flex items-center animate-shimmer"
                  >
                    <div
                      className="h-3 rounded bg-[#DCDAD2] dark:bg-[#2C2E34]"
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                ))}
              </div>
            </div>
          ) : conversations.length > 0 ? (
            <>
              {renderConversationGroup('Today', today)}
              {renderConversationGroup('Yesterday', yesterday)}
              {renderConversationGroup('Earlier', earlier)}
            </>
          ) : (
            <div className="px-3 py-6 text-xs text-[#8E9096] dark:text-[#71737A] text-center font-normal">
              No conversations yet
            </div>
          )}
        </div>

        {/* Bottom Section: Settings (Clean & seamless) */}
        <div className="shrink-0 p-2.5 pt-2 space-y-1 w-[260px]">
          {/* Settings */}
          <button
            onClick={() => {
              setIsSettingsOpen(true);
              onOpenSettings?.();
            }}
            className="w-full h-9 px-3 rounded-lg flex items-center gap-2.5 text-[#5E6066] dark:text-[#A1A3A8] dark:hover:bg-[#25272C] hover:bg-[#F4F3EE] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] transition cursor-pointer"
            aria-label="Open settings"
          >
            <Settings className="w-4 h-4 stroke-[1.75] shrink-0" />
            <span className="text-[13.5px] font-medium whitespace-nowrap">
              Settings
            </span>
          </button>
        </div>
      </aside>

      <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </>
  );
};
