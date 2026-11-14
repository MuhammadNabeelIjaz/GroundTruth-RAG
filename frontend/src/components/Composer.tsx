import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  ArrowUp,
  Square,
  ChevronDown,
  Check,
  FileText,
  Clock,
  AlertCircle,
  X,
  Mic,
  Paperclip,
  Upload,
} from 'lucide-react';
import { useChat } from '../context/ChatContext';
import { useUpload } from '../context/UploadContext';
import { useVoiceInput } from '../hooks/useVoiceInput';
import { AudioWaveform } from './AudioWaveform';

export const Composer: React.FC = () => {
  const {
    sendMessage,
    isLoading,
    documents,
    selectedDocumentNames,
    setSelectedDocumentNames,
    defaultScope,
    toggleDocumentSelection,
    selectAllDocuments,
    clearDocumentSelection,
    activeConversationId,
    draftText,
    setDraftText,
    composerFocusTrigger,
    composerPulseTrigger,
    addToast,
    setCurrentPage,
    isDocSelectorOpen,
    setIsDocSelectorOpen,
  } = useChat();

  const { uploads, onDocumentReadyCallbacks, cancelUpload, uploadFiles } = useUpload();

  const [inputText, setInputText] = useState('');

  // Check URL params on initial load
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get('attach') === 'true' || params.get('scope') === 'true') {
        setIsDocSelectorOpen(true);
      }
    } catch {
      // ignore
    }
  }, [setIsDocSelectorOpen]);
  const [isPulsing, setIsPulsing] = useState(false);
  const [queuedNotice, setQueuedNotice] = useState<string | null>(null);
  const [showDocRequiredHint, setShowDocRequiredHint] = useState(false);
  const [voiceAnnouncement, setVoiceAnnouncement] = useState('');

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const scopeButtonRef = useRef<HTMLButtonElement>(null);
  const queuedMessageRef = useRef<string | null>(null);
  const preVoiceTextRef = useRef<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOverComposer, setIsDragOverComposer] = useState(false);
  const dragCounterRef = useRef<number>(0);

  const handleTriggerFileUpload = () => {
    fileInputRef.current?.click();
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const rawFiles = Array.from(files);
    const pdfFiles = rawFiles.filter(
      (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
    );

    if (pdfFiles.length === 0) {
      addToast('error', 'Please select PDF documents only.');
      e.target.value = '';
      return;
    }

    const overSized = pdfFiles.filter((f) => f.size > 20 * 1024 * 1024);
    if (overSized.length > 0) {
      addToast('error', 'File size exceeds 20MB limit.');
      e.target.value = '';
      return;
    }

    uploadFiles(pdfFiles);
    const newNames = pdfFiles.map((f) => f.name);
    setSelectedDocumentNames(Array.from(new Set([...selectedDocumentNames, ...newNames])));

    setIsDocSelectorOpen(false);
    e.target.value = '';
    textareaRef.current?.focus();
  };

  const handleComposerDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragOverComposer(true);
    }
  };

  const handleComposerDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragOverComposer(false);
    }
  };

  const handleComposerDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleComposerDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOverComposer(false);
    dragCounterRef.current = 0;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const rawFiles = Array.from(e.dataTransfer.files);
      const pdfFiles = rawFiles.filter(
        (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
      );
      if (pdfFiles.length > 0) {
        uploadFiles(pdfFiles);
        const newNames = pdfFiles.map((f) => f.name);
        setSelectedDocumentNames(Array.from(new Set([...selectedDocumentNames, ...newNames])));
        textareaRef.current?.focus();
      } else {
        addToast('error', 'Please drop PDF documents only.');
      }
    }
  };

  // Voice dictation integration
  const onTranscriptUpdate = useCallback(
    (fullDictatedText: string) => {
      const base = preVoiceTextRef.current;
      const combined = base
        ? `${base.trimEnd()} ${fullDictatedText.trimStart()}`
        : fullDictatedText;
      setInputText(combined);

      // Auto-grow and scroll caret into view
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 144)}px`;
        textareaRef.current.scrollTop = textareaRef.current.scrollHeight;
        textareaRef.current.setSelectionRange(combined.length, combined.length);
      }
    },
    []
  );

  const onAutoConfirmVoice = useCallback((finalText: string) => {
    const base = preVoiceTextRef.current;
    const combined = base
      ? `${base.trimEnd()} ${finalText.trimStart()}`
      : finalText;
    setInputText(combined);
    setVoiceAnnouncement('Recording stopped');
  }, []);

  const voice = useVoiceInput(onTranscriptUpdate, onAutoConfirmVoice);
  const isRecording = voice.state === 'recording' || voice.state === 'requesting';

  const handleStartVoice = async () => {
    preVoiceTextRef.current = inputText;
    setVoiceAnnouncement('Recording started');
    await voice.start();
  };

  const handleConfirmVoice = () => {
    voice.stop();
    setVoiceAnnouncement('Recording stopped');
    textareaRef.current?.focus();
    if (textareaRef.current) {
      const len = textareaRef.current.value.length;
      textareaRef.current.setSelectionRange(len, len);
    }
  };

  const handleCancelVoice = () => {
    voice.cancel();
    setInputText(preVoiceTextRef.current);
    setVoiceAnnouncement('Recording cancelled');
    textareaRef.current?.focus();
  };

  // Compute if at least one document is selected or all documents are in scope
  const isDocumentSelected = useMemo(() => {
    if (selectedDocumentNames.length > 0) return true;
    if (defaultScope === 'all' && documents.length > 0) return true;
    return false;
  }, [selectedDocumentNames, defaultScope, documents]);

  // Dismiss inline hint when document selection becomes valid
  useEffect(() => {
    if (isDocumentSelected) {
      setShowDocRequiredHint(false);
    }
  }, [isDocumentSelected]);

  // Check if any selected document is still uploading or processing
  const processingSelectedDoc = useMemo(() => {
    return uploads.find(
      (u) =>
        (u.status === 'uploading' || u.status === 'processing') &&
        (selectedDocumentNames.includes(u.fileName) ||
          (selectedDocumentNames.length === 0 &&
            defaultScope === 'all' &&
            documents.some((d) => d.file_name === u.fileName)))
    );
  }, [uploads, selectedDocumentNames, defaultScope, documents]);

  // Brief green flash when a processing document finishes and becomes ready
  const [justBecameReady, setJustBecameReady] = useState(false);
  const prevProcessingRef = useRef<boolean>(false);

  useEffect(() => {
    const isNowProcessing = Boolean(processingSelectedDoc);
    if (prevProcessingRef.current && !isNowProcessing) {
      setJustBecameReady(true);
      const timer = setTimeout(() => setJustBecameReady(false), 1200);
      return () => clearTimeout(timer);
    }
    prevProcessingRef.current = isNowProcessing;
  }, [processingSelectedDoc]);

  // Restore draft text when draftText changes
  useEffect(() => {
    if (draftText !== undefined) {
      setInputText(draftText);
    }
  }, [draftText]);

  // Focus textarea when trigger changes
  useEffect(() => {
    if (composerFocusTrigger > 0 && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [composerFocusTrigger]);

  // Pulse focus ring when pulse trigger changes
  useEffect(() => {
    if (composerPulseTrigger > 0) {
      setIsPulsing(true);
      const timer = setTimeout(() => setIsPulsing(false), 300);
      return () => clearTimeout(timer);
    }
  }, [composerPulseTrigger]);

  // Auto-grow textarea height up to 6 lines (~144px)
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 144)}px`;
    }
  }, [inputText]);

  // Close scope popover on click outside or Esc
  useEffect(() => {
    if (!isDocSelectorOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        popoverRef.current &&
        !popoverRef.current.contains(target) &&
        scopeButtonRef.current &&
        !scopeButtonRef.current.contains(target)
      ) {
        setIsDocSelectorOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsDocSelectorOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isDocSelectorOpen, setIsDocSelectorOpen]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputText(val);
    if (activeConversationId === null) {
      setDraftText(val);
    }
  };

  // Safe question queuing if document is still processing
  const executeSend = useCallback(
    async (textToSend: string) => {
      setInputText('');
      if (activeConversationId === null) {
        setDraftText('');
      }
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
      setQueuedNotice(null);
      queuedMessageRef.current = null;
      await sendMessage(textToSend);
    },
    [activeConversationId, sendMessage, setDraftText]
  );

  const handleSubmit = async () => {
    const trimmed = inputText.trim();
    if (!trimmed) return;
    if (isLoading) return;

    if (!isDocumentSelected) {
      setIsDocSelectorOpen(true);
      setShowDocRequiredHint(true);
      return;
    }

    // Check if any selected document is still uploading or processing
    const processingItem = uploads.find(
      (u) =>
        (u.status === 'uploading' || u.status === 'processing') &&
        selectedDocumentNames.includes(u.fileName)
    );

    if (processingItem && trimmed) {
      setQueuedNotice(
        'Your document is still being prepared. Your answer will use it once it’s ready.'
      );
      queuedMessageRef.current = trimmed;
      setInputText('');
      if (activeConversationId === null) {
        setDraftText('');
      }

      onDocumentReadyCallbacks.current.set(processingItem.fileName, () => {
        if (queuedMessageRef.current) {
          executeSend(queuedMessageRef.current);
        }
      });
      return;
    }

    await executeSend(trimmed);
  };

  const handleSendAttempt = () => {
    if (isLoading) return;
    if (!isDocumentSelected) {
      setIsDocSelectorOpen(true);
      setShowDocRequiredHint(true);
      return;
    }
    const trimmed = inputText.trim();
    if (!trimmed) {
      textareaRef.current?.focus();
      return;
    }
    if (processingSelectedDoc) {
      setQueuedNotice('Your question will be sent when the document is ready.');
      queuedMessageRef.current = trimmed;
      setInputText('');
      if (activeConversationId === null) {
        setDraftText('');
      }
      onDocumentReadyCallbacks.current.set(processingSelectedDoc.fileName, () => {
        if (queuedMessageRef.current) {
          executeSend(queuedMessageRef.current);
        }
      });
      return;
    }
    handleSubmit();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isRecording) {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleCancelVoice();
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) {
          handleConfirmVoice();
        } else {
          handleConfirmVoice();
          setTimeout(() => {
            handleSendAttempt();
          }, 50);
        }
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendAttempt();
    }
  };

  const canSubmit =
    Boolean(inputText.trim()) &&
    isDocumentSelected &&
    !processingSelectedDoc &&
    !isLoading;

  const scopeButtonLabel = useMemo(() => {
    if (!isDocumentSelected) {
      return 'Select document first';
    }
    if (selectedDocumentNames.length === 1) {
      return selectedDocumentNames[0];
    }
    if (selectedDocumentNames.length > 1) {
      return `${selectedDocumentNames.length} documents`;
    }
    if (documents.length === 1) {
      return documents[0].file_name;
    }
    return `${documents.length} documents`;
  }, [isDocumentSelected, selectedDocumentNames, documents]);

  return (
    <div className="w-full max-w-[720px] mx-auto relative z-30 pb-[env(safe-area-inset-bottom,0px)]">
      {/* Gentle Queue Notice Banner */}
      {queuedNotice && (
        <div className="mb-2 px-3.5 py-2 rounded-xl dark:bg-[#1E2024] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#EBEAE5] text-xs dark:text-[#F3F4F6] text-[#2C2D30] flex items-center justify-between gap-3 animate-fade-in shadow-xs">
          <div className="flex items-center gap-2 min-w-0">
            <Clock className="w-3.5 h-3.5 text-[#10B981] shrink-0 animate-pulse" />
            <span className="font-medium truncate">{queuedNotice}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              setQueuedNotice(null);
              queuedMessageRef.current = null;
            }}
            className="text-xs text-[#10B981] hover:underline shrink-0 font-medium cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Composer Capsule (Spacious, rounded-2xl/3xl, soft diffused elevation shadow) */}
      <div
        onDragEnter={handleComposerDragEnter}
        onDragLeave={handleComposerDragLeave}
        onDragOver={handleComposerDragOver}
        onDrop={handleComposerDrop}
        className={`relative rounded-2xl sm:rounded-3xl min-h-[60px] dark:bg-[#1E2024] bg-white border ${isDragOverComposer
          ? 'border-dashed border-[#10B981] ring-2 ring-[#10B981]/30 dark:bg-emerald-950/20 bg-emerald-50/40'
          : 'dark:border-[#2D3036] border-[#EBEAE5]'
          } shadow-[0_4px_24px_rgba(0,0,0,0.04)] dark:shadow-[0_4px_24px_rgba(0,0,0,0.35)] p-3 sm:px-4 sm:py-3 transition-colors duration-150 focus-within:border-[#10B981]/60 dark:focus-within:border-[#10B981]/60 ${isPulsing ? 'animate-focus-pulse' : ''
          }`}
      >
        {/* Drop Overlay when dragging file over composer */}
        {isDragOverComposer && (
          <div className="absolute inset-0 z-50 rounded-2xl sm:rounded-3xl bg-[#FAF9F5]/90 dark:bg-[#1E2024]/90 backdrop-blur-xs border-2 border-dashed border-[#10B981] flex items-center justify-center gap-2 text-xs font-medium text-[#10B981] pointer-events-none animate-fade-in">
            <Upload className="w-4 h-4 animate-bounce" />
            <span>Drop PDF to attach and upload</span>
          </div>
        )}

        {/* Scope & Attachment Popover */}
        {isDocSelectorOpen && (
          <div
            ref={popoverRef}
            className="absolute left-0 sm:left-2 bottom-[calc(100%+8px)] z-[70] w-80 sm:w-84 max-w-[calc(100vw-32px)] max-h-[min(300px,calc(100dvh-350px))] p-2.5 sm:p-3 dark:bg-[#1E2024] bg-white border dark:border-[#2D3036] border-[#EBEAE5] rounded-2xl shadow-[0_12px_36px_rgba(0,0,0,0.08)] dark:shadow-[0_12px_36px_rgba(0,0,0,0.5)] animate-slide-up flex flex-col space-y-1.5"
          >
            {/* Popover Header (Seamless, zero horizontal border line) */}
            <div className="flex items-center justify-between pb-0.5 select-none">
              <div className="flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-[#10B981]" />
                <span className="text-xs font-semibold dark:text-[#F3F4F6] text-[#2C2D30]">
                  Active Documents
                </span>
              </div>
              <button
                type="button"
                onClick={() => setIsDocSelectorOpen(false)}
                className="w-5 h-5 rounded-full flex items-center justify-center dark:text-[#8E9097] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] hover:bg-[#F0EFEA] dark:hover:bg-[#25272C] transition cursor-pointer"
                title="Close"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Notice if no documents selected */}
            {!isDocumentSelected && (
              <div className="p-1.5 rounded-lg dark:bg-[#25272C] bg-[#F7F6F2] border border-[#E5E4DE] dark:border-[#33363D] text-[11px] dark:text-[#E5E7EB] text-[#4B5563] flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0 text-[#10B981]" />
                <span>Select or upload a document to attach.</span>
              </div>
            )}

            {/* Bulk controls and library header */}
            {documents.length > 0 && (
              <div className="flex items-center justify-between text-xs px-0.5 dark:text-[#8E9097] text-[#6B7280] select-none">
                <span className="text-[11px] font-medium">
                  {selectedDocumentNames.length > 0
                    ? `${selectedDocumentNames.length} of ${documents.length} attached`
                    : defaultScope === 'all'
                      ? `All ${documents.length} attached`
                      : 'Select from library'}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={selectAllDocuments}
                    className="hover:text-[#10B981] font-medium transition cursor-pointer"
                  >
                    Select all
                  </button>
                  <span>•</span>
                  <button
                    type="button"
                    onClick={clearDocumentSelection}
                    className="hover:text-red-500 font-medium transition cursor-pointer"
                  >
                    Clear
                  </button>
                </div>
              </div>
            )}

            {/* Checkbox document list */}
            <div className="max-h-48 overflow-y-auto space-y-0.5 pr-0.5">
              {documents.length > 0 ? (
                documents.map((doc) => {
                  const isChecked = defaultScope === 'all'
                    ? (selectedDocumentNames.length === 0 || selectedDocumentNames.includes(doc.file_name))
                    : selectedDocumentNames.includes(doc.file_name);
                  return (
                    <div
                      key={doc.file_name}
                      onClick={() => toggleDocumentSelection(doc.file_name)}
                      className="flex items-center gap-2 py-1 px-1.5 rounded-lg dark:hover:bg-[#25272C] hover:bg-[#F7F6F2] cursor-pointer text-[12.5px] select-none transition"
                    >
                      <div
                        className={`w-3.5 h-3.5 rounded flex items-center justify-center transition shrink-0 ${isChecked
                          ? 'bg-[#10B981] text-white'
                          : 'dark:bg-[#25272C] bg-white border dark:border-[#383C45] border-[#D1D0C7]'
                          }`}
                      >
                        {isChecked && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                      </div>
                      <span
                        className="truncate flex-1 dark:text-[#F3F4F6] text-[#2C2D30] leading-tight"
                        title={doc.file_name}
                      >
                        {doc.file_name}
                      </span>
                      <span className="text-[10px] font-mono dark:text-[#8E9097] text-[#9CA3AF] shrink-0">
                        {doc.chunk_count}p
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="py-2 text-center text-xs dark:text-[#8E9097] text-[#9CA3AF] space-y-0.5">
                  <div>No documents in library yet.</div>
                  <div className="text-[11px] text-[#10B981]">Upload a PDF above to attach it!</div>
                </div>
              )}
            </div>

            {/* "View All in Documents" Option */}
            {documents.length > 0 && (
              <div className="pt-1 flex items-center justify-between px-0.5 text-xs select-none">
                <span className="text-[11px] dark:text-[#8E9097] text-[#6B7280]">
                  {selectedDocumentNames.length > 0
                    ? `${selectedDocumentNames.length} selected`
                    : defaultScope === 'all'
                      ? 'All selected'
                      : 'None selected'}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setIsDocSelectorOpen(false);
                    setCurrentPage('library');
                  }}
                  className="text-[11.5px] font-medium text-[#10B981] hover:underline flex items-center gap-1 cursor-pointer transition-colors"
                  title="Move to Documents section to choose and manage all documents"
                >
                  <span>View all in Documents</span>
                  <span aria-hidden="true">→</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* Row 1: Auto-growing Textarea */}
        <div className="w-full px-1 pt-0.5">
          <textarea
            ref={textareaRef}
            value={inputText}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="How can I help you today?"
            rows={1}
            disabled={isLoading}
            className="w-full max-h-36 py-1 text-[15px] sm:text-[16px] font-sans dark:text-[#F3F4F6] text-[#2C2D30] bg-transparent outline-none resize-none dark:placeholder:text-[#71737A] placeholder:text-[#9CA3AF] leading-relaxed"
          />
        </div>

        {/* Row 2: Document attachment & selector on Left, Voice & Send on Right */}
        <div className="flex items-center justify-between pt-2 px-0.5 relative">
          <div className={`flex items-center gap-1.5 ${isRecording ? 'opacity-80 pointer-events-none' : ''}`}>
            {/* Dedicated Document Attachment Button (Paperclip) - Directly opens file browser */}
            <button
              type="button"
              onClick={handleTriggerFileUpload}
              disabled={isLoading}
              className="w-8 h-8 rounded-full flex items-center justify-center transition select-none cursor-pointer shrink-0 dark:text-[#9CA3AF] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] dark:hover:bg-[#25272C] hover:bg-[#F0EFEA]"
              title="Upload PDF from computer"
              aria-label="Upload PDF from computer"
            >
              <Paperclip className="w-4 h-4 stroke-[1.75]" />
            </button>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              multiple
              onChange={handleFileInputChange}
              className="hidden"
              aria-label="Upload PDF files"
            />

            {/* Status Chip while processing, or normal Scope Button Chip */}
            {processingSelectedDoc ? (
              <div
                className="h-8 max-w-[280px] px-3 rounded-full text-[12px] font-medium flex items-center gap-2 dark:bg-[#25272C] bg-[#F4F3EE] border border-[#E5E4DE] dark:border-[#33363D] dark:text-[#F3F4F6] text-[#2C2D30] select-none"
                title={`${processingSelectedDoc.fileName} (${processingSelectedDoc.progress}%)`}
              >
                <div className="relative w-3.5 h-3.5 shrink-0 flex items-center justify-center">
                  <svg className="w-3.5 h-3.5 -rotate-90 transform" viewBox="0 0 36 36">
                    <path
                      className="dark:text-[#383C45] text-[#E5E4DE]"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                    <path
                      className="text-[#10B981] transition-all duration-200"
                      strokeDasharray={`${processingSelectedDoc.progress}, 100`}
                      strokeLinecap="round"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                  </svg>
                </div>
                <span className="truncate max-w-[140px] dark:text-[#F3F4F6] text-[#2C2D30] font-medium">
                  {processingSelectedDoc.fileName}
                </span>
                <span className="text-[11px] dark:text-[#8E9097] text-[#6B7280] shrink-0 tabular-nums">
                  · {processingSelectedDoc.progress}%
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    cancelUpload(processingSelectedDoc.id);
                  }}
                  className="w-4 h-4 rounded-full dark:hover:bg-[#383C45] hover:bg-[#E5E4DE] flex items-center justify-center dark:text-[#8E9097] text-[#6B7280] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] shrink-0 transition"
                  title="Cancel upload"
                  aria-label="Cancel upload"
                >
                  <X className="w-3 h-3 stroke-[2.5]" />
                </button>
              </div>
            ) : (
              <button
                ref={scopeButtonRef}
                type="button"
                onClick={() => setIsDocSelectorOpen(!isDocSelectorOpen)}
                className={`h-8 max-w-[280px] px-3 rounded-full text-[12px] font-normal flex items-center gap-1.5 transition select-none cursor-pointer border ${justBecameReady
                  ? 'dark:bg-[#25272C] bg-[#ECEBE5] text-[#10B981] border-[#10B981]/50'
                  : isDocSelectorOpen
                    ? 'dark:bg-emerald-950/30 bg-emerald-50 text-[#10B981] border-[#10B981]/50 font-medium'
                    : !isDocumentSelected
                      ? 'dark:bg-[#25272C] bg-[#F4F3EE] text-[#6B7280] dark:text-[#9CA3AF] border-[#E5E4DE] dark:border-[#33363D]'
                      : 'dark:bg-[#25272C] bg-[#F4F3EE] dark:text-[#E5E7EB] text-[#374151] hover:bg-[#ECEBE5] dark:hover:bg-[#2D3037] border-[#E5E4DE] dark:border-[#33363D]'
                  }`}
                title={!isDocumentSelected ? 'Select document first' : scopeButtonLabel}
                aria-label="Select reference documents"
                aria-expanded={isDocSelectorOpen}
              >
                <FileText
                  className={`w-3.5 h-3.5 stroke-[1.75] shrink-0 transition-colors ${
                    isDocSelectorOpen ? 'text-[#10B981]' : 'dark:text-[#9CA3AF] text-[#6B7280]'
                  }`}
                />
                <span className={`truncate ${isDocSelectorOpen ? 'text-[#10B981] font-medium' : ''}`}>
                  {scopeButtonLabel}
                </span>
                <ChevronDown
                  className={`w-3 h-3 shrink-0 transition-transform ${
                    isDocSelectorOpen
                      ? 'rotate-180 text-[#10B981]'
                      : 'dark:text-[#8E9097] text-[#9CA3AF]'
                  }`}
                />
              </button>
            )}
          </div>

          {/* Right Toolbar: Voice Dictation Mode or Normal Mode */}
          <div className="flex items-center gap-1.5">
            {isRecording ? (
              /* Active Dictation Bar (Fixed exact h-8 to prevent any height jitter) */
              <div className="h-8 flex items-center gap-1.5 dark:bg-[#25272C] bg-[#F0EFEA] px-2.5 rounded-full border dark:border-[#2D3036] border-[#E5E4DE] animate-fade-in select-none">
                {/* Language Switcher */}
                <button
                  type="button"
                  onClick={() => voice.setLang(voice.currentLang === 'en-IN' ? 'hi-IN' : 'en-IN')}
                  className="h-5 px-1.5 rounded-full text-[11px] font-medium dark:bg-[#1E2024] bg-white text-[#10B981] border dark:border-[#33363D] border-[#E5E4DE] dark:hover:bg-[#282E33] hover:bg-gray-100 transition cursor-pointer select-none"
                  title={`Language: ${voice.currentLang === 'en-IN' ? 'English (India)' : 'Hindi'}. Click to toggle.`}
                  aria-label="Toggle voice dictation language"
                >
                  {voice.currentLang === 'en-IN' ? 'EN' : 'हिं'}
                </button>

                {/* Elapsed Timer */}
                <span className="text-[11px] font-mono tabular-nums dark:text-[#8E9097] text-[#6B7280] select-none">
                  {Math.floor(voice.elapsedSeconds / 60)}:
                  {String(voice.elapsedSeconds % 60).padStart(2, '0')}
                </span>

                {/* Audio Waveform */}
                <AudioWaveform analyserNode={voice.analyserNode} barCount={14} />

                {/* Cancel X button */}
                <button
                  type="button"
                  onClick={handleCancelVoice}
                  className="w-5 h-5 rounded-full flex items-center justify-center dark:text-[#8E9097] text-[#6B7280] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition cursor-pointer"
                  title="Discard dictation (Esc)"
                  aria-label="Cancel voice input"
                >
                  <X className="w-3.5 h-3.5" />
                </button>

                {/* Done Check button */}
                <button
                  type="button"
                  onClick={handleConfirmVoice}
                  className="w-5 h-5 rounded-full flex items-center justify-center bg-[#10B981] hover:bg-[#059669] text-white transition cursor-pointer active:scale-95"
                  title="Done (commit dictated text)"
                  aria-label="Finish voice dictation"
                >
                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                </button>
              </div>
            ) : (
              /* Normal Mode: Mic + Send buttons */
              <>
                {voice.supported && (
                  <button
                    type="button"
                    onClick={handleStartVoice}
                    disabled={isLoading}
                    className="w-8 h-8 rounded-full flex items-center justify-center dark:text-[#9CA3AF] text-[#6B7280] hover:text-[#10B981] dark:hover:text-[#10B981] dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] transition cursor-pointer select-none active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
                    title="Dictate"
                    aria-label="Start voice input"
                  >
                    <Mic className="w-4 h-4" />
                  </button>
                )}

                {/* Send / Stop button (Project green when active, subtle disabled) */}
                <button
                  type="button"
                  onClick={handleSendAttempt}
                  disabled={isLoading}
                  aria-disabled={!canSubmit}
                  className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-all duration-150 ${isLoading
                    ? 'bg-[#10B981] text-white hover:bg-[#059669] cursor-pointer'
                    : canSubmit
                      ? 'bg-[#10B981] hover:bg-[#059669] text-white shadow-xs active:scale-95 cursor-pointer'
                      : 'dark:bg-[#25272C] bg-[#EBEAE5] text-[#9CA3AF] dark:text-[#71737A] cursor-not-allowed'
                    }`}
                  title={
                    isLoading
                      ? 'Stop'
                      : processingSelectedDoc
                        ? `Waiting for document to finish processing (${processingSelectedDoc.progress}%)`
                        : !isDocumentSelected
                          ? 'Select at least one document to continue'
                          : !inputText.trim()
                            ? 'Type a question to send'
                            : 'Send message (Enter)'
                  }
                  aria-label={isLoading ? 'Stop' : 'Send message'}
                >
                  {isLoading ? (
                    <Square className="w-3 h-3 fill-current" />
                  ) : (
                    <ArrowUp className="w-4 h-4 stroke-[2.5]" />
                  )}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Screen reader live announcement */}
      <div className="sr-only" aria-live="polite" role="status">
        {voiceAnnouncement}
      </div>

      {/* Voice error notice */}
      {voice.error && (
        <div className="mt-2 text-xs font-medium text-red-400 select-none animate-fade-in flex items-center justify-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{voice.error}</span>
        </div>
      )}

      {/* Voice inactivity hint */}
      {voice.hint && isRecording && (
        <div className="absolute left-1/2 -translate-x-1/2 -bottom-7 text-[11px] text-[#71717A] bg-white dark:bg-[#1C2025] px-2 py-0.5 rounded border dark:border-[#30363D] border-[#E5E7EB] shadow-xs select-none animate-fade-in pointer-events-none whitespace-nowrap z-20">
          {voice.hint}
        </div>
      )}

      {/* Small inline hint under composer when no document is selected */}
      {showDocRequiredHint && (
        <div className="mt-2 text-xs font-normal text-[#10B981] select-none animate-fade-in flex items-center justify-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 text-[#10B981]" />
          <span>Select at least one document to continue.</span>
        </div>
      )}
    </div>
  );
};