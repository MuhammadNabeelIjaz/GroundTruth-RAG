import React, { useState, useEffect } from 'react';
import {
  ChevronDown,
  ChevronUp,
  X,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  RotateCw,
} from 'lucide-react';
import { useUpload } from '../context/UploadContext';
import { useChat } from '../context/ChatContext';

interface UploadTrayProps {
  onNavigateToDocuments?: () => void;
}

export const UploadTray: React.FC<UploadTrayProps> = () => {
  const {
    uploads,
    hasActiveUploads,
    activeCount,
    failedCount,
    cancelUpload,
    retryUpload,
    removeUpload,
  } = useUpload();

  const { currentPage } = useChat();

  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [isDismissed, setIsDismissed] = useState<boolean>(false);
  const [confirmCancelId, setConfirmCancelId] = useState<string | null>(null);
  const [fadingOutIds, setFadingOutIds] = useState<string[]>([]);

  // Auto-fade individual ready rows after 3s
  useEffect(() => {
    const readyItems = uploads.filter((u) => u.status === 'ready');
    if (readyItems.length === 0) return;

    const timers = readyItems.map((item) => {
      return setTimeout(() => {
        setFadingOutIds((prev) => [...prev, item.id]);
        setTimeout(() => {
          removeUpload(item.id);
          setFadingOutIds((prev) => prev.filter((id) => id !== item.id));
        }, 250);
      }, 3000);
    });

    return () => {
      timers.forEach(clearTimeout);
    };
  }, [uploads, removeUpload]);

  // Auto-dismiss the entire tray 3.5s after all uploads finish (if none failed)
  useEffect(() => {
    if (uploads.length > 0 && !hasActiveUploads && failedCount === 0) {
      const timer = setTimeout(() => {
        setIsDismissed(true);
      }, 3500);
      return () => clearTimeout(timer);
    } else if (hasActiveUploads || failedCount > 0) {
      setIsDismissed(false);
    }
  }, [uploads.length, hasActiveUploads, failedCount]);

  if (uploads.length === 0 || isDismissed || currentPage === 'library') {
    return null;
  }

  // Calculate overall percentage across active uploads
  const overallPercentage =
    uploads.length > 0
      ? Math.round(
          uploads.reduce((sum, u) => sum + (u.progress || 0), 0) / uploads.length
        )
      : 0;

  const getHeaderTitle = () => {
    if (hasActiveUploads) {
      return `Uploading ${activeCount} file${activeCount === 1 ? '' : 's'}`;
    }
    if (failedCount > 0) {
      return `${failedCount} file${failedCount === 1 ? '' : 's'} failed`;
    }
    return 'All files ready';
  };

  const getStageLabel = (item: (typeof uploads)[0]) => {
    if (item.status === 'failed') {
      return item.error || 'Upload failed';
    }
    if (item.status === 'ready') {
      return 'Ready';
    }
    if (item.stage === 'indexing') {
      return 'Indexing…';
    }
    if (item.stage === 'processing') {
      return 'Processing…';
    }
    return 'Uploading…';
  };

  const handleCancelClick = (item: (typeof uploads)[0]) => {
    if (item.status === 'processing') {
      setConfirmCancelId(item.id);
    } else {
      cancelUpload(item.id);
    }
  };

  // COLLAPSED STATE: Floating pill with 16px circular progress ring
  if (isCollapsed) {
    return (
      <button
        type="button"
        onClick={() => setIsCollapsed(false)}
        className="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40 px-3.5 py-2 rounded-xl dark:bg-[#1E2024] bg-white shadow-[0_8px_30px_rgba(0,0,0,0.06)] dark:shadow-[0_8px_30px_rgba(0,0,0,0.4)] border dark:border-[#2D3036] border-[#EBEAE5] flex items-center gap-2.5 dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] transition-colors cursor-pointer animate-fade-in dark:text-[#F3F4F6] text-[#2C2D30]"
        title="Expand upload tray"
        aria-label="Expand upload progress tray"
      >
        {hasActiveUploads ? (
          <svg className="w-4 h-4 shrink-0 -rotate-90" viewBox="0 0 36 36">
            <path
              className="dark:text-[#30363D] text-[#E5E7EB]"
              strokeWidth="4"
              stroke="currentColor"
              fill="none"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
            <path
              className="text-[#10B981] transition-all duration-200"
              strokeDasharray={`${overallPercentage}, 100`}
              strokeLinecap="round"
              strokeWidth="4"
              stroke="currentColor"
              fill="none"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            />
          </svg>
        ) : failedCount > 0 ? (
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-[#10B981] shrink-0" />
        )}

        <span className="text-xs font-medium dark:text-[#F3F4F6] text-[#1F2937]">
          {hasActiveUploads
            ? `Uploading · ${overallPercentage}%`
            : failedCount > 0
            ? `${failedCount} failed`
            : 'All ready'}
        </span>

        <ChevronUp className="w-3.5 h-3.5 dark:text-[#71717A] text-[#9CA3AF] ml-0.5" />
      </button>
    );
  }

  // EXPANDED TRAY: Fixed bottom-right with safe offsets
  return (
    <aside
      aria-label="Upload status tray"
      className="fixed bottom-24 sm:bottom-6 right-4 sm:right-6 z-40 w-[calc(100vw-2rem)] sm:w-[360px] rounded-2xl dark:bg-[#1E2024] bg-white shadow-[0_12px_36px_rgba(0,0,0,0.08)] dark:shadow-[0_12px_36px_rgba(0,0,0,0.45)] border dark:border-[#2D3036] border-[#EBEAE5] overflow-hidden transition-all duration-150 animate-slide-down pb-[env(safe-area-inset-bottom,0px)] dark:text-[#F3F4F6] text-[#2C2D30]"
    >
      {/* Header with Title and Single Collapse Chevron */}
      <div className="flex items-center justify-between px-3.5 py-2.5 dark:bg-[#25272C] bg-[#F7F6F2] border-b dark:border-[#2D3036] border-[#EBEAE5] select-none">
        <div className="flex items-center gap-2 min-w-0">
          {hasActiveUploads ? (
            <Loader2 className="w-3.5 h-3.5 text-[#10B981] animate-spin shrink-0" />
          ) : failedCount > 0 ? (
            <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-[#10B981] shrink-0" />
          )}

          <span className="text-xs font-semibold dark:text-[#F3F4F6] text-[#1F2937] truncate">
            {getHeaderTitle()}
          </span>
        </div>

        <button
          type="button"
          onClick={() => setIsCollapsed(true)}
          className="p-1 rounded-md dark:text-[#71717A] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] dark:hover:bg-[#25272C] hover:bg-[#E5E7EB] transition cursor-pointer"
          title="Collapse tray"
          aria-label="Collapse upload tray"
        >
          <ChevronDown className="w-4 h-4 stroke-[2]" />
        </button>
      </div>

      {/* File Items List */}
      <div className="p-2 space-y-1.5 max-h-64 overflow-y-auto scrollbar-gutter-stable">
        {uploads.map((item) => {
          const isFading = fadingOutIds.includes(item.id);
          const isConfirming = confirmCancelId === item.id;

          return (
            <div
              key={item.id}
              className={`p-2.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] dark:hover:bg-[#282E33] hover:bg-[#F3F4F6] transition-all duration-150 border dark:border-[#2D3036]/70 border-[#EBEAE5] text-xs ${
                isFading ? 'opacity-0 scale-95' : 'opacity-100 scale-100'
              }`}
            >
              {/* Row Top: File Icon, Name, and Right Status/Cancel */}
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <div
                    className={`w-6 h-6 rounded flex items-center justify-center shrink-0 ${
                      item.status === 'ready'
                        ? 'dark:bg-emerald-950/40 bg-emerald-100 text-emerald-600 dark:text-emerald-400'
                        : item.status === 'failed'
                        ? 'dark:bg-red-950/40 bg-red-100 text-red-600 dark:text-red-400'
                        : 'dark:bg-[#1E2024] bg-emerald-50 text-[#10B981]'
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5" />
                  </div>

                  <span
                    className="font-medium dark:text-[#F3F4F6] text-[#1F2937] truncate flex-1 text-[13px]"
                    title={item.fileName}
                  >
                    {item.fileName}
                  </span>
                </div>

                {/* Right side: Live Percentage / Action */}
                <div className="flex items-center gap-1.5 shrink-0">
                  {item.status === 'uploading' && (
                    <span className="w-10 text-right tabular-nums text-xs font-medium text-[#10B981]">
                      {item.progress}%
                    </span>
                  )}
                  {item.status === 'processing' && (
                    <span className="w-10 text-right tabular-nums text-xs font-medium text-[#10B981]">
                      {item.progress}%
                    </span>
                  )}
                  {item.status === 'ready' && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[#10B981]">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Ready</span>
                    </span>
                  )}
                  {item.status === 'failed' && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => retryUpload(item.id)}
                        className="text-[11px] text-red-500 dark:text-red-400 hover:underline font-medium flex items-center gap-1 cursor-pointer"
                        title="Retry upload"
                      >
                        <RotateCw className="w-3 h-3" />
                        <span>Retry</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => removeUpload(item.id)}
                        className="p-1 dark:text-[#71717A] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] transition cursor-pointer"
                        title="Dismiss"
                        aria-label="Dismiss error"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  )}

                  {/* Cancel Button (if active) */}
                  {(item.status === 'uploading' || item.status === 'processing') && (
                    <button
                      type="button"
                      onClick={() => handleCancelClick(item)}
                      className="p-1 rounded dark:text-[#71717A] text-[#9CA3AF] hover:text-red-500 transition cursor-pointer"
                      title="Cancel upload"
                      aria-label="Cancel upload"
                    >
                      <X className="w-3.5 h-3.5 stroke-[2]" />
                    </button>
                  )}
                </div>
              </div>

              {/* Progress Bar */}
              {item.status !== 'ready' && item.status !== 'failed' && (
                <div
                  role="progressbar"
                  aria-valuenow={item.progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="w-full h-1 dark:bg-[#1E2024] bg-[#E5E7EB] rounded-full overflow-hidden my-1"
                >
                  <div
                    className={`h-full bg-[#10B981] rounded-full transition-all duration-200 ${
                      item.isIndeterminate ? 'animate-pulse' : ''
                    }`}
                    style={{ width: `${Math.max(5, item.progress)}%` }}
                  />
                </div>
              )}

              {/* Stage label below bar */}
              <div className="flex items-center justify-between text-[11px] dark:text-[#71717A] text-[#6B7280] mt-0.5">
                <span
                  className={
                    item.status === 'failed'
                      ? 'text-red-500 dark:text-red-400 font-medium'
                      : item.status === 'ready'
                      ? 'text-[#10B981] font-medium'
                      : 'dark:text-[#71717A] text-[#6B7280]'
                  }
                >
                  {getStageLabel(item)}
                </span>
                {item.elapsedProcessingSeconds > 0 && item.status === 'processing' && (
                  <span className="text-[10px] tabular-nums dark:text-[#71717A] text-[#9CA3AF] font-mono">
                    {item.elapsedProcessingSeconds}s
                  </span>
                )}
              </div>

              {/* Confirmation Popover if user cancels during server processing */}
              {isConfirming && (
                <div className="mt-2 p-2 rounded-md dark:bg-red-950/40 bg-red-50 border dark:border-red-900/60 border-red-200 text-xs flex items-center justify-between gap-2 animate-fade-in">
                  <span className="text-[11px] dark:text-red-200 text-red-800 font-medium">
                    Cancel and remove?
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => {
                        cancelUpload(item.id);
                        setConfirmCancelId(null);
                      }}
                      className="px-2 py-0.5 rounded bg-red-600 text-white font-medium text-[10px] hover:bg-red-700 transition cursor-pointer"
                    >
                      Yes, cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmCancelId(null)}
                      className="px-2 py-0.5 rounded dark:bg-[#1E2024] bg-white dark:text-[#A1A1AA] text-[#6B7280] border dark:border-[#2D3036] border-[#EBEAE5] font-medium text-[10px] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] transition cursor-pointer"
                    >
                      Keep
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
};
