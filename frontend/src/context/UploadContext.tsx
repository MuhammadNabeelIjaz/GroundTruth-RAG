import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import type { DocumentInfo } from '../types';
import { api } from '../services/api';

export type UploadStage = 'uploading' | 'processing' | 'indexing' | 'ready' | 'failed';
export type UploadStatus = 'uploading' | 'processing' | 'ready' | 'failed';

export interface UploadItem {
  id: string;
  file?: File;
  fileName: string;
  fileSize: number;
  status: UploadStatus;
  stage: UploadStage;
  progress: number; // 0 to 100
  uploadProgress?: number; // 0 to 100 real byte upload percent
  isIndeterminate?: boolean;
  startTime: number;
  processingStartTime?: number;
  elapsedProcessingSeconds: number;
  error?: string;
  xhr?: XMLHttpRequest;
  abortController?: AbortController;
  isDuplicate?: boolean;
  readyTimeout?: ReturnType<typeof setTimeout>;
  isRemoving?: boolean;
}

interface UploadContextType {
  uploads: UploadItem[];
  hasActiveUploads: boolean;
  activeCount: number;
  readyCount: number;
  failedCount: number;
  isTrayOpen: boolean;
  setIsTrayOpen: (open: boolean) => void;
  uploadFiles: (files: File[], forceDuplicate?: boolean) => void;
  cancelUpload: (id: string) => void;
  cancelAllUploads: () => void;
  retryUpload: (id: string) => void;
  removeUpload: (id: string) => void;
  confirmDuplicate: (id: string) => void;
  cancelDuplicate: (id: string) => void;
  isDocumentProcessing: (fileName: string) => boolean;
  onDocumentReadyCallbacks: React.MutableRefObject<Map<string, () => void>>;
}

const UploadContext = createContext<UploadContextType | undefined>(undefined);

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB

