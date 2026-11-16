"""Request and response shapes shared between the API and its clients."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class PagePreview(BaseModel):
    """What was extracted from one page (the text itself is not returned)."""

    page_number: int  # physical page, 1-based
    char_count: int  # 0 for a blank page
    preview: str  # first characters of the page, whitespace collapsed


class OverLimitChunk(BaseModel):
    """A chunk longer than the embedding model accepts (it was NOT embedded)."""

    chunk_id: str
    token_count: int


class FileResult(BaseModel):
    """Outcome for one uploaded file. Files in a request succeed or fail independently."""

    original_name: str  # the name as received by the server (before sanitizing)
    file_name: str | None  # name stored on disk and used in citations; None if unusable
    success: bool
    status_code: int  # the HTTP status this file alone would have produced
    error: str | None = None
    page_count: int | None = None
    blank_pages: list[int] | None = None
    pages: list[PagePreview] | None = None
    # Stage 3: indexing outcome (None when the file was rejected before chunking).
    chunk_count: int | None = None
    max_chunk_tokens: int | None = None
    over_limit_chunks: list[OverLimitChunk] | None = None


class UploadResponse(BaseModel):
    results: list[FileResult]


class DocumentInfo(BaseModel):
    file_name: str
    size_bytes: int
    indexed: bool  # False: the PDF is on disk but has no chunks (run rebuild_index)
    chunk_count: int


class DocumentList(BaseModel):
    documents: list[DocumentInfo]
    orphan_files: list[str]  # indexed file names that no longer exist on disk


class DeleteResponse(BaseModel):
    file_name: str
    chunks_removed: int


class SearchResultItem(BaseModel):
    chunk_id: str
    file_name: str
    page_number: int  # physical page, 1-based
    chunk_index: int
    text: str
    similarity: float
    excerpt: str


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = None
    min_similarity: float | None = None


class SearchResponse(BaseModel):
    query: str
    total_found: int
    results: list[SearchResultItem]


# Generation (Stage 5)


class SourceCitation(BaseModel):
    chunk_id: str
    file_name: str
    page_number: int  # physical page, 1-based
    chunk_index: int
    similarity: float
    excerpt: str
    passage_number: int | None = None


class AnswerRequest(BaseModel):
    question: str
    top_k: int | None = None
    min_similarity: float | None = None
    conversation_id: str | None = None
    file_names: list[str] | None = None


class AnswerResponse(BaseModel):
    question: str
    answer: str
    found: bool
    sources: list[SourceCitation]
    conversation_id: str | None = None
    standalone_query: str | None = None


# Conversations & Multi-Turn History (Stage 7)


class MessageItem(BaseModel):
    id: str
    conversation_id: str
    role: str  # "user" | "assistant"
    content: str
    standalone_query: str | None = None
    found: bool | None = None
    sources: list[SourceCitation] = []
    created_at: str


class ConversationCreateRequest(BaseModel):
    title: str | None = None


class ConversationResponse(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


class ConversationDetailResponse(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    messages: list[MessageItem]


class ConversationListResponse(BaseModel):
    total: int
    conversations: list[ConversationResponse]


class ConversationMessageRequest(BaseModel):
    question: str
    top_k: int | None = None
    min_similarity: float | None = None
    file_names: list[str] | None = None


class ConversationMessageResponse(BaseModel):
    conversation_id: str
    question: str
    standalone_query: str
    answer: str
    found: bool
    sources: list[SourceCitation]
    created_at: str

