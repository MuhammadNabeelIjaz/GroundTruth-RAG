import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  FileText,
  Search,
  Trash2,
  FileUp,
  MoreHorizontal,
  MessageSquare,
  XCircle,
  X,
  Check,
} from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useUpload } from '../context/UploadContext';
import { UploadRow } from './UploadRow';
import { Modal } from './Modal';
import type { DocumentInfo } from '../types';

export const DocumentLibrary: React.FC = () => {
  const {
    documents,
    deleteDocument,
    selectedDocumentNames,
    toggleDocumentSelection,
    clearDocumentSelection,
    setSelectedDocumentNames,
    setCurrentPage,
    startNewDraft,
    isLoading,
  } = useChat();

  const {
    uploads,
    uploadFiles,
    activeCount,
    cancelUpload,
    cancelAllUploads,
    retryUpload,
    removeUpload,
    confirmDuplicate,
    cancelDuplicate,
  } = useUpload();

  const [searchQuery, setSearchQuery] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [activeMenuFile, setActiveMenuFile] = useState<string | null>(null);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [hasMounted, setHasMounted] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastClickedIndexRef = useRef<number | null>(null);
  const longPressTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const touchStartPosRef = useRef<{ x: number; y: number } | null>(null);
  const didLongPressRef = useRef<boolean>(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  // Close overflow menu on outside click
  useEffect(() => {
    const handleClickOutside = () => setActiveMenuFile(null);
    window.addEventListener('click', handleClickOutside);
    return () => window.removeEventListener('click', handleClickOutside);
  }, []);

  const filteredDocs = documents.filter((d) =>
    d.file_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Ready status check: documents in library are ready unless actively uploading/processing
  const isDocReady = useCallback(
    (doc: DocumentInfo) => {
      const activeUpload = uploads.find((u) => u.fileName === doc.file_name);
      if (
        activeUpload &&
        (activeUpload.status === 'uploading' ||
          activeUpload.status === 'processing' ||
          activeUpload.status === 'failed')
      ) {
        return false;
      }
      return true;
    },
    [uploads]
  );

  // Row selection handler supporting normal toggle and Shift+click range selection
  const handleRowSelect = useCallback(
    (docName: string, index: number, isShift = false) => {
      const targetDoc = filteredDocs[index];
      if (!targetDoc || !isDocReady(targetDoc)) return;

      if (isShift && lastClickedIndexRef.current !== null) {
        const start = Math.min(lastClickedIndexRef.current, index);
        const end = Math.max(lastClickedIndexRef.current, index);
        const rangeNames = filteredDocs
          .slice(start, end + 1)
          .filter(isDocReady)
          .map((d) => d.file_name);

        setSelectedDocumentNames(
          Array.from(new Set([...selectedDocumentNames, ...rangeNames]))
        );
      } else {
        toggleDocumentSelection(docName);
        lastClickedIndexRef.current = index;
      }
    },
    [
      filteredDocs,
      isDocReady,
      selectedDocumentNames,
      setSelectedDocumentNames,
      toggleDocumentSelection,
    ]
  );

  // Global keyboard shortcuts: Esc clears selection, Ctrl/Cmd+A selects all ready documents
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput =
        target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');

      if (e.key === 'Escape') {
        if (selectedDocumentNames.length > 0) {
          e.preventDefault();
          clearDocumentSelection();
        }
      } else if (
        (e.ctrlKey || e.metaKey) &&
        e.key.toLowerCase() === 'a' &&
        !isInput
      ) {
        e.preventDefault();
        const allReadyNames = filteredDocs
          .filter(isDocReady)
          .map((d) => d.file_name);
        setSelectedDocumentNames(allReadyNames);
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [
    filteredDocs,
    isDocReady,
    selectedDocumentNames.length,
    clearDocumentSelection,
    setSelectedDocumentNames,
  ]);

  // Touch long press (~400ms) handlers
  const handleTouchStart = (docName: string, index: number, e: React.TouchEvent) => {
    if (e.touches.length > 0) {
      touchStartPosRef.current = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
      };
    }
    didLongPressRef.current = false;
    if (longPressTimeoutRef.current) {
      clearTimeout(longPressTimeoutRef.current);
    }
    longPressTimeoutRef.current = setTimeout(() => {
      didLongPressRef.current = true;
      handleRowSelect(docName, index, false);
      if (typeof window !== 'undefined' && 'vibrate' in navigator) {
        navigator.vibrate(40);
      }
    }, 400);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartPosRef.current && e.touches.length > 0) {
      const dx = Math.abs(e.touches[0].clientX - touchStartPosRef.current.x);
      const dy = Math.abs(e.touches[0].clientY - touchStartPosRef.current.y);
      if (dx > 10 || dy > 10) {
        if (longPressTimeoutRef.current) {
          clearTimeout(longPressTimeoutRef.current);
          longPressTimeoutRef.current = null;
        }
      }
    }
  };

  const handleTouchEnd = () => {
    if (longPressTimeoutRef.current) {
      clearTimeout(longPressTimeoutRef.current);
      longPressTimeoutRef.current = null;
    }
  };

  const handleRowClick = (
    docName: string,
    index: number,
    e: React.MouseEvent
  ) => {
    if (didLongPressRef.current) {
      didLongPressRef.current = false;
      return;
    }
    handleRowSelect(docName, index, e.shiftKey);
  };

  const handleKeyDownRow = (
    docName: string,
    index: number,
    e: React.KeyboardEvent
  ) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      handleRowSelect(docName, index, e.shiftKey);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      uploadFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      uploadFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  };

  const confirmDelete = async () => {
    if (deletingFile) {
      await deleteDocument(deletingFile);
      setDeletingFile(null);
    }
  };

  const handleAskAbout = (fileName: string) => {
    setSelectedDocumentNames([fileName]);
    startNewDraft();
    setCurrentPage('chat');
  };

  const handleChatWithSelected = () => {
    startNewDraft();
    setCurrentPage('chat');
  };

  return (
    <div className="flex-1 overflow-y-auto w-full relative pb-28 sm:pb-32 dark:bg-[#141517] bg-[#FAF9F5] transition-colors duration-150">
      <div className="px-6 py-6 sm:px-12 sm:py-8 max-w-library mx-auto w-full space-y-4 animate-fade-in">
        {/* 1. Subheader with count, description and search */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-xs font-semibold dark:text-[#F3F4F6] text-[#2C2D30]">
            {documents.length} document{documents.length === 1 ? '' : 's'}
          </span>
          <span className="text-xs dark:text-[#8E9097] text-[#9CA3AF] hidden sm:inline">·</span>
          <p className="text-xs dark:text-[#9CA3AF] text-[#6B7280]">
            Upload reference PDFs and select documents for grounded Q&A.
          </p>
        </div>

        {/* Search & Cancel All Bar */}
        <div className="flex items-center gap-2 w-full sm:w-auto">
          {activeCount > 1 && (
            <button
              type="button"
              onClick={cancelAllUploads}
              className="px-2.5 py-1.5 rounded-xl text-xs font-medium text-red-500 bg-red-50 dark:text-red-400 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 hover:bg-red-100 dark:hover:bg-red-900/40 flex items-center gap-1.5 transition cursor-pointer"
              title="Cancel all active uploads"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Cancel all</span>
            </button>
          )}

          {documents.length > 0 && (
            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 dark:text-[#8E9097] text-[#9CA3AF] absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search documents…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-7 py-1.5 text-[13px] dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#E5E4DE] rounded-xl outline-none dark:text-[#F3F4F6] text-[#2C2D30] dark:placeholder:text-[#71737A] placeholder:text-[#9CA3AF] focus:border-[#D5D3CB] transition-colors shadow-xs"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1.5 dark:text-[#8E9097] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] text-sm leading-none"
                  title="Clear search"
                >
                  ×
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 2. Drag-over / Drop Upload Area (Claude card aesthetic) */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`py-5 px-5 rounded-2xl transition-all duration-150 flex flex-col items-center justify-center text-center select-none shadow-[0_4px_20px_rgba(0,0,0,0.03)] ${isDragging
          ? 'border-2 border-dashed border-[#10B981] bg-[#FAF9F5] dark:bg-[#25272C]'
          : 'dark:bg-[#1E2024] bg-white border border-solid dark:border-[#2D3036] border-[#EBEAE5] hover:border-[#10B981]/50 dark:hover:border-[#10B981]/50'
          }`}
      >
        <div className="w-9 h-9 rounded-xl dark:bg-[#25272C] bg-[#F4F3EE] text-[#10B981] flex items-center justify-center mb-2 border dark:border-[#33363D] border-[#E5E4DE]">
          <FileUp className="w-4.5 h-4.5 stroke-[1.75]" />
        </div>

        <div className="text-[13.5px] font-medium dark:text-[#F3F4F6] text-[#2C2D30]">
          <span>{isDragging ? 'Drop PDF files to upload' : 'Drag & drop PDF files here, or '}</span>
          {!isDragging && (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="text-[#10B981] font-medium hover:underline cursor-pointer"
            >
              browse computer
            </button>
          )}
        </div>

        <span className="text-[12px] dark:text-[#8E9097] text-[#6B7280] mt-0.5 block">
          Supports PDF documents up to 20 MB each for grounded semantic search
        </span>

        <input
          ref={fileInputRef}
          data-testid="document-upload-input"
          type="file"
          accept=".pdf,application/pdf"
          multiple
          className="hidden"
          onChange={handleFileInput}
        />
      </div>

      {/* 3. Live Active Upload Rows */}
      {uploads.length > 0 && (
        <div className="space-y-2">
          {uploads.map((item) => (
            <UploadRow
              key={item.id}
              item={item}
              onCancel={cancelUpload}
              onRetry={retryUpload}
              onRemove={removeUpload}
              onAskAbout={handleAskAbout}
              onConfirmDuplicate={confirmDuplicate}
              onCancelDuplicate={cancelDuplicate}
            />
          ))}
        </div>
      )}

      {/* 4. Document List with Skeleton Loading and Clean Selection */}
      <div className="space-y-1.5">
        {/* Skeleton loading state */}
        {isLoading && !hasMounted && documents.length === 0 ? (
          <div
            className="space-y-1.5 animate-pulse"
            aria-label="Loading documents"
          >
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-[52px] dark:bg-[#1E2024] bg-white rounded-xl flex items-center justify-between px-4 border dark:border-[#2D3036] border-[#EBEAE5]"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-xl dark:bg-[#25272C] bg-[#ECEBE5]" />
                  <div className="h-4 w-44 sm:w-64 dark:bg-[#25272C] bg-[#ECEBE5] rounded-md" />
                </div>
                <div className="flex items-center gap-4">
                  <div className="h-3 w-14 dark:bg-[#25272C] bg-[#ECEBE5] rounded hidden sm:block" />
                  <div className="h-5 w-16 dark:bg-[#25272C] bg-[#ECEBE5] rounded-full" />
                  <div className="w-6 h-6 dark:bg-[#25272C] bg-[#ECEBE5] rounded-full" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredDocs.length > 0 ? (
          <div
            role="listbox"
            aria-multiselectable="true"
            aria-label="Document library list"
            className="space-y-1.5"
          >
            {filteredDocs.map((doc, index) => {
              const isSelected = selectedDocumentNames.includes(doc.file_name);
              const isReady = isDocReady(doc);
              const activeUpload = uploads.find(
                (u) =>
                  u.fileName === doc.file_name &&
                  (u.status === 'uploading' || u.status === 'processing')
              );
              const isProcessing = Boolean(activeUpload);
              const sizeText =
                doc.size_bytes > 1048576
                  ? `${(doc.size_bytes / 1048576).toFixed(1)} MB`
                  : `${Math.max(1, Math.round(doc.size_bytes / 1024))} KB`;

              return (
                <div
                  key={doc.file_name}
                  role="option"
                  aria-selected={isSelected}
                  aria-label={`${doc.file_name}, ${sizeText}, ${isProcessing
                    ? `${activeUpload?.progress}% processing`
                    : isReady
                      ? 'Ready'
                      : 'Not ready'
                    }`}
                  tabIndex={isReady && !isProcessing ? 0 : -1}
                  onKeyDown={(e) => handleKeyDownRow(doc.file_name, index, e)}
                  onClick={(e) => {
                    if (isProcessing) return;
                    handleRowClick(doc.file_name, index, e);
                  }}
                  onTouchStart={(e) => {
                    if (isProcessing) return;
                    handleTouchStart(doc.file_name, index, e);
                  }}
                  onTouchMove={handleTouchMove}
                  onTouchEnd={handleTouchEnd}
                  className={`group flex items-center justify-between px-3.5 sm:px-4 py-2.5 rounded-xl transition-all duration-150 select-none border ${isProcessing || !isReady
                    ? 'opacity-60 cursor-not-allowed dark:bg-[#1E2024]/50 bg-gray-50/50 dark:border-[#2D3036]/60 border-[#E5E4DE]/60'
                    : 'dark:bg-[#1E2024] bg-white dark:border-[#2D3036] border-[#EBEAE5] dark:hover:bg-[#25272C]/60 hover:bg-[#F7F6F2] cursor-pointer shadow-xs'
                    } focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#10B981]`}
                  title={
                    isProcessing
                      ? `${doc.file_name} (${activeUpload?.progress}% - processing)`
                      : !isReady
                        ? 'Not ready'
                        : isSelected
                          ? `${doc.file_name} (Selected - click to deselect)`
                          : `${doc.file_name} (Click to select for chat)`
                  }
                >
                  {/* Left: File Icon & Name */}
                  <div className="flex items-center gap-3 min-w-0 flex-1 mr-3">
                    {isSelected ? (
                      <div className="w-8 h-8 rounded-full bg-[#10B981] text-white flex items-center justify-center shrink-0 shadow-xs transition-transform duration-150 scale-100">
                        <Check className="w-4 h-4 stroke-[3]" />
                      </div>
                    ) : (
                      <div className="w-8 h-8 rounded-xl dark:bg-[#25272C] bg-[#F4F3EE] dark:border-[#33363D] border-[#E5E4DE] dark:text-[#8E9097] text-[#6B7280] flex items-center justify-center shrink-0 border transition-colors">
                        <FileText className="w-4 h-4 stroke-[1.75]" />
                      </div>
                    )}

                    <div className="flex flex-col min-w-0 flex-1">
                      <span
                        className={`text-[13.5px] truncate transition-colors ${isSelected
                          ? 'dark:text-[#F3F4F6] text-[#2C2D30] font-semibold'
                          : 'dark:text-[#F3F4F6] text-[#2C2D30] font-medium'
                          }`}
                        title={doc.file_name}
                      >
                        {doc.file_name}
                      </span>
                      {isProcessing && activeUpload && (
                        <div className="w-full mt-1.5 max-w-[200px] sm:max-w-xs">
                          <div className="w-full h-1 dark:bg-[#383C45] bg-[#E5E4DE] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-[#10B981] transition-all duration-200 rounded-full"
                              style={{ width: `${activeUpload.progress}%` }}
                              role="progressbar"
                              aria-valuenow={activeUpload.progress}
                              aria-valuemin={0}
                              aria-valuemax={100}
                            />
                          </div>
                          <span className="text-[11px] text-[#10B981] font-medium mt-0.5 block">
                            {activeUpload.stage === 'uploading'
                              ? 'Uploading…'
                              : activeUpload.stage === 'processing'
                                ? 'Processing…'
                                : activeUpload.stage === 'indexing'
                                  ? 'Indexing…'
                                  : 'Preparing…'}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right: Fixed-width columns for Size, Ready Status, and Overflow Menu */}
                  <div className="flex items-center gap-3 sm:gap-4 shrink-0">
                    {/* File Size column */}
                    <span className="w-16 sm:w-20 text-right text-xs dark:text-[#71717A] text-[#6B7280] font-mono hidden sm:block">
                      {sizeText}
                    </span>

                    {/* Status Badge column */}
                    <div
                      className="w-16 sm:w-20 flex items-center justify-end"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isProcessing && activeUpload ? (
                        <span className="text-xs font-semibold text-[#10B981] tabular-nums">
                          {activeUpload.progress}%
                        </span>
                      ) : isReady ? (
                        <span
                          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full dark:bg-emerald-950/40 bg-emerald-50 border dark:border-emerald-800/40 border-emerald-200 text-[11px] font-medium dark:text-emerald-400 text-emerald-700"
                          title={`${doc.chunk_count} indexed chunks`}
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
                          <span>Ready</span>
                        </span>
                      ) : (
                        <span
                          className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full dark:bg-amber-950/40 bg-amber-50 border dark:border-amber-800/40 border-amber-200 text-[11px] font-medium dark:text-amber-400 text-amber-700"
                          title="Not ready: document is processing"
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                          <span>Not ready</span>
                        </span>
                      )}
                    </div>

                    {/* Overflow Menu or Cancel button */}
                    <div
                      className="w-8 flex items-center justify-end relative"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isProcessing && activeUpload ? (
                        <button
                          type="button"
                          onClick={() => cancelUpload(activeUpload.id)}
                          className="w-7 h-7 rounded-lg dark:text-[#71717A] text-[#9CA3AF] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center justify-center transition cursor-pointer"
                          title="Cancel upload"
                          aria-label="Cancel upload"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() =>
                              setActiveMenuFile(
                                activeMenuFile === doc.file_name
                                  ? null
                                  : doc.file_name
                              )
                            }
                            className="w-7 h-7 rounded-lg dark:text-[#71717A] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] dark:hover:bg-[#22272D] hover:bg-[#F3F4F6] flex items-center justify-center transition cursor-pointer"
                            title="More options"
                            aria-label="More options"
                          >
                            <MoreHorizontal className="w-4 h-4" />
                          </button>

                          {activeMenuFile === doc.file_name && (
                            <div className="absolute right-0 top-8 z-30 w-36 p-1.5 dark:bg-[#1E2024] bg-white rounded-xl shadow-[0_8px_30px_rgba(0,0,0,0.06)] dark:shadow-[0_8px_30px_rgba(0,0,0,0.4)] border dark:border-[#2D3036] border-[#EBEAE5] animate-slide-down">
                              <button
                                type="button"
                                onClick={() => {
                                  handleAskAbout(doc.file_name);
                                  setActiveMenuFile(null);
                                }}
                                className="w-full px-2.5 py-1.5 text-left text-xs flex items-center gap-2 dark:text-[#F3F4F6] text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] rounded-lg transition cursor-pointer"
                              >
                                <MessageSquare className="w-3.5 h-3.5 text-[#10B981]" />
                                <span>Chat with this</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setDeletingFile(doc.file_name);
                                  setActiveMenuFile(null);
                                }}
                                className="w-full px-2.5 py-1.5 text-left text-xs flex items-center gap-2 text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 rounded-lg transition cursor-pointer"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                                <span>Delete</span>
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : searchQuery ? (
          /* Empty state when search finds nothing */
          <div className="py-12 text-center dark:text-[#71717A] text-[#9CA3AF] text-xs space-y-2">
            <p className="text-sm font-medium dark:text-[#A1A1AA] text-[#4B5563]">
              No documents match your search.
            </p>
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="text-xs text-[#10B981] hover:underline font-medium cursor-pointer"
            >
              Clear search query
            </button>
          </div>
        ) : uploads.length === 0 ? (
          /* Empty state when library has no documents */
          <div className="py-14 text-center dark:text-[#71717A] text-[#9CA3AF] text-xs space-y-3">
            <p className="text-sm font-medium dark:text-[#F3F4F6] text-[#1F2937]">
              No documents yet
            </p>
            <p className="text-xs dark:text-[#A1A1AA] text-[#6B7280] max-w-sm mx-auto">
              Upload your PDF documents to ask grounded questions and inspect sources.
            </p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-3.5 py-2 rounded-lg bg-[#10B981] hover:bg-[#059669] text-white text-xs font-medium shadow-btn-hover transition cursor-pointer"
            >
              Upload PDF
            </button>
          </div>
        ) : null}
      </div>
      </div>

      {/* 5. Floating selection bottom bar with 150ms transition */}
      <div
        className={`fixed bottom-6 sm:bottom-8 left-1/2 -translate-x-1/2 z-40 max-w-[calc(100vw-2rem)] transition-all duration-150 ease-out ${selectedDocumentNames.length > 0
          ? 'opacity-100 translate-y-0 pointer-events-auto'
          : 'opacity-0 translate-y-3 pointer-events-none'
          }`}
        aria-live="polite"
      >
        <div className="px-4 py-2.5 rounded-full dark:bg-[#1E2024] bg-white shadow-[0_8px_30px_rgba(0,0,0,0.08)] dark:shadow-[0_8px_30px_rgba(0,0,0,0.4)] flex items-center gap-3 border dark:border-[#2D3036] border-[#E5E4DE]">
          <span className="text-xs font-medium dark:text-[#F3F4F6] text-[#2C2D30] whitespace-nowrap">
            {selectedDocumentNames.length} document
            {selectedDocumentNames.length === 1 ? '' : 's'} selected
          </span>

          <div className="h-3.5 w-px dark:bg-[#2D3036] bg-[#E5E4DE] shrink-0" />

          <button
            type="button"
            onClick={handleChatWithSelected}
            className="px-3.5 py-1.5 rounded-full bg-[#2C2D30] hover:bg-[#1A1B1E] dark:bg-[#F3F4F6] dark:hover:bg-white text-white dark:text-[#141517] text-xs font-medium flex items-center gap-1.5 transition active:scale-[0.98] cursor-pointer whitespace-nowrap shrink-0 shadow-xs"
          >
            <MessageSquare className="w-3.5 h-3.5 shrink-0 text-[#10B981]" />
            <span>Chat with these</span>
          </button>

          <button
            type="button"
            onClick={clearDocumentSelection}
            className="px-2.5 py-1.5 rounded-full text-xs font-normal dark:text-[#8E9097] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] transition cursor-pointer whitespace-nowrap shrink-0"
            title="Deselect all"
          >
            Clear
          </button>
        </div>
      </div>

      {/* 6. Delete Confirmation Modal */}
      <Modal
        isOpen={!!deletingFile}
        onClose={() => setDeletingFile(null)}
        variant="compact"
        ariaLabelledBy="delete-doc-dialog-title"
      >
        <div className="p-5 space-y-3.5 dark:bg-[#1C2025] bg-white dark:text-[#F3F4F6] text-[#1F2937]">
          <h3
            id="delete-doc-dialog-title"
            className="text-base font-semibold dark:text-[#F3F4F6] text-[#1F2937]"
          >
            Delete document?
          </h3>
          <p className="text-xs dark:text-[#A1A1AA] text-[#6B7280] leading-relaxed">
            This will remove{' '}
            <strong className="font-semibold dark:text-white text-[#111827]">
              {deletingFile}
            </strong>{' '}
            and all its indexed contents from your library.
          </p>
          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setDeletingFile(null)}
              className="px-3 py-1.5 rounded-lg text-xs dark:text-[#A1A1AA] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] dark:hover:bg-[#22272D] hover:bg-[#F3F4F6] transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirmDelete}
              className="px-3.5 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition cursor-pointer"
            >
              Delete
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
