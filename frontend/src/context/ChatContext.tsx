import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { api, extractErrorMessage } from '../services/api';
import type {
  DocumentInfo,
  ConversationResponse,
  MessageItem,
} from '../types';

interface Toast {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

export function parseAppUrl(): { page: 'chat' | 'library'; chatId: string | null } {
  try {
    const params = new URLSearchParams(window.location.search);
    const view = params.get('view') || params.get('page');
    const isLibrary = view === 'library' || view === 'documents';
    const chatId = params.get('chat') || params.get('c') || null;
    return {
      page: isLibrary ? 'library' : 'chat',
      chatId,
    };
  } catch {
    return { page: 'chat', chatId: null };
  }
}

export function syncAppUrl(options: {
  page?: 'chat' | 'library';
  chatId?: string | null;
  replace?: boolean;
}) {
  try {
    const url = new URL(window.location.href);

    if (options.page === 'library') {
      url.searchParams.set('view', 'documents');
      url.searchParams.delete('chat');
      url.searchParams.delete('c');
    } else {
      url.searchParams.delete('view');
      url.searchParams.delete('page');
      if (options.chatId) {
        url.searchParams.set('chat', options.chatId);
        url.searchParams.delete('c');
      } else {
        url.searchParams.delete('chat');
        url.searchParams.delete('c');
      }
    }

    const newUrl = url.pathname + (url.search ? url.search : '') + url.hash;
    const currentUrl = window.location.pathname + window.location.search + window.location.hash;

    if (newUrl !== currentUrl) {
      if (options.replace) {
        window.history.replaceState({ page: options.page, chatId: options.chatId }, '', newUrl);
      } else {
        window.history.pushState({ page: options.page, chatId: options.chatId }, '', newUrl);
      }
    }
  } catch (e) {
    console.warn('Failed to sync app URL:', e);
  }
}

interface ChatContextType {
  documents: DocumentInfo[];
  conversations: ConversationResponse[];
  activeConversationId: string | null;
  activeConversationTitle: string;
  messages: MessageItem[];
  currentPage: 'chat' | 'library';
  isBackendConnected: boolean;
  isLoading: boolean;
  isInitialLoading: boolean;
  isUploading: boolean;
  toasts: Toast[];
  selectedDocumentNames: string[];
  isDocSelectorOpen: boolean;
  setIsDocSelectorOpen: (open: boolean) => void;
  draftText: string;
  setDraftText: (text: string) => void;
  composerFocusTrigger: number;
  composerPulseTrigger: number;
  setCurrentPage: (page: 'chat' | 'library', options?: { replace?: boolean; skipUrl?: boolean }) => void;
  selectConversation: (id: string, options?: { skipUrl?: boolean; replace?: boolean }) => Promise<void>;
  startNewDraft: (options?: { skipUrl?: boolean } | React.MouseEvent) => void;
  createConversation: (title?: string) => Promise<string | null>;
  deleteConversation: (id: string) => Promise<void>;
  clearAllConversations: () => Promise<void>;
  defaultScope: 'all' | 'selected';
  setDefaultScope: (scope: 'all' | 'selected') => void;
  topK: number;
  setTopK: (k: number) => void;
  minSimilarity: number;
  setMinSimilarity: (sim: number) => void;
  streamEnabled: boolean;
  setStreamEnabled: (enabled: boolean) => void;
  renameConversation: (id: string, newTitle: string) => void;
  sendMessage: (question: string) => Promise<void>;
  uploadDocuments: (files: File[]) => Promise<boolean>;
  deleteDocument: (fileName: string) => Promise<void>;
  setSelectedDocumentNames: (names: string[]) => void;
  toggleDocumentSelection: (fileName: string) => void;
  selectAllDocuments: () => void;
  clearDocumentSelection: () => void;
  refreshData: () => Promise<void>;
  addToast: (type: 'success' | 'error' | 'info', message: string) => void;
  removeToast: (id: string) => void;
}

const SELECTED_DOCS_KEY = 'rag.selectedDocs.v1';
const CHAT_DOCS_PREFIX = 'rag.chatDocs.';

const loadPersistedSelectedDocs = (): string[] => {
  try {
    const raw = localStorage.getItem(SELECTED_DOCS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((item): item is string => typeof item === 'string');
    }
  } catch (e) {
    console.warn('Failed to parse persisted selected docs:', e);
  }
  return [];
};

const savePersistedSelectedDocs = (docs: string[]) => {
  try {
    localStorage.setItem(SELECTED_DOCS_KEY, JSON.stringify(docs));
  } catch (e) {
    console.warn('Failed to persist selected docs:', e);
  }
};

const loadChatSelectedDocs = (chatId: string): string[] | null => {
  try {
    const raw = localStorage.getItem(`${CHAT_DOCS_PREFIX}${chatId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((item): item is string => typeof item === 'string');
    }
  } catch (e) {
    console.warn(`Failed to parse chat docs for ${chatId}:`, e);
  }
  return null;
};

const saveChatSelectedDocs = (chatId: string, docs: string[]) => {
  try {
    localStorage.setItem(`${CHAT_DOCS_PREFIX}${chatId}`, JSON.stringify(docs));
  } catch (e) {
    console.warn(`Failed to persist chat docs for ${chatId}:`, e);
  }
};

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const initialNav = useRef(parseAppUrl());

  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [conversations, setConversations] = useState<ConversationResponse[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(() => {
    return (
      initialNav.current.chatId ||
      (initialNav.current.page === 'chat' ? localStorage.getItem('rag_qa_last_active_chat') : null)
    );
  });
  const [activeConversationTitle, setActiveConversationTitle] = useState<string>('New chat');
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [currentPage, setCurrentPageState] = useState<'chat' | 'library'>(() => {
    return initialNav.current.page;
  });

  const activeConversationIdRef = useRef<string | null>(activeConversationId);
  const selectingConvIdRef = useRef<string | null>(activeConversationId);

  useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  const setCurrentPage = useCallback(
    (page: 'chat' | 'library', options?: { replace?: boolean; skipUrl?: boolean }) => {
      setCurrentPageState(page);
      if (!options?.skipUrl) {
        syncAppUrl({
          page,
          chatId: page === 'chat' ? activeConversationIdRef.current : null,
          replace: options?.replace,
        });
      }
    },
    []
  );
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [selectedDocumentNames, setSelectedDocumentNamesState] = useState<string[]>(() => {
    return loadPersistedSelectedDocs();
  });
  const [isDocSelectorOpen, setIsDocSelectorOpen] = useState<boolean>(false);
  const [draftText, setDraftText] = useState<string>('');
  const [composerFocusTrigger, setComposerFocusTrigger] = useState<number>(0);
  const [composerPulseTrigger, setComposerPulseTrigger] = useState<number>(0);
  const lastNewChatClickRef = useRef<number>(0);
  const [defaultScope, setDefaultScopeState] = useState<'all' | 'selected'>(() => {
    return (localStorage.getItem('rag_qa_default_scope') as 'all' | 'selected') || 'selected';
  });
  const [streamEnabled, setStreamEnabledState] = useState<boolean>(() => {
    return localStorage.getItem('rag_qa_stream_enabled') !== 'false';
  });

  const [topK, setTopKState] = useState<number>(() => {
    const saved = localStorage.getItem('rag_qa_top_k');
    return saved ? Math.max(1, Math.min(20, parseInt(saved, 10))) : 5;
  });

  const [minSimilarity, setMinSimilarityState] = useState<number>(() => {
    const saved = localStorage.getItem('rag_qa_min_similarity');
    return saved ? Math.max(0.0, Math.min(0.8, parseFloat(saved))) : 0.0;
  });

  const setDefaultScope = useCallback((scope: 'all' | 'selected') => {
    setDefaultScopeState(scope);
    localStorage.setItem('rag_qa_default_scope', scope);
  }, []);

  const setTopK = useCallback((k: number) => {
    const clamped = Math.max(1, Math.min(20, Math.round(k)));
    setTopKState(clamped);
    localStorage.setItem('rag_qa_top_k', String(clamped));
  }, []);

  const setMinSimilarity = useCallback((sim: number) => {
    const clamped = Math.max(0.0, Math.min(0.8, Number(sim.toFixed(2))));
    setMinSimilarityState(clamped);
    localStorage.setItem('rag_qa_min_similarity', String(clamped));
  }, []);

  const setStreamEnabled = useCallback((enabled: boolean) => {
    setStreamEnabledState(enabled);
    localStorage.setItem('rag_qa_stream_enabled', String(enabled));
  }, []);

  const isSendingRef = useRef(false);

  // Cross-tab synchronization via storage event
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === SELECTED_DOCS_KEY) {
        try {
          const next = e.newValue ? JSON.parse(e.newValue) : [];
          if (Array.isArray(next)) {
            setSelectedDocumentNamesState(next.filter((x): x is string => typeof x === 'string'));
          }
        } catch {}
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const setSelectedDocumentNames = useCallback((action: string[] | ((prev: string[]) => string[])) => {
    setSelectedDocumentNamesState((prev) => {
      const next = typeof action === 'function' ? action(prev) : action;
      savePersistedSelectedDocs(next);
      const currentActiveId = activeConversationIdRef.current;
      if (currentActiveId) {
        saveChatSelectedDocs(currentActiveId, next);
      }
      return next;
    });
  }, []);

  const toggleDocumentSelection = useCallback((fileName: string) => {
    setSelectedDocumentNames((prev) => {
      if (prev.length === 0) {
        return [fileName];
      }
      return prev.includes(fileName)
        ? prev.filter((f) => f !== fileName)
        : [...prev, fileName];
    });
  }, [setSelectedDocumentNames]);

  const selectAllDocuments = useCallback(() => {
    setSelectedDocumentNames(documents.map((d) => d.file_name));
  }, [documents, setSelectedDocumentNames]);

  const clearDocumentSelection = useCallback(() => {
    setSelectedDocumentNames([]);
  }, [setSelectedDocumentNames]);

  const addToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const refreshData = useCallback(async () => {
    try {
      await api.checkHealth();
      setIsBackendConnected(true);

      const [docsRes, convsRes] = await Promise.all([
        api.listDocuments().catch(() => ({ documents: [], orphan_files: [] })),
        api.listConversations(50, 0).catch(() => ({ total: 0, conversations: [] })),
      ]);

      const docs = docsRes.documents || [];
      setDocuments(docs);

      // Validate stored IDs: remove any ID that no longer exists or is not "Ready"
      // If something was removed, silently update storage (no error toast)
      const readyDocNames = new Set(
        docs.filter((d: DocumentInfo) => d.indexed !== false).map((d: DocumentInfo) => d.file_name)
      );
      setSelectedDocumentNamesState((prev) => {
        const valid = prev.filter((name) => readyDocNames.has(name));
        if (valid.length !== prev.length) {
          savePersistedSelectedDocs(valid);
          const currentActiveId = activeConversationIdRef.current;
          if (currentActiveId) {
            saveChatSelectedDocs(currentActiveId, valid);
          }
          return valid;
        }
        return prev;
      });

      // Display conversations with messages, or the active conversation if it was just created
      const allConvs = convsRes.conversations || [];
      const currentActiveId = activeConversationIdRef.current;
      const visibleConvs = allConvs.filter(
        (c) => (c.message_count || 0) > 0 || c.conversation_id === currentActiveId
      );

      setConversations(visibleConvs);
    } catch {
      setIsBackendConnected(false);
    } finally {
      setIsInitialLoading(false);
    }
  }, []);

  // Start a new in-memory draft (NO backend call, NO empty sidebar row)
  const startNewDraft = useCallback(
    (options?: { skipUrl?: boolean } | React.MouseEvent) => {
      const skipUrl = options && 'skipUrl' in options ? Boolean(options.skipUrl) : false;
      const now = Date.now();
      // Guard/debounce rapid clicks within 300ms
      if (now - lastNewChatClickRef.current < 300) {
        return;
      }
      lastNewChatClickRef.current = now;

      // If already in an empty draft: do nothing visible except focus composer and pulse ring
      if (activeConversationIdRef.current === null && messages.length === 0) {
        setCurrentPageState('chat');
        if (!skipUrl) {
          syncAppUrl({ page: 'chat', chatId: null });
        }
        setComposerPulseTrigger((prev) => prev + 1);
        setComposerFocusTrigger((prev) => prev + 1);
        return;
      }

      selectingConvIdRef.current = null;
      activeConversationIdRef.current = null;

      // New chat: starts with last used selection (the persisted global selection)
      const globalDocs = loadPersistedSelectedDocs();
      setSelectedDocumentNamesState(globalDocs);

      setActiveConversationId(null);
      setActiveConversationTitle('New chat');
      setMessages([]);
      setCurrentPageState('chat');
      try {
        localStorage.removeItem('rag_qa_last_active_chat');
      } catch {}

      if (!skipUrl) {
        syncAppUrl({ page: 'chat', chatId: null });
      }
      setComposerFocusTrigger((prev) => prev + 1);
    },
    [messages.length]
  );

  // Load conversation details when selecting an existing conversation
  const selectConversation = useCallback(
    async (id: string, options?: { skipUrl?: boolean; replace?: boolean }) => {
      if (!id) return;
      selectingConvIdRef.current = id;
      setIsLoading(true);
      setActiveConversationId(id);
      activeConversationIdRef.current = id;
      setCurrentPageState('chat');

      try {
        localStorage.setItem('rag_qa_last_active_chat', id);
      } catch {}

      if (!options?.skipUrl) {
        syncAppUrl({ page: 'chat', chatId: id, replace: options?.replace });
      }

      // Per-chat behavior: restore documents that were used in that chat
      const chatDocs = loadChatSelectedDocs(id);
      if (chatDocs !== null) {
        setSelectedDocumentNamesState(chatDocs);
        savePersistedSelectedDocs(chatDocs);
      } else {
        const globalDocs = loadPersistedSelectedDocs();
        setSelectedDocumentNamesState(globalDocs);
        saveChatSelectedDocs(id, globalDocs);
      }

      try {
        const detail = await api.getConversation(id);
        if (selectingConvIdRef.current === id) {
          setActiveConversationTitle(detail.title || 'Conversation');
          setMessages(detail.messages || []);
        }
      } catch (err) {
        if (selectingConvIdRef.current === id) {
          addToast('error', `Failed to load conversation: ${extractErrorMessage(err)}`);
          startNewDraft({ skipUrl: false });
        }
      } finally {
        if (selectingConvIdRef.current === id) {
          setIsLoading(false);
        }
      }
    },
    [addToast, startNewDraft]
  );

  // Initial load & heartbeat check with URL recovery
  useEffect(() => {
    let isMounted = true;

    const init = async () => {
      await refreshData();
      if (!isMounted) return;

      const { page, chatId } = parseAppUrl();
      const storedLastChat = localStorage.getItem('rag_qa_last_active_chat');
      const targetChatId = chatId || (page === 'chat' ? storedLastChat : null);

      if (page === 'library') {
        setCurrentPageState('library');
        syncAppUrl({ page: 'library', replace: true });
      } else if (targetChatId) {
        await selectConversation(targetChatId, { replace: true });
      } else {
        syncAppUrl({ page: 'chat', chatId: null, replace: true });
      }
    };

    init();

    const interval = setInterval(() => {
      api.checkHealth()
        .then(() => setIsBackendConnected(true))
        .catch(() => setIsBackendConnected(false));
    }, 15000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Handle browser back and forward navigation
  useEffect(() => {
    const handlePopState = () => {
      const { page, chatId } = parseAppUrl();
      if (page === 'library') {
        setCurrentPageState('library');
      } else {
        setCurrentPageState('chat');
        if (chatId) {
          selectConversation(chatId, { skipUrl: true });
        } else {
          startNewDraft({ skipUrl: true });
        }
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [selectConversation, startNewDraft]);

  // Explicit creation (used internally by sendMessage upon first question)
  const createConversation = useCallback(
    async (title = 'New chat'): Promise<string | null> => {
      try {
        const newConv = await api.createConversation(title);
        setConversations((prev) => [newConv, ...prev.filter((c) => c.conversation_id !== newConv.conversation_id)]);
        setActiveConversationId(newConv.conversation_id);
        setActiveConversationTitle(newConv.title);
        saveChatSelectedDocs(newConv.conversation_id, selectedDocumentNames);
        try {
          localStorage.setItem('rag_qa_last_active_chat', newConv.conversation_id);
        } catch {}
        syncAppUrl({ page: 'chat', chatId: newConv.conversation_id });
        return newConv.conversation_id;
      } catch (err) {
        addToast('error', `Failed to create chat: ${extractErrorMessage(err)}`);
        return null;
      }
    },
    [addToast, selectedDocumentNames]
  );

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await api.deleteConversation(id);
      try {
        localStorage.removeItem(`${CHAT_DOCS_PREFIX}${id}`);
      } catch {}
      setConversations((prev) => prev.filter((c) => c.conversation_id !== id));
      if (activeConversationId === id) {
        startNewDraft();
      }
      addToast('success', 'Conversation deleted');
    } catch (err) {
      addToast('error', `Failed to delete conversation: ${extractErrorMessage(err)}`);
    }
  }, [activeConversationId, startNewDraft, addToast]);

  const clearAllConversations = useCallback(async () => {
    try {
      for (const conv of conversations) {
        await api.deleteConversation(conv.conversation_id);
      }
      setConversations([]);
      startNewDraft();
      addToast('success', 'All conversations cleared');
    } catch (err) {
      addToast('error', `Failed to clear conversations: ${extractErrorMessage(err)}`);
    }
  }, [conversations, startNewDraft, addToast]);

  const renameConversation = useCallback((id: string, newTitle: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.conversation_id === id ? { ...c, title: newTitle } : c))
    );
    if (activeConversationId === id) {
      setActiveConversationTitle(newTitle);
    }
  }, [activeConversationId]);

  const sendMessage = useCallback(async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed) return;
    if (isSendingRef.current || isLoading) return;
    isSendingRef.current = true;

    // 1. If user has no documents uploaded yet, provide friendly inline response
    if (documents.length === 0) {
      addToast('info', 'Please upload a reference document first to continue.');
      const userMsg: MessageItem = {
        id: `client-${Date.now()}`,
        conversation_id: 'draft',
        role: 'user',
        content: trimmed,
        created_at: new Date().toISOString(),
        sources: [],
      };
      const promptUploadMsg: MessageItem = {
        id: `assistant-${Date.now()}`,
        conversation_id: 'draft',
        role: 'assistant',
        content: "Please upload your reference PDF documents in the Documents tab first so I can ground answers in your verified files.",
        created_at: new Date().toISOString(),
        sources: [],
      };
      setMessages((prev) => [...prev, userMsg, promptUploadMsg]);
      isSendingRef.current = false;
      return;
    }

    // 2. If user has not chosen any document for this session
    if (defaultScope === 'selected' && selectedDocumentNames.length === 0) {
      addToast('info', 'Please select at least one document first to continue.');
      const userMsg: MessageItem = {
        id: `client-${Date.now()}`,
        conversation_id: 'draft',
        role: 'user',
        content: trimmed,
        created_at: new Date().toISOString(),
        sources: [],
      };
      const promptSelectMsg: MessageItem = {
        id: `assistant-${Date.now()}`,
        conversation_id: 'draft',
        role: 'assistant',
        content: "Please select at least one reference document for this conversation first so I can retrieve relevant facts and ground the answer in your chosen files.",
        created_at: new Date().toISOString(),
        sources: [],
      };
      setMessages((prev) => [...prev, userMsg, promptSelectMsg]);
      isSendingRef.current = false;
      return;
    }

    setIsLoading(true);

    let targetConvId = activeConversationIdRef.current;
    const optimisticUserMsg: MessageItem = {
      id: `client-${Date.now()}`,
      conversation_id: targetConvId || 'pending',
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
      sources: [],
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);

    try {
      // 2. If activeConversationId is null, create conversation on first message
      if (!targetConvId) {
        // Auto-title from the first question (max ~40 characters, trimmed)
        let autoTitle = trimmed.replace(/[\r\n]+/g, ' ').trim();
        if (autoTitle.length > 40) {
          autoTitle = autoTitle.slice(0, 40).trim() + '…';
        }
        if (!autoTitle) autoTitle = 'New chat';

        const newConv = await api.createConversation(autoTitle);
        targetConvId = newConv.conversation_id;
        selectingConvIdRef.current = targetConvId;
        activeConversationIdRef.current = targetConvId;
        setActiveConversationId(targetConvId);
        setActiveConversationTitle(newConv.title);
        saveChatSelectedDocs(targetConvId, selectedDocumentNames);
        try {
          localStorage.setItem('rag_qa_last_active_chat', targetConvId);
        } catch {}
        syncAppUrl({ page: 'chat', chatId: targetConvId });
        // Add to sidebar conversation list at the very top
        setConversations((prev) => [newConv, ...prev.filter((c) => c.conversation_id !== targetConvId)]);
      }

      // Call backend
      let resp;
      try {
        resp = await api.sendMessage(
          targetConvId,
          trimmed,
          topK,
          minSimilarity,
          selectedDocumentNames.length > 0 ? selectedDocumentNames : null
        );
      } catch (sendErr) {
        const errMsg = extractErrorMessage(sendErr);
        // If the conversation was not found on the backend (e.g. stale ID),
        // recover seamlessly by creating a fresh conversation session and retrying.
        if (errMsg.includes('not found') || errMsg.includes('404')) {
          let autoTitle = trimmed.replace(/[\r\n]+/g, ' ').trim();
          if (autoTitle.length > 40) {
            autoTitle = autoTitle.slice(0, 40).trim() + '…';
          }
          if (!autoTitle) autoTitle = 'New chat';

          const recoveredConv = await api.createConversation(autoTitle);
          targetConvId = recoveredConv.conversation_id;
          selectingConvIdRef.current = targetConvId;
          activeConversationIdRef.current = targetConvId;
          setActiveConversationId(targetConvId);
          setActiveConversationTitle(recoveredConv.title);
          saveChatSelectedDocs(targetConvId, selectedDocumentNames);
          try {
            localStorage.setItem('rag_qa_last_active_chat', targetConvId);
          } catch {}
          syncAppUrl({ page: 'chat', chatId: targetConvId });
          setConversations((prev) => [recoveredConv, ...prev.filter((c) => c.conversation_id !== targetConvId)]);

          resp = await api.sendMessage(
            targetConvId,
            trimmed,
            topK,
            minSimilarity,
            selectedDocumentNames.length > 0 ? selectedDocumentNames : null
          );
        } else {
          throw sendErr;
        }
      }

      const assistantMsg: MessageItem = {
        id: `assistant-${Date.now()}`,
        conversation_id: targetConvId,
        role: 'assistant',
        content: resp.answer,
        standalone_query: resp.standalone_query,
        found: resp.found,
        sources: resp.sources || [],
        created_at: resp.created_at || new Date().toISOString(),
      };
      setMessages((prev) => {
        const hasUser = prev.some((m) => m.id === optimisticUserMsg.id || (m.role === 'user' && m.content === trimmed));
        if (hasUser) {
          return [...prev, assistantMsg];
        }
        return [...prev, optimisticUserMsg, assistantMsg];
      });

      // Update conversations list message count
      setConversations((prev) =>
        prev.map((c) =>
          c.conversation_id === targetConvId
            ? { ...c, message_count: (c.message_count || 0) + 2, updated_at: new Date().toISOString() }
            : c
        )
      );
    } catch (err) {
      const errMsg = extractErrorMessage(err);
      addToast('error', `Message failed: ${errMsg}`);
      const errAssistantMsg: MessageItem = {
        id: `assistant-error-${Date.now()}`,
        conversation_id: targetConvId || 'error',
        role: 'assistant',
        content: `Error: ${errMsg}. Please try sending your message again.`,
        created_at: new Date().toISOString(),
        sources: [],
      };
      setMessages((prev) => {
        const hasUser = prev.some((m) => m.id === optimisticUserMsg.id || (m.role === 'user' && m.content === trimmed));
        if (hasUser) {
          return [...prev, errAssistantMsg];
        }
        return [...prev, optimisticUserMsg, errAssistantMsg];
      });
    } finally {
      setIsLoading(false);
      isSendingRef.current = false;
    }
  }, [defaultScope, documents.length, isLoading, minSimilarity, selectedDocumentNames, topK, addToast]);

  const uploadDocuments = useCallback(async (files: File[]): Promise<boolean> => {
    if (!files.length) return false;
    setIsUploading(true);
    try {
      const res = await api.uploadDocuments(files);
      const successCount = res.results.filter((r) => r.success).length;
      if (successCount > 0) {
        addToast('success', `Indexed ${successCount} document(s) successfully.`);
        await refreshData();
        return true;
      } else {
        const firstErr = res.results.find((r) => r.error)?.error || 'Upload rejected';
        addToast('error', `Upload failed: ${firstErr}`);
        return false;
      }
    } catch (err) {
      addToast('error', `Upload error: ${extractErrorMessage(err)}`);
      return false;
    } finally {
      setIsUploading(false);
    }
  }, [addToast, refreshData]);

  const deleteDocument = useCallback(async (fileName: string) => {
    try {
      await api.deleteDocument(fileName);
      setDocuments((prev) => prev.filter((d) => d.file_name !== fileName));
      setSelectedDocumentNames((prev) => prev.filter((f) => f !== fileName));
      addToast('success', `Deleted document ${fileName}`);
    } catch (err) {
      addToast('error', `Failed to delete document: ${extractErrorMessage(err)}`);
    }
  }, [addToast]);

  return (
    <ChatContext.Provider
      value={{
        documents,
        conversations,
        activeConversationId,
        activeConversationTitle,
        messages,
        currentPage,
        isBackendConnected,
        isLoading,
        isInitialLoading,
        isUploading,
        toasts,
        selectedDocumentNames,
        isDocSelectorOpen,
        setIsDocSelectorOpen,
        draftText,
        setDraftText,
        composerFocusTrigger,
        composerPulseTrigger,
        setCurrentPage,
        selectConversation,
        startNewDraft,
        createConversation,
        deleteConversation,
        clearAllConversations,
        defaultScope,
        setDefaultScope,
        topK,
        setTopK,
        minSimilarity,
        setMinSimilarity,
        streamEnabled,
        setStreamEnabled,
        renameConversation,
        sendMessage,
        uploadDocuments,
        deleteDocument,
        setSelectedDocumentNames,
        toggleDocumentSelection,
        selectAllDocuments,
        clearDocumentSelection,
        refreshData,
        addToast,
        removeToast,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
