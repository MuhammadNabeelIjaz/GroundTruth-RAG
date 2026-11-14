import React, { useEffect, useRef, useState, useCallback } from 'react';
import { ArrowDown, FileUp } from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useUpload } from '../context/UploadContext';
import { MessageItem } from './MessageItem';
import { Composer } from './Composer';
import { BrandLogoIcon } from './BrandLogoIcon';
import { api } from '../services/api';

// Cache for document-set suggestions: sorted document key -> question list
const docSetSuggestionsCache = new Map<string, string[]>();

export const ChatArea: React.FC = () => {
  const {
    messages,
    isLoading,
    documents,
    selectedDocumentNames,
    setSelectedDocumentNames,
    setDraftText,
    sendMessage,
    setIsDocSelectorOpen,
  } = useChat();

  const { uploadFiles } = useUpload();

  useEffect(() => {
    (window as any).__uploadFiles = uploadFiles;
    (window as any).__setSelectedDocs = setSelectedDocumentNames;
  }, [uploadFiles, setSelectedDocumentNames]);

  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const isNearBottomRef = useRef(true);

  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isSuggestionsLoading, setIsSuggestionsLoading] = useState(false);

  // Full-area Drag & Drop state
  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      dragCounterRef.current = 0;

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const rawFiles = Array.from(e.dataTransfer.files);
        const pdfFiles = rawFiles.filter(
          (f) =>
            f.type === 'application/pdf' ||
            f.name.toLowerCase().endsWith('.pdf')
        );
        if (pdfFiles.length > 0) {
          uploadFiles(pdfFiles);
          setSelectedDocumentNames(pdfFiles.map((f) => f.name));
        }
      }
    },
    [uploadFiles, setSelectedDocumentNames]
  );

  // Document-set suggestion fetcher with 300ms debounce and persistent caching
  useEffect(() => {
    if (selectedDocumentNames.length === 0) {
      setSuggestions([]);
      setIsSuggestionsLoading(false);
      return;
    }

    const cacheKey = [...selectedDocumentNames].sort().join('::');

    if (docSetSuggestionsCache.has(cacheKey)) {
      setSuggestions(docSetSuggestionsCache.get(cacheKey)!);
      setIsSuggestionsLoading(false);
      return;
    }

    setIsSuggestionsLoading(true);

    const debounceTimer = setTimeout(async () => {
      try {
        const results = await Promise.all(
          selectedDocumentNames.slice(0, 4).map(async (fileName) => {
            try {
              return await api.getDocumentSuggestions(fileName);
            } catch {
              return [];
            }
          })
        );

        const collected: string[] = [];
        for (const list of results) {
          if (Array.isArray(list)) {
            for (const item of list) {
              if (!collected.includes(item) && item.trim()) {
                collected.push(item);
              }
              if (collected.length >= 4) break;
            }
          }
          if (collected.length >= 4) break;
        }

        const finalQuestions = collected.slice(0, 4);
        docSetSuggestionsCache.set(cacheKey, finalQuestions);
        setSuggestions(finalQuestions);
      } catch {
        setSuggestions([]);
      } finally {
        setIsSuggestionsLoading(false);
      }
    }, 300);

    return () => {
      clearTimeout(debounceTimer);
    };
  }, [selectedDocumentNames]);

  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const distanceToBottom = scrollHeight - scrollTop - clientHeight;
    isNearBottomRef.current = distanceToBottom < 120;
    setShowScrollBottom(distanceToBottom > 200);
  };

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isNearBottomRef.current && messages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  return (
    <div
      data-testid="chat-dropzone"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className="flex-1 flex flex-col h-[calc(100dvh-64px)] min-h-0 overflow-hidden dark:bg-[#141517] bg-[#FAF9F5] relative transition-colors duration-150"
    >
      {/* Full-area Drag & Drop Overlay */}
      {isDragging && (
        <div className="absolute inset-0 z-50 dark:bg-[#141517]/90 bg-[#FAF9F5]/95 backdrop-blur-sm flex flex-col items-center justify-center pointer-events-none animate-fade-in dark:text-[#F3F4F6] text-[#2C2D30] p-6">
          <div className="w-14 h-14 rounded-2xl dark:bg-[#1E2024] bg-white border-2 border-dashed border-[#10B981] flex items-center justify-center mb-3 shadow-sm">
            <FileUp className="w-6 h-6 text-[#10B981]" />
          </div>
          <h3 className="text-lg font-serif tracking-tight dark:text-[#F3F4F6] text-[#2C2D30] mb-1">
            Drop PDF to add
          </h3>
          <p className="text-xs dark:text-[#9CA3AF] text-[#6B7280]">
            Files will be uploaded and selected for your conversation
          </p>
        </div>
      )}

      {/* 1. Main Canvas Area (Scrollable Message History or Centered Welcome Hero) */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col"
      >
        {messages.length === 0 ? (
          /* Welcome Hero (Centered vertically in the canvas space above the composer) */
          <div className="flex-1 flex flex-col items-center justify-center max-w-[720px] mx-auto w-full select-none animate-fade-in py-6">
            {/* Grounded Document QA Brand Logo (No background box, clean brand color) */}
            <div className="mb-3.5 flex items-center justify-center">
              <BrandLogoIcon className="w-10 h-10 text-[#10B981] stroke-[1.85]" />
            </div>
            <h2 className="font-serif text-[32px] sm:text-[40px] font-normal tracking-[-0.015em] text-[#2C2D30] dark:text-[#F3F4F6] leading-tight mb-2 text-center">
              What would you like to know?
            </h2>
            <p className="text-[14px] sm:text-[15px] font-normal dark:text-[#9CA3AF] text-[#6B7280] tracking-[-0.01em] text-center mb-6">
              Ask anything about your documents.
            </p>

            {/* Suggested Question Chips */}
            <div className="w-full max-w-[720px] min-h-[90px]">
              {selectedDocumentNames.length > 0 ? (
                isSuggestionsLoading ? (
                  /* YouTube-style Shimmer Skeleton Chips */
                  <div
                    className="flex flex-col items-center gap-2.5 max-w-[720px] px-2 animate-fade-in"
                    aria-label="Loading suggested questions"
                  >
                    <div className="h-3 w-28 rounded bg-[#EBEAE5] dark:bg-[#25272C] animate-shimmer" />
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      {[210, 260, 230].map((width, idx) => (
                        <div
                          key={idx}
                          className="h-[34px] rounded-full dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#EBEAE5] animate-shimmer shadow-xs flex items-center px-3.5"
                          style={{ width: `${width}px` }}
                        >
                          <div className="h-2.5 rounded bg-[#EBEAE5] dark:bg-[#25272C] w-3/4" />
                        </div>
                      ))}
                    </div>
                  </div>
                ) : suggestions.length > 0 ? (
                  /* Ready Question Chips: Claude-style rounded-full ghost pills */
                  <div className="flex flex-col items-center gap-2 max-w-[720px] px-2 animate-fade-in">
                    <div className="text-[11.5px] font-medium tracking-wide uppercase dark:text-[#8E9097] text-[#9CA3AF] text-center select-none">
                      Suggested Questions
                    </div>
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      {suggestions.map((chipText, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => {
                            setDraftText('');
                            sendMessage(chipText);
                          }}
                          style={{ animationDelay: `${idx * 30}ms` }}
                          className="group inline-flex items-center px-4 py-2 rounded-full dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#EBEAE5] hover:bg-[#F7F6F2] dark:hover:bg-[#25272C] hover:border-[#10B981]/50 dark:hover:border-[#10B981]/50 dark:text-[#F3F4F6] text-[#374151] text-[13px] font-normal transition-all duration-150 active:scale-[0.99] cursor-pointer text-left leading-snug line-clamp-2 max-w-full animate-fade-in shadow-[0_1px_3px_rgba(0,0,0,0.03)]"
                          title="Click to ask this question"
                        >
                          <span>{chipText}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null
              ) : (
                <div className="flex items-center justify-center px-4 py-3">
                  {documents.length === 0 ? (
                    <span className="text-[12.5px] dark:text-[#8E9097] text-[#6B7280] select-none text-center">
                      Upload a PDF document to view grounded suggested questions.
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setIsDocSelectorOpen(true)}
                      className="inline-flex items-center gap-1.5 text-[13px] dark:text-[#10B981] text-[#059669] hover:underline font-medium cursor-pointer"
                    >
                      <FileUp className="w-3.5 h-3.5" />
                      <span>Select a document to view grounded suggested questions</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Active Conversation Messages */
          <div className="max-w-[720px] mx-auto w-full space-y-5 px-1 pb-4 flex-1">
            {messages.map((msg, index) => (
              <MessageItem
                key={msg.id || index}
                message={msg}
                isLatest={index === messages.length - 1}
              />
            ))}

            {/* Typing indicator */}
            {isLoading && (
              <div className="flex items-center gap-1.5 py-2 px-1 text-[#6B7280] dark:text-[#9CA3AF]">
                <span className="w-2 h-2 rounded-full bg-[#6B7280] dark:bg-[#9CA3AF] dot-bounce-1" />
                <span className="w-2 h-2 rounded-full bg-[#6B7280] dark:bg-[#9CA3AF] dot-bounce-2" />
                <span className="w-2 h-2 rounded-full bg-[#6B7280] dark:bg-[#9CA3AF] dot-bounce-3" />
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* 2. Permanent Composer Capsule (Pinned at bottom, ZERO displacement, 100% silky smooth) */}
      <div className="w-full flex-none px-4 pb-3 sm:pb-4 flex flex-col items-center">
        <Composer />
      </div>

      {/* Floating scroll-to-bottom button */}
      {showScrollBottom && messages.length > 0 && (
        <div className="absolute right-6 bottom-24 z-30 animate-fade-in">
          <button
            type="button"
            onClick={scrollToBottom}
            className="w-9 h-9 rounded-full dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#E5E4DE] dark:text-[#F3F4F6] text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] shadow-md flex items-center justify-center transition cursor-pointer"
            title="Scroll to bottom"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="w-4 h-4 stroke-[2]" />
          </button>
        </div>
      )}
    </div>
  );
};
