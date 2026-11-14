export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface DocumentInfo {
  file_name: string;
  size_bytes: number;
  indexed: boolean;
  chunk_count: number;
}

export interface DocumentList {
  documents: DocumentInfo[];
  orphan_files: string[];
}

export interface PagePreview {
  page_number: number;
  char_count: number;
  preview: string;
}

export interface OverLimitChunk {
  chunk_id: string;
  token_count: number;
}

export interface FileResult {
  original_name: string;
  file_name: string | null;
  success: boolean;
  status_code: number;
  error?: string | null;
  page_count?: number | null;
  chunk_count?: number | null;
  pages?: PagePreview[] | null;
}

export interface UploadResponse {
  results: FileResult[];
}

export interface DeleteResponse {
  file_name: string;
  chunks_removed: number;
}

export interface SourceCitation {
  chunk_id: string;
  file_name: string;
  page_number: number;
  chunk_index: number;
  similarity: number;
  excerpt: string;
}

export interface MessageItem {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  standalone_query?: string | null;
  found?: boolean | null;
  sources: SourceCitation[];
  created_at: string;
}

export interface ConversationResponse {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationListResponse {
  total: number;
  conversations: ConversationResponse[];
}

export interface ConversationDetailResponse {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  messages: MessageItem[];
}

export interface ConversationMessageRequest {
  question: string;
  top_k?: number | null;
  min_similarity?: number | null;
  file_names?: string[] | null;
}

export interface ConversationMessageResponse {
  conversation_id: string;
  question: string;
  standalone_query: string;
  answer: string;
  found: boolean;
  sources: SourceCitation[];
  created_at: string;
}

export interface AnswerRequest {
  question: string;
  top_k?: number | null;
  min_similarity?: number | null;
  conversation_id?: string | null;
  file_names?: string[] | null;
}

export interface AnswerResponse {
  question: string;
  answer: string;
  found: boolean;
  sources: SourceCitation[];
  conversation_id?: string | null;
  standalone_query?: string | null;
}