export const UploadProvider: React.FC<{
  children: React.ReactNode;
  onDocumentIndexed?: (doc: DocumentInfo) => void;
  onRefreshNeeded?: () => Promise<void>;
  existingDocuments?: DocumentInfo[];
  addToast?: (type: 'success' | 'error' | 'info', message: string) => void;
}> = ({ children, onRefreshNeeded, existingDocuments = [], addToast }) => {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [isTrayOpen, setIsTrayOpen] = useState<boolean>(true);
  const onDocumentReadyCallbacks = useRef<Map<string, () => void>>(new Map());

  // Test hook for automated inspection
  useEffect(() => {
    (window as any).__TEST_SET_UPLOADS = (items: UploadItem[]) => setUploads(items);
    return () => {
      delete (window as any).__TEST_SET_UPLOADS;
    };
  }, []);

  const hasActiveUploads = uploads.some(
    (u) => u.status === 'uploading' || u.status === 'processing'
  );
  const activeCount = uploads.filter(
    (u) => u.status === 'uploading' || u.status === 'processing'
  ).length;
  const readyCount = uploads.filter((u) => u.status === 'ready').length;
  const failedCount = uploads.filter((u) => u.status === 'failed').length;

  // Warn with browser's beforeunload prompt ONLY while a byte upload (not processing) is in progress
  useEffect(() => {
    const hasByteUploadInProgress = uploads.some((u) => u.status === 'uploading');
    if (!hasByteUploadInProgress) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = 'Upload in progress. If you leave now, your upload will be cancelled.';
      return e.returnValue;
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [uploads]);

  // Screen reader aria-live announcements
  const announceToScreenReader = useCallback((message: string) => {
    const announcer = document.getElementById('a11y-upload-announcer');
    if (announcer) {
      announcer.textContent = message;
    }
  }, []);

  // Elapsed processing timer for files in 'processing' status: transitions to 'indexing' after 2-3s
  useEffect(() => {
    const processingItems = uploads.filter((u) => u.status === 'processing');
    if (processingItems.length === 0) return;

    const interval = setInterval(() => {
      setUploads((prev) =>
        prev.map((item) => {
          if (item.status === 'processing') {
            const start = item.processingStartTime || item.startTime;
            const elapsed = Math.floor((Date.now() - start) / 1000);
            // Transition stage from processing (60-90%) to indexing (90-95%)
            let stage: UploadStage = item.stage;
            let progress = item.progress;
            if (elapsed >= 2 && item.stage === 'processing') {
              stage = 'indexing';
              progress = Math.max(item.progress, 90);
              announceToScreenReader(`${item.fileName} indexing.`);
            } else if (item.stage === 'indexing') {
              progress = Math.min(Math.max(item.progress, 90 + Math.min(elapsed - 2, 5)), 95);
            } else {
              progress = Math.min(Math.max(item.progress, 65 + elapsed * 5), 85);
            }
            return {
              ...item,
              stage,
              progress,
              elapsedProcessingSeconds: elapsed,
            };
          }
          return item;
        })
      );
    }, 1000);

    return () => clearInterval(interval);
  }, [uploads, announceToScreenReader]);

  // Internal executor for a single file upload
  const startSingleUpload = useCallback(
    (item: UploadItem) => {
      if (!item.file) return;

      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('files', item.file);

      // Record XHR on item
      setUploads((prev) =>
        prev.map((u) =>
          u.id === item.id
            ? {
                ...u,
                xhr,
                status: 'uploading',
                stage: 'uploading',
                progress: 0,
                uploadProgress: 0,
              }
            : u
        )
      );

      // Real upload progress (mapped to 0-60% of total pipeline)
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const rawPercent = Math.min(Math.round((event.loaded * 100) / event.total), 99);
          const mappedOverall = Math.min(Math.round((event.loaded / event.total) * 60), 60);

          setUploads((prev) =>
            prev.map((u) =>
              u.id === item.id
                ? {
                    ...u,
                    uploadProgress: rawPercent,
                    progress: Math.max(u.progress, mappedOverall),
                    isIndeterminate: false,
                  }
                : u
            )
          );
        } else {
          setUploads((prev) =>
            prev.map((u) =>
              u.id === item.id ? { ...u, isIndeterminate: true } : u
            )
          );
        }
      };

      xhr.upload.onload = () => {
        // Byte upload finished: transition to server-side processing stage (60-90%)
        setUploads((prev) =>
          prev.map((u) =>
            u.id === item.id
              ? {
                  ...u,
                  status: 'processing',
                  stage: 'processing',
                  progress: Math.max(u.progress, 65),
                  isIndeterminate: true,
                  processingStartTime: Date.now(),
                  elapsedProcessingSeconds: 0,
                }
              : u
          )
        );
        announceToScreenReader(`${item.fileName} uploaded. Processing document.`);
      };

      xhr.onload = async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            const fileResult = Array.isArray(response.results) ? response.results[0] : null;
            if (fileResult && fileResult.success === false) {
              const errMsg = fileResult.error || 'Document processing rejected by server.';
              setUploads((prev) =>
                prev.map((u) =>
                  u.id === item.id
                    ? {
                        ...u,
                        status: 'failed',
                        stage: 'failed',
                        error: mapFriendlyError(errMsg),
                      }
                    : u
                )
              );
              announceToScreenReader(`${item.fileName} failed to process.`);
              return;
            }

            // Success! Only now show 100% and 'ready'
            setUploads((prev) =>
              prev.map((u) =>
                u.id === item.id
                  ? {
                      ...u,
                      status: 'ready',
                      stage: 'ready',
                      progress: 100,
                      isIndeterminate: false,
                    }
                  : u
              )
            );
            announceToScreenReader(`${item.fileName} is ready.`);

            // Refresh document list
            if (onRefreshNeeded) {
              await onRefreshNeeded();
            }

            // Fire any waiting callbacks (e.g. queued chat message)
            const cb = onDocumentReadyCallbacks.current.get(item.fileName);
            if (cb) {
              cb();
              onDocumentReadyCallbacks.current.delete(item.fileName);
            }
          } catch {
            setUploads((prev) =>
              prev.map((u) =>
                u.id === item.id
                  ? {
                      ...u,
                      status: 'failed',
                      stage: 'failed',
                      error: 'Server response could not be parsed.',
                    }
                  : u
              )
            );
          }
        } else {
          let errorMsg = 'Server error during upload';
          try {
            const errData = JSON.parse(xhr.responseText);
            errorMsg = errData.detail || errorMsg;
          } catch {}
          setUploads((prev) =>
            prev.map((u) =>
              u.id === item.id
                ? {
                    ...u,
                    status: 'failed',
                    stage: 'failed',
                    error: mapFriendlyError(errorMsg, xhr.status),
                  }
                : u
            )
          );
          announceToScreenReader(`${item.fileName} failed.`);
        }
      };

      xhr.onerror = () => {
        setUploads((prev) =>
          prev.map((u) =>
            u.id === item.id
              ? {
                  ...u,
                  status: 'failed',
                  stage: 'failed',
                  error: 'Upload interrupted. Check your connection.',
                }
              : u
          )
        );
      };

      xhr.onabort = () => {
        // Handled in cancelUpload
      };

      const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
      xhr.open('POST', `${API_BASE_URL}/documents`, true);
      xhr.send(formData);
    },
    [addToast, announceToScreenReader, onRefreshNeeded]
  );

  // Upload handler with validation
  const uploadFiles = useCallback(
    (files: File[], forceDuplicate = false) => {
      if (!files || files.length === 0) return;

      const newItems: UploadItem[] = [];

      for (const file of files) {
        const id = `upload-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
        const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
        const isOverSize = file.size > MAX_FILE_SIZE;

        const isDuplicateExisting = existingDocuments.some(
          (d) => d.file_name.toLowerCase() === file.name.toLowerCase()
        );
        const isDuplicateCurrent = uploads.some(
          (u) =>
            u.fileName.toLowerCase() === file.name.toLowerCase() &&
            u.status !== 'failed'
        );
        const isDuplicate = !forceDuplicate && (isDuplicateExisting || isDuplicateCurrent);

        if (!isPdf) {
          newItems.push({
            id,
            file,
            fileName: file.name,
            fileSize: file.size,
            status: 'failed',
            stage: 'failed',
            progress: 0,
            startTime: Date.now(),
            elapsedProcessingSeconds: 0,
            error: 'Only PDF files are supported',
          });
        } else if (isOverSize) {
          newItems.push({
            id,
            file,
            fileName: file.name,
            fileSize: file.size,
            status: 'failed',
            stage: 'failed',
            progress: 0,
            startTime: Date.now(),
            elapsedProcessingSeconds: 0,
            error: 'File is larger than 20 MB',
          });
        } else if (isDuplicate) {
          newItems.push({
            id,
            file,
            fileName: file.name,
            fileSize: file.size,
            status: 'failed',
            stage: 'failed',
            progress: 0,
            startTime: Date.now(),
            elapsedProcessingSeconds: 0,
            isDuplicate: true,
            error: 'Already added. Upload again?',
          });
        } else {
          newItems.push({
            id,
            file,
            fileName: file.name,
            fileSize: file.size,
            status: 'uploading',
            stage: 'uploading',
            progress: 0,
            uploadProgress: 0,
            startTime: Date.now(),
            elapsedProcessingSeconds: 0,
          });
        }
      }

      setUploads((prev) => [...newItems, ...prev]);
      setIsTrayOpen(true);

      for (const item of newItems) {
        if (item.status === 'uploading') {
          startSingleUpload(item);
        }
      }
    },
    [existingDocuments, startSingleUpload, uploads]
  );

  const confirmDuplicate = useCallback(
    (id: string) => {
      const target = uploads.find((u) => u.id === id);
      if (target && target.file) {
        setUploads((prev) =>
          prev.map((u) =>
            u.id === id
              ? {
                  ...u,
                  status: 'uploading',
                  stage: 'uploading',
                  isDuplicate: false,
                  error: undefined,
                  progress: 0,
                }
              : u
          )
        );
        startSingleUpload({
          ...target,
          status: 'uploading',
          stage: 'uploading',
          isDuplicate: false,
          progress: 0,
        });
      }
    },
    [startSingleUpload, uploads]
  );

  const cancelDuplicate = useCallback((id: string) => {
    setUploads((prev) => prev.filter((u) => u.id !== id));
  }, []);

  const cancelUpload = useCallback((id: string) => {
    setUploads((prev) => {
      const item = prev.find((u) => u.id === id);
      if (item?.xhr) {
        try {
          item.xhr.abort();
        } catch {}
      }
      if (item?.fileName) {
        // Abort partial upload & remove partial server document if one was created
        api.deleteDocument(item.fileName).catch(() => {});
      }
      return prev.filter((u) => u.id !== id);
    });
  }, []);

  const cancelAllUploads = useCallback(() => {
    setUploads((prev) => {
      for (const item of prev) {
        if (item.xhr) {
          try {
            item.xhr.abort();
          } catch {}
        }
        if (item.fileName) {
          api.deleteDocument(item.fileName).catch(() => {});
        }
      }
      return prev.filter((u) => u.status === 'ready');
    });
  }, []);

  const retryUpload = useCallback(
    (id: string) => {
      const target = uploads.find((u) => u.id === id);
      if (target && target.file) {
        setUploads((prev) =>
          prev.map((u) =>
            u.id === id
              ? {
                  ...u,
                  status: 'uploading',
                  stage: 'uploading',
                  error: undefined,
                  progress: 0,
                  startTime: Date.now(),
                  elapsedProcessingSeconds: 0,
                }
              : u
          )
        );
        startSingleUpload(target);
      }
    },
    [startSingleUpload, uploads]
  );

  const removeUpload = useCallback((id: string) => {
    setUploads((prev) => prev.filter((u) => u.id !== id));
  }, []);

  const isDocumentProcessing = useCallback(
    (fileName: string) => {
      return uploads.some(
        (u) =>
          u.fileName.toLowerCase() === fileName.toLowerCase() &&
          (u.status === 'uploading' || u.status === 'processing')
      );
    },
    [uploads]
  );

  return (
    <UploadContext.Provider
      value={{
        uploads,
        hasActiveUploads,
        activeCount,
        readyCount,
        failedCount,
        isTrayOpen,
        setIsTrayOpen,
        uploadFiles,
        cancelUpload,
        cancelAllUploads,
        retryUpload,
        removeUpload,
        confirmDuplicate,
        cancelDuplicate,
        isDocumentProcessing,
        onDocumentReadyCallbacks,
      }}
    >
      {/* Screen reader live notification node */}
      <div
        id="a11y-upload-announcer"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      />
      {children}
    </UploadContext.Provider>
  );
};

export const useUpload = (): UploadContextType => {
  const context = useContext(UploadContext);
  if (!context) {
    throw new Error('useUpload must be used within an UploadProvider');
  }
  return context;
};

function mapFriendlyError(rawError: string, status?: number): string {
  const err = (rawError || '').toLowerCase();
  if (status === 413 || err.includes('larger than') || err.includes('too large')) {
    return 'File is larger than 20 MB';
  }
  if (status === 415 || err.includes('only pdf') || err.includes('not a pdf') || err.includes('extension')) {
    return 'Only PDF files are supported';
  }
  if (err.includes('corrupt') || err.includes('unusable') || err.includes('no text') || err.includes('encrypted')) {
    return "We couldn't read this PDF. It may be scanned or protected.";
  }
  if (err.includes('network') || err.includes('connection') || err.includes('interrupted')) {
    return 'Upload interrupted. Check your connection.';
  }
  if (err.includes('duplicate') || status === 409) {
    return 'Already added. Upload again?';
  }
  return rawError || 'Upload failed. Please try again.';
}
