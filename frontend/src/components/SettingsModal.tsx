import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  MessageSquare,
  FileText,
  Info,
  Check,
  Trash2,
  ExternalLink,
  Server,
  Shield,
  Palette,
  Sun,
  Moon,
} from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useTheme } from '../context/ThemeContext';
import { Modal } from './Modal';
import { BrandLogoIcon } from './BrandLogoIcon';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabKey = 'chat' | 'appearance' | 'documents' | 'about';

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const {
    isBackendConnected,
    documents,
    conversations,
    defaultScope,
    setDefaultScope,
    topK,
    setTopK,
    minSimilarity,
    setMinSimilarity,
    clearAllConversations,
    setCurrentPage,
  } = useChat();

  const { theme, setTheme } = useTheme();

  const [activeTab, setActiveTab] = useState<TabKey>(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const tab = params.get('tab') as TabKey;
      if (tab === 'appearance' || tab === 'chat' || tab === 'documents' || tab === 'about') return tab;
      return 'chat';
    } catch {
      return 'chat';
    }
  });
  const [isConfirmingClear, setIsConfirmingClear] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const contentPaneRef = useRef<HTMLDivElement>(null);

  // Reset pane's scrollTop to 0 on each tab switch, and reset confirm clear
  useEffect(() => {
    if (contentPaneRef.current) {
      contentPaneRef.current.scrollTop = 0;
    }
    setIsConfirmingClear(false);
  }, [activeTab]);

  const handleClearAll = async () => {
    setIsClearing(true);
    await clearAllConversations();
    setIsClearing(false);
    setIsConfirmingClear(false);
  };

  const navItems = [
    { key: 'chat' as TabKey, label: 'Chat', icon: MessageSquare },
    { key: 'appearance' as TabKey, label: 'Appearance', icon: Palette },
    { key: 'documents' as TabKey, label: 'Documents', icon: FileText },
    { key: 'about' as TabKey, label: 'About', icon: Info },
  ];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      variant="settings"
      ariaLabelledBy="settings-dialog-title"
    >
      {/* MOBILE HEADER (<640px) */}
      <div className="sm:hidden h-14 shrink-0 px-4 flex items-center justify-between select-none dark:bg-[#1E2024] bg-[#F7F6F2]">
        <h2 id="settings-dialog-title" className="text-base font-semibold dark:text-[#F3F4F6] text-[#2C2D30] tracking-tight">
          Settings
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="w-7 h-7 rounded-full dark:hover:bg-[#25272C] hover:bg-[#ECEBE5] dark:text-[#8E9097] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] flex items-center justify-center transition cursor-pointer"
          title="Close (Esc)"
          aria-label="Close settings"
        >
          <X className="w-4 h-4 stroke-[2]" />
        </button>
      </div>

      {/* MOBILE HORIZONTAL TABS (<640px) */}
      <div className="sm:hidden shrink-0 flex items-center gap-1.5 px-3 py-2 overflow-x-auto no-scrollbar dark:bg-[#1E2024] bg-[#F7F6F2]">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setActiveTab(item.key)}
              className={`px-3 py-1.5 rounded-full text-xs flex items-center gap-1.5 whitespace-nowrap transition cursor-pointer ${
                isActive
                  ? 'dark:bg-[#25272C] bg-[#ECEBE5] dark:text-[#F3F4F6] text-[#2C2D30] font-medium'
                  : 'dark:text-[#8E9097] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30]'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 stroke-[1.75] ${isActive ? 'text-[#10B981]' : ''}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* MAIN CONTAINER (DESKTOP: Unified Combined Sidebar + Content Pane, Zero Border Lines) */}
      <div className="flex-1 min-h-0 flex flex-col sm:flex-row overflow-hidden dark:bg-[#191A1D] bg-white">
        {/* DESKTOP COMBINED SIDEBAR (Header + Nav Tabs combined into one surface, rounded top-right corner, no border lines) */}
        <div className="hidden sm:flex w-[200px] shrink-0 dark:bg-[#1E2024] bg-[#F7F6F2] sm:rounded-tr-2xl sm:rounded-br-2xl flex-col justify-between select-none">
          {/* Settings Title Header in Sidebar */}
          <div className="h-14 px-5 flex items-center shrink-0">
            <h2 id="settings-dialog-title" className="text-base font-semibold dark:text-[#F3F4F6] text-[#2C2D30] tracking-tight">
              Settings
            </h2>
          </div>

          {/* Navigation Items */}
          <nav className="px-3 py-1 space-y-1 flex-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveTab(item.key)}
                  className={`w-full h-9 px-3 rounded-xl flex items-center gap-2.5 text-[13.5px] transition text-left cursor-pointer ${
                    isActive
                      ? 'dark:bg-[#25272C] bg-[#ECEBE5] dark:text-[#F3F4F6] text-[#2C2D30] font-medium shadow-xs'
                      : 'dark:text-[#8E9097] text-[#6B7280] dark:hover:bg-[#25272C]/60 hover:bg-[#ECEBE5]/60 dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] font-normal'
                  }`}
                >
                  <Icon className={`w-4 h-4 stroke-[1.75] ${isActive ? 'text-[#10B981]' : 'dark:text-[#8E9097] text-[#9CA3AF]'}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Version Footer in Sidebar */}
          <div className="p-4 text-xs dark:text-[#8E9097] text-[#9CA3AF] font-mono">
            v0.1.0 · Grounded RAG
          </div>
        </div>

        {/* RIGHT CONTENT PANEL (With Close Button at top-right, Zero Border Lines) */}
        <div className="flex-1 min-h-0 dark:bg-[#191A1D] bg-white overflow-hidden flex flex-col">
          {/* Desktop Close Button Header Row */}
          <div className="hidden sm:flex h-14 px-5 items-center justify-end shrink-0 select-none">
            <button
              type="button"
              onClick={onClose}
              className="w-7 h-7 rounded-full dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] dark:text-[#8E9097] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] flex items-center justify-center transition cursor-pointer"
              title="Close (Esc)"
              aria-label="Close settings"
            >
              <X className="w-4 h-4 stroke-[2]" />
            </button>
          </div>

          <div
            ref={contentPaneRef}
            className="flex-1 min-h-0 overflow-y-auto px-5 pb-5 sm:px-6 sm:pb-6 scrollbar-gutter-stable dark:bg-[#191A1D] bg-white transition-opacity duration-150"
          >
            {/* TAB 1: CHAT */}
            {activeTab === 'chat' && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-base font-semibold dark:text-[#F3F4F6] text-[#1F2937]">
                    Chat Preferences
                  </h3>
                  <p className="text-[13px] dark:text-[#A1A1AA] text-[#6B7280] mt-0.5">
                    Configure document scope, retrieval parameters, and generation settings.
                  </p>
                </div>

                {/* Default Document Scope */}
                <div className="space-y-2 pt-1">
                  <label className="text-xs font-semibold uppercase tracking-wider dark:text-[#71717A] text-[#6B7280] block">
                    Default Document Scope
                  </label>
                  <div className="grid grid-cols-2 gap-2.5">
                    <button
                      type="button"
                      onClick={() => setDefaultScope('all')}
                      className={`p-3 rounded-lg text-left transition flex flex-col justify-between cursor-pointer border ${
                        defaultScope === 'all'
                          ? 'dark:bg-[#25272C] bg-emerald-50/50 border-[#10B981]/60 ring-1 ring-[#10B981]/25'
                          : 'dark:bg-[#25272C]/50 bg-[#F7F6F2] dark:border-[#2D3036] border-[#EBEAE5] dark:hover:bg-[#25272C] hover:bg-[#F3F4F6]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#1F2937]">All Documents</span>
                        {defaultScope === 'all' ? (
                          <span className="w-3.5 h-3.5 rounded-full bg-[#10B981] text-white flex items-center justify-center shrink-0">
                            <Check className="w-2.5 h-2.5 stroke-[3]" />
                          </span>
                        ) : (
                          <span className="w-3.5 h-3.5 rounded-full border dark:border-[#2D3036] border-[#D1D5DB] shrink-0" />
                        )}
                      </div>
                      <span className="text-[12px] dark:text-[#71717A] text-[#6B7280]">
                        Search across all indexed reference files
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setDefaultScope('selected')}
                      className={`p-3 rounded-lg text-left transition flex flex-col justify-between cursor-pointer border ${
                        defaultScope === 'selected'
                          ? 'dark:bg-[#25272C] bg-emerald-50/50 border-[#10B981]/60 ring-1 ring-[#10B981]/25'
                          : 'dark:bg-[#25272C]/50 bg-[#F7F6F2] dark:border-[#2D3036] border-[#EBEAE5] dark:hover:bg-[#25272C] hover:bg-[#F3F4F6]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#1F2937]">Selected Only</span>
                        {defaultScope === 'selected' ? (
                          <span className="w-3.5 h-3.5 rounded-full bg-[#10B981] text-white flex items-center justify-center shrink-0">
                            <Check className="w-2.5 h-2.5 stroke-[3]" />
                          </span>
                        ) : (
                          <span className="w-3.5 h-3.5 rounded-full border dark:border-[#2D3036] border-[#D1D5DB] shrink-0" />
                        )}
                      </div>
                      <span className="text-[12px] dark:text-[#71717A] text-[#6B7280]">
                        Query only documents explicitly checked
                      </span>
                    </button>
                  </div>
                </div>

                {/* Top-K Retrieval Slider */}
                <div className="space-y-2 pt-1 p-3.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#EBEAE5]">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-top-k" className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#1F2937] block">
                        Passages to Retrieve (Top-K)
                      </label>
                      <span className="text-[12px] dark:text-[#71717A] text-[#6B7280]">
                        Maximum number of chunks retrieved for generator context
                      </span>
                    </div>
                    <span className="text-xs font-mono font-semibold text-[#10B981] dark:bg-[#1E2024] bg-white px-2 py-0.5 rounded border dark:border-[#2D3036] border-[#EBEAE5]">
                      {topK}
                    </span>
                  </div>
                  <input
                    id="settings-top-k"
                    type="range"
                    min={1}
                    max={20}
                    step={1}
                    value={topK}
                    onChange={(e) => setTopK(parseInt(e.target.value, 10))}
                    className="w-full h-1.5 dark:bg-[#1E2024] bg-[#E5E7EB] rounded appearance-none cursor-pointer accent-[#10B981]"
                  />
                  <div className="flex justify-between text-[11.5px] dark:text-[#71717A] text-[#6B7280] font-mono px-0.5">
                    <span>1 (Focused)</span>
                    <span>5 (Default)</span>
                    <span>20 (Broad)</span>
                  </div>
                </div>

                {/* Minimum Similarity Threshold Slider */}
                <div className="space-y-2 pt-1 p-3.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#EBEAE5]">
                  <div className="flex items-center justify-between">
                    <div>
                      <label htmlFor="settings-min-sim" className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#1F2937] block">
                        Minimum Similarity Threshold
                      </label>
                      <span className="text-[12px] dark:text-[#71717A] text-[#6B7280]">
                        Filter out passages with similarity below this score
                      </span>
                    </div>
                    <span className="text-xs font-mono font-semibold text-[#10B981] dark:bg-[#1E2024] bg-white px-2 py-0.5 rounded border dark:border-[#2D3036] border-[#EBEAE5]">
                      {(minSimilarity * 100).toFixed(0)}%
                    </span>
                  </div>
                  <input
                    id="settings-min-sim"
                    type="range"
                    min={0.0}
                    max={0.8}
                    step={0.05}
                    value={minSimilarity}
                    onChange={(e) => setMinSimilarity(parseFloat(e.target.value))}
                    className="w-full h-1.5 dark:bg-[#1E2024] bg-[#E5E7EB] rounded appearance-none cursor-pointer accent-[#10B981]"
                  />
                  <div className="flex justify-between text-[11.5px] dark:text-[#71717A] text-[#6B7280] font-mono px-0.5">
                    <span>0% (All matches)</span>
                    <span>40% (Medium)</span>
                    <span>80% (Strict)</span>
                  </div>
                </div>

                {/* Response Generation Mode Status Card */}
                <div className="p-3.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#EBEAE5] flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#1F2937] block">
                      Response Generation Mode
                    </span>
                    <span className="text-[12px] dark:text-[#71717A] text-[#6B7280] mt-0.5 block leading-relaxed">
                      Standard Response Mode: The complete response is displayed after generation finishes. Progressive streaming is not currently supported.
                    </span>
                  </div>
                  <span className="text-xs font-mono dark:text-[#A1A1AA] text-[#6B7280] dark:bg-[#1E2024] bg-white px-2 py-0.5 rounded border dark:border-[#2D3036] border-[#EBEAE5] shrink-0">
                    Standard
                  </span>
                </div>
              </div>
            )}

            {/* TAB 2: APPEARANCE */}
            {activeTab === 'appearance' && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-[14.5px] font-semibold dark:text-[#F3F4F6] text-[#1F2937]">
                    Appearance & Theme
                  </h3>
                  <p className="text-xs dark:text-[#A1A1AA] text-[#6B7280] mt-0.5">
                    Choose your preferred interface theme. Selection persists across sessions.
                  </p>
                </div>

                <div className="space-y-2 pt-1">
                  <label className="text-xs font-semibold uppercase tracking-wider dark:text-[#71717A] text-[#6B7280] block">
                    Interface Theme
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    {/* Light Mode Selector Card */}
                    <button
                      type="button"
                      onClick={() => setTheme('light')}
                      className={`p-4 rounded-lg text-left transition flex flex-col justify-between cursor-pointer border ${
                        theme === 'light'
                          ? 'bg-emerald-50/60 border-[#10B981] ring-2 ring-[#10B981]/25'
                          : 'dark:bg-[#25272C]/50 bg-[#F7F6F2] dark:border-[#2D3036] border-[#EBEAE5] hover:border-[#10B981]/50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="w-8 h-8 rounded-lg bg-white border border-[#EBEAE5] flex items-center justify-center text-amber-500 shadow-xs">
                          <Sun className="w-4 h-4 stroke-[2]" />
                        </div>
                        {theme === 'light' ? (
                          <span className="w-4 h-4 rounded-full bg-[#10B981] text-white flex items-center justify-center shrink-0">
                            <Check className="w-2.5 h-2.5 stroke-[3]" />
                          </span>
                        ) : (
                          <span className="w-4 h-4 rounded-full border dark:border-[#2D3036] border-[#D1D5DB] shrink-0" />
                        )}
                      </div>
                      <div>
                        <span className="text-[14px] font-semibold dark:text-[#F3F4F6] text-[#1F2937] block">
                          Light Theme
                        </span>
                        <span className="text-[12px] dark:text-[#71717A] text-[#6B7280] mt-0.5 block">
                          Clean white background with soft borders and crisp contrast
                        </span>
                      </div>
                    </button>

                    {/* Dark Mode Selector Card */}
                    <button
                      type="button"
                      onClick={() => setTheme('dark')}
                      className={`p-4 rounded-lg text-left transition flex flex-col justify-between cursor-pointer border ${
                        theme === 'dark'
                          ? 'dark:bg-[#25272C] bg-emerald-50/40 border-[#10B981] ring-2 ring-[#10B981]/25'
                          : 'dark:bg-[#25272C]/50 bg-[#F7F6F2] dark:border-[#2D3036] border-[#EBEAE5] hover:border-[#10B981]/50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="w-8 h-8 rounded-lg dark:bg-[#1E2024] bg-[#1F2937] border dark:border-[#2D3036] border-[#1F2937] flex items-center justify-center text-emerald-400 shadow-xs">
                          <Moon className="w-4 h-4 stroke-[2]" />
                        </div>
                        {theme === 'dark' ? (
                          <span className="w-4 h-4 rounded-full bg-[#10B981] text-white flex items-center justify-center shrink-0">
                            <Check className="w-2.5 h-2.5 stroke-[3]" />
                          </span>
                        ) : (
                          <span className="w-4 h-4 rounded-full border dark:border-[#2D3036] border-[#D1D5DB] shrink-0" />
                        )}
                      </div>
                      <div>
                        <span className="text-[14px] font-semibold dark:text-[#F3F4F6] text-[#1F2937] block">
                          Dark Theme
                        </span>
                        <span className="text-[12px] dark:text-[#71717A] text-[#6B7280] mt-0.5 block">
                          Deep charcoal theme with low eye strain and emerald accents
                        </span>
                      </div>
                    </button>
                  </div>
                </div>

                <div className="p-3.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#EBEAE5] text-[12.5px] dark:text-[#A1A1AA] text-[#6B7280] leading-relaxed">
                  <div className="flex items-center gap-2 font-medium dark:text-[#F3F4F6] text-[#1F2937] mb-1">
                    <Palette className="w-4 h-4 text-[#10B981]" />
                    <span>Quick Theme Shortcuts</span>
                  </div>
                  You can also toggle between themes anytime using the Sun/Moon icon in the sidebar footer, the top header action bar, or the header overflow menu.
                </div>
              </div>
            )}

            {/* TAB 3: DOCUMENTS */}
            {activeTab === 'documents' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold dark:text-[#F3F4F6] text-[#1F2937]">
                    Documents & Data
                  </h3>
                  <p className="text-[13px] dark:text-[#A1A1AA] text-[#6B7280] mt-0.5">
                    Manage indexed knowledge files and conversation data.
                  </p>
                </div>

                {/* Library Link Card */}
                <div className="p-3.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#EBEAE5] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg dark:bg-[#1E2024] bg-emerald-50 border dark:border-[#2D3036] border-emerald-200 flex items-center justify-center text-[#10B981]">
                      <FileText className="w-4 h-4 stroke-[1.75]" />
                    </div>
                    <div>
                      <span className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#1F2937] block">
                        Knowledge Base
                      </span>
                      <span className="text-[12px] dark:text-[#71717A] text-[#6B7280]">
                        {documents.length} document{documents.length === 1 ? '' : 's'} indexed
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      setCurrentPage('library');
                    }}
                    className="px-3 py-1.5 rounded-md dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#EBEAE5] text-xs font-medium dark:text-[#F3F4F6] text-[#1F2937] dark:hover:bg-[#282E33] hover:bg-[#F3F4F6] transition flex items-center gap-1.5 cursor-pointer shadow-xs"
                  >
                    <span>Manage</span>
                    <ExternalLink className="w-3.5 h-3.5 dark:text-[#71717A] text-[#9CA3AF]" />
                  </button>
                </div>

                {/* Danger Zone */}
                <div className="p-3.5 rounded-lg dark:bg-red-950/20 bg-red-50 dark:border-red-900/50 border-red-200 space-y-2">
                  <span className="text-xs font-semibold text-red-500 dark:text-red-400 block">
                    Danger Zone
                  </span>
                  <p className="text-[12px] dark:text-[#A1A1AA] text-[#6B7280] leading-relaxed">
                    Permanently delete all conversation sessions and history. Indexed document vectors will remain safe.
                  </p>

                  {isConfirmingClear ? (
                    <div className="pt-2 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setIsConfirmingClear(false)}
                        className="px-3 py-1.5 rounded-md text-xs dark:text-[#A1A1AA] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] dark:hover:bg-[#25272C] hover:bg-[#E5E7EB] transition cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        disabled={isClearing}
                        onClick={handleClearAll}
                        className="px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition cursor-pointer"
                      >
                        {isClearing ? 'Clearing…' : 'Yes, delete all'}
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setIsConfirmingClear(true)}
                      className="mt-1 text-xs font-medium text-red-500 dark:text-red-400 hover:underline flex items-center gap-1.5 transition cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>Clear all conversations</span>
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* TAB 4: ABOUT */}
            {activeTab === 'about' && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold dark:text-[#F3F4F6] text-[#1F2937]">
                    About & Diagnostics
                  </h3>
                  <p className="text-[13px] dark:text-[#A1A1AA] text-[#6B7280] mt-0.5">
                    System specifications and keyboard shortcuts.
                  </p>
                </div>

                <div className="flex items-center gap-3 p-3.5 rounded-xl dark:bg-[#1E2024] bg-[#FAF9F5] border dark:border-[#2D3036] border-[#EBEAE5] shadow-xs">
                  <div className="w-9 h-9 rounded-xl dark:bg-[#25272C] bg-[#ECEBE5] text-[#10B981] flex items-center justify-center shrink-0">
                    <BrandLogoIcon className="w-5 h-5 text-[#10B981]" />
                  </div>
                  <div>
                    <span className="text-[14px] font-semibold dark:text-[#F3F4F6] text-[#2C2D30] block">
                      RAG QA Assistant
                    </span>
                    <span className="text-[12px] dark:text-[#8E9097] text-[#6B7280]">
                      Version 0.1.0 · Grounded Document Intelligence
                    </span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider dark:text-[#8E9097] text-[#6B7280] block">
                    System Status
                  </label>
                  <div className="p-3.5 rounded-xl dark:bg-[#1E2024] bg-[#FAF9F5] border dark:border-[#2D3036] border-[#EBEAE5] space-y-2.5 text-[13px] shadow-xs">
                    <div className="flex items-center justify-between">
                      <span className="dark:text-[#A1A1AA] text-[#6B7280] flex items-center gap-2">
                        <Server className="w-3.5 h-3.5 text-[#10B981]" />
                        Backend Service
                      </span>
                      <span className="flex items-center gap-1.5 font-medium dark:text-[#F3F4F6] text-[#2C2D30]">
                        <span className={`w-1.5 h-1.5 rounded-full ${isBackendConnected ? 'bg-[#10B981]' : 'bg-[#EF4444]'}`} />
                        {isBackendConnected ? 'Connected (Port 8000)' : 'Offline'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="dark:text-[#A1A1AA] text-[#6B7280] flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-[#10B981]" />
                        Active Library
                      </span>
                      <span className="dark:text-[#F3F4F6] text-[#2C2D30] font-mono">
                        {documents.length} docs · {conversations.length} chats
                      </span>
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold uppercase tracking-wider dark:text-[#8E9097] text-[#6B7280] block">
                    Keyboard Shortcuts
                  </label>
                  <div className="p-3.5 rounded-xl dark:bg-[#1E2024] bg-[#FAF9F5] border dark:border-[#2D3036] border-[#EBEAE5] space-y-2.5 text-[13px] dark:text-[#A1A1AA] text-[#6B7280] shadow-xs">
                    <div className="flex items-center justify-between">
                      <span>New chat</span>
                      <kbd className="px-2 py-0.5 rounded-md dark:bg-[#25272C] bg-white border dark:border-[#33363D] border-[#E5E4DE] text-[11px] font-mono dark:text-[#F3F4F6] text-[#2C2D30] shadow-xs">Ctrl + Shift + O</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Toggle sidebar</span>
                      <kbd className="px-2 py-0.5 rounded-md dark:bg-[#25272C] bg-white border dark:border-[#33363D] border-[#E5E4DE] text-[11px] font-mono dark:text-[#F3F4F6] text-[#2C2D30] shadow-xs">Ctrl + B</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Send message</span>
                      <kbd className="px-2 py-0.5 rounded-md dark:bg-[#25272C] bg-white border dark:border-[#33363D] border-[#E5E4DE] text-[11px] font-mono dark:text-[#F3F4F6] text-[#2C2D30] shadow-xs">Enter</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>New line in input</span>
                      <kbd className="px-2 py-0.5 rounded-md dark:bg-[#25272C] bg-white border dark:border-[#33363D] border-[#E5E4DE] text-[11px] font-mono dark:text-[#F3F4F6] text-[#2C2D30] shadow-xs">Shift + Enter</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Close modal</span>
                      <kbd className="px-2 py-0.5 rounded-md dark:bg-[#25272C] bg-white border dark:border-[#33363D] border-[#E5E4DE] text-[11px] font-mono dark:text-[#F3F4F6] text-[#2C2D30] shadow-xs">Esc</kbd>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};
