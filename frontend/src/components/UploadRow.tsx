import React from 'react';
import {
  FileText,
  X,
  RotateCw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  MessageSquare,
} from 'lucide-react';
import type { UploadItem } from '../context/UploadContext';

interface UploadRowProps {
  item: UploadItem;
  compact?: boolean;
  onCancel?: (id: string) => void;
  onRetry?: (id: string) => void;
  onRemove?: (id: string) => void;
  onAskAbout?: (fileName: string) => void;
  onConfirmDuplicate?: (id: string) => void;
  onCancelDuplicate?: (id: string) => void;
}

export const UploadRow: React.FC<UploadRowProps> = ({
  item,
  compact = false,
  onCancel,
  onRetry,
  onRemove,
  onAskAbout,
  onConfirmDuplicate,
  onCancelDuplicate,
}) => {
  const sizeFormatted =
    item.fileSize > 1048576
      ? `${(item.fileSize / 1048576).toFixed(1)} MB`
      : `${Math.max(1, Math.round(item.fileSize / 1024))} KB`;

  // Processing elapsed time text
  const getProcessingText = () => {
    if (item.elapsedProcessingSeconds >= 90) {
      return 'Taking longer than usual';
    }
    if (item.elapsedProcessingSeconds >= 10) {
      return `Still working… ${item.elapsedProcessingSeconds}s`;
    }
    return 'Preparing your document…';
  };

  // Duplicate prompt variant
  if (item.isDuplicate) {
    return (
      <div
        className={`flex items-center justify-between rounded-lg dark:bg-[#22272D] bg-amber-50/70 border dark:border-amber-500/30 border-amber-300 px-3.5 py-2.5 transition-colors ${
          compact ? 'text-xs' : 'text-sm'
        }`}
      >
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <AlertCircle className="w-4 h-4 text-amber-500 dark:text-amber-400 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-medium dark:text-[#F3F4F6] text-[#1F2937] truncate text-[13px]">
              {item.fileName}
            </p>
            <p className="text-[11px] text-amber-600 dark:text-amber-400/90">
              Already added. Upload again?
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-3">
          <button
            type="button"
            onClick={() => onConfirmDuplicate?.(item.id)}
            className="px-2.5 py-1 text-xs font-medium rounded-md bg-[#10B981] hover:bg-[#059669] text-white transition cursor-pointer"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={() => onCancelDuplicate?.(item.id)}
            className="px-2 py-1 text-xs dark:text-[#71717A] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] transition cursor-pointer"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  // 1. UPLOADING STATE
  if (item.status === 'uploading') {
    return (
      <div
        className="group flex flex-col justify-center px-4 py-3 rounded-xl dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#EBEAE5] shadow-xs transition-colors min-h-[58px]"
      >
        <div className="flex items-center justify-between gap-3 mb-1.5">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <FileText className="w-4 h-4 text-[#10B981] shrink-0" />
            <span
              className="font-medium dark:text-[#F3F4F6] text-[#2C2D30] truncate text-[13px]"
              title={item.fileName}
            >
              {item.fileName}
            </span>
            <span className="text-xs dark:text-[#8E9097] text-[#6B7280] font-mono shrink-0">
              {sizeFormatted}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs font-medium text-[#2C2D30] dark:text-[#F3F4F6] tabular-nums">
              {item.isIndeterminate ? 'Uploading…' : `${item.progress}%`}
            </span>
            <button
              type="button"
              onClick={() => onCancel?.(item.id)}
              aria-label="Cancel upload"
              className="p-1 rounded-full dark:text-[#8E9097] text-[#9CA3AF] hover:text-red-500 transition flex items-center justify-center cursor-pointer"
              title="Cancel upload"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Progress Track */}
        <div
          role="progressbar"
          aria-valuenow={item.progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Upload progress for ${item.fileName}`}
          className="w-full h-1 dark:bg-[#25272C] bg-[#ECEBE5] rounded-full overflow-hidden relative"
        >
          {item.isIndeterminate ? (
            <div className="h-full bg-[#10B981] rounded-full animate-pulse w-1/2" />
          ) : (
            <div
              className="h-full bg-[#10B981] rounded-full transition-all duration-150 ease-out"
              style={{ width: `${Math.max(4, item.progress)}%` }}
            />
          )}
        </div>
      </div>
    );
  }

  // 2. PROCESSING STATE
  if (item.status === 'processing') {
    return (
      <div
        className="group flex flex-col justify-center px-4 py-3 rounded-xl dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#EBEAE5] shadow-xs transition-colors min-h-[58px]"
      >
        <div className="flex items-center justify-between gap-3 mb-1">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Loader2 className="w-4 h-4 text-[#10B981] animate-spin shrink-0" />
            <span
              className="font-medium dark:text-[#F3F4F6] text-[#2C2D30] truncate text-[13px]"
              title={item.fileName}
            >
              {item.fileName}
            </span>
            <span className="text-xs dark:text-[#8E9097] text-[#6B7280] font-mono shrink-0">
              {sizeFormatted}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs font-medium text-[#10B981]">
              {getProcessingText()}
            </span>
            {item.elapsedProcessingSeconds >= 90 && (
              <button
                type="button"
                onClick={() => onRetry?.(item.id)}
                className="text-xs font-medium text-[#10B981] hover:underline flex items-center gap-1 ml-1 cursor-pointer"
              >
                <RotateCw className="w-3 h-3" />
                Retry
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between text-[11px] dark:text-[#8E9097] text-[#6B7280] mt-0.5">
          <span>Preparing chunks and embeddings for search…</span>
        </div>

        {/* Shimmer progress track */}
        <div className="w-full h-1 dark:bg-[#25272C] bg-[#ECEBE5] rounded-full overflow-hidden mt-1.5 relative">
          <div className="h-full bg-[#10B981]/60 rounded-full animate-pulse w-full" />
        </div>
      </div>
    );
  }

  // 3. READY STATE
  if (item.status === 'ready') {
    return (
      <div
        className="group flex items-center justify-between px-4 py-3 rounded-xl dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#E5E4DE] shadow-xs transition-colors min-h-[58px]"
      >
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <div className="w-5 h-5 rounded-full dark:bg-[#25272C] bg-[#ECEBE5] flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-3.5 h-3.5 text-[#2C2D30] dark:text-[#F3F4F6]" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className="font-medium dark:text-[#F3F4F6] text-[#2C2D30] truncate text-[13px]"
                title={item.fileName}
              >
                {item.fileName}
              </span>
              <span className="text-xs dark:text-[#8E9097] text-[#6B7280] font-mono shrink-0">
                {sizeFormatted}
              </span>
            </div>
            <p className="text-xs text-[#6B7280] dark:text-[#9CA3AF] font-normal mt-0.5">
              Ready for Q&A
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-3">
          {onAskAbout && (
            <button
              type="button"
              onClick={() => onAskAbout(item.fileName)}
              className="px-3 py-1.5 rounded-full bg-[#2C2D30] hover:bg-[#1A1B1E] dark:bg-[#F3F4F6] dark:hover:bg-white text-white dark:text-[#141517] text-xs font-medium flex items-center gap-1.5 transition cursor-pointer shadow-xs"
            >
              <MessageSquare className="w-3 h-3 text-[#10B981]" />
              <span>Ask about this</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => onRemove?.(item.id)}
            aria-label="Dismiss row"
            className="p-1 rounded-full dark:text-[#8E9097] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] transition flex items-center justify-center cursor-pointer"
            title="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // 4. FAILED STATE
  return (
    <div
      className="group flex items-center justify-between px-3.5 py-2.5 rounded-lg dark:bg-red-950/20 bg-red-50 border dark:border-red-900/50 border-red-200 transition-colors min-h-[58px]"
    >
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        <div className="w-5 h-5 rounded-full dark:bg-red-900/30 bg-red-100 flex items-center justify-center shrink-0">
          <AlertCircle className="w-3.5 h-3.5 text-red-500 dark:text-red-400" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="font-medium dark:text-[#F3F4F6] text-[#1F2937] truncate text-[13px]"
              title={item.fileName}
            >
              {item.fileName}
            </span>
            <span className="text-xs dark:text-[#71717A] text-[#6B7280] font-mono shrink-0">
              {sizeFormatted}
            </span>
          </div>
          <p className="text-xs text-red-500 dark:text-red-400 mt-0.5">
            {item.error || 'Upload failed'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-3">
        {onRetry && (
          <button
            type="button"
            onClick={() => onRetry(item.id)}
            className="px-2 py-1 rounded-md dark:bg-red-900/40 bg-red-100 hover:bg-red-200 dark:hover:bg-red-900/60 dark:text-red-200 text-red-700 text-xs font-medium flex items-center gap-1 transition cursor-pointer"
          >
            <RotateCw className="w-3 h-3" />
            <span>Retry</span>
          </button>
        )}

        <button
          type="button"
          onClick={() => onRemove?.(item.id)}
          aria-label="Dismiss row"
          className="p-1 rounded dark:text-[#71717A] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#1F2937] transition flex items-center justify-center cursor-pointer"
          title="Dismiss"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
