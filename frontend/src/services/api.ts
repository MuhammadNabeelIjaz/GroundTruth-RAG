import axios, { AxiosError } from 'axios';
import type {
  HealthResponse,
  DocumentList,
  UploadResponse,
  DeleteResponse,
  ConversationListResponse,
  ConversationResponse,
  ConversationDetailResponse,
  ConversationMessageResponse,
} from '../types';

export function getDefaultApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
}

export function getApiBaseUrl(): string {
  try {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('rag_api_base_url');
      if (stored && stored.trim()) {
        return stored.trim().replace(/\/$/, '');
      }
    }
  } catch {
    // localStorage might be unavailable in some iframe/restricted modes
  }
  return getDefaultApiBaseUrl();
}

export const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 60000,
});

apiClient.interceptors.request.use((config) => {
  const currentBase = getApiBaseUrl();
  if (currentBase) {
    config.baseURL = currentBase;
  }
  return config;
});

export function setApiBaseUrl(url: string | null): string {
  const normalized = url && url.trim() ? url.trim().replace(/\/$/, '') : '';
  try {
    if (typeof window !== 'undefined') {
      if (normalized) {
        localStorage.setItem('rag_api_base_url', normalized);
      } else {
        localStorage.removeItem('rag_api_base_url');
      }
    }
  } catch {
    // ignore storage exceptions
  }
  const effectiveUrl = normalized || getDefaultApiBaseUrl();
  apiClient.defaults.baseURL = effectiveUrl;
  return effectiveUrl;
}

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosErr = error as AxiosError<any>;
    if (axiosErr.response?.data) {
      const data = axiosErr.response.data;
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
      }
      if (Array.isArray(data.results)) {
        const failed = data.results.filter((r: any) => !r.success && r.error);
        if (failed.length > 0) {
          return failed.map((f: any) => `${f.original_name}: ${f.error}`).join('; ');
        }
      }
      if (data.error) return String(data.error);
    }
    if (axiosErr.message === 'Network Error') {
      return 'Backend unreachable. Please verify FastAPI backend is running.';
    }
    return axiosErr.message;
  }
  return error instanceof Error ? error.message : 'Unknown error occurred';
}

export const api = {
  checkHealth: async (): Promise<HealthResponse> => {
    const res = await apiClient.get<HealthResponse>('/health', { timeout: 4000 });
    return res.data;
  },

  listDocuments: async (): Promise<DocumentList> => {
    const res = await apiClient.get<DocumentList>('/documents');
    return res.data;
  },

  uploadDocuments: async (files: File[]): Promise<UploadResponse> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    const res = await apiClient.post<UploadResponse>('/documents', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 120000,
    });
    return res.data;
  },

  deleteDocument: async (fileName: string): Promise<DeleteResponse> => {
    const quoted = encodeURIComponent(fileName);
    const res = await apiClient.delete<DeleteResponse>(`/documents/${quoted}`);
    return res.data;
  },

  listConversations: async (limit = 50, offset = 0): Promise<ConversationListResponse> => {
    const res = await apiClient.get<ConversationListResponse>('/conversations', {
      params: { limit, offset },
    });
    return res.data;
  },

  createConversation: async (title?: string): Promise<ConversationResponse> => {
    const res = await apiClient.post<ConversationResponse>('/conversations', { title });
    return res.data;
  },

  getConversation: async (conversationId: string): Promise<ConversationDetailResponse> => {
    const res = await apiClient.get<ConversationDetailResponse>(`/conversations/${conversationId}`);
    return res.data;
  },

  deleteConversation: async (conversationId: string): Promise<{ deleted: boolean; conversation_id: string }> => {
    const res = await apiClient.delete(`/conversations/${conversationId}`);
    return res.data;
  },

  sendMessage: async (
    conversationId: string,
    question: string,
    topK = 5,
    minSimilarity = 0.0,
    fileNames?: string[] | null
  ): Promise<ConversationMessageResponse> => {
    const res = await apiClient.post<ConversationMessageResponse>(
      `/conversations/${conversationId}/messages`,
      {
        question,
        top_k: topK,
        min_similarity: minSimilarity,
        file_names: fileNames && fileNames.length > 0 ? fileNames : null,
      }
    );
    return res.data;
  },

  getDocumentSuggestions: async (fileName: string): Promise<string[]> => {
    try {
      const quoted = encodeURIComponent(fileName);
      const res = await apiClient.get<{ file_name: string; suggestions: string[] }>(
        `/documents/${quoted}/suggestions`,
        { timeout: 6000 }
      );
      return res.data?.suggestions || [];
    } catch {
      return [];
    }
  },
};
