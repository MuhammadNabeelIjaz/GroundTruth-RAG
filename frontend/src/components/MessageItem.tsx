import React, { useState, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check, RotateCw } from 'lucide-react';
import type { MessageItem as MessageItemType } from '../types';
import { CitationsDrawer } from './CitationsDrawer';
import { InsufficientEvidenceWarning } from './InsufficientEvidenceWarning';
import { useChat } from '../context/ChatContext';

interface MessageProps {
  message: MessageItemType;
  isLatest?: boolean;
}

/**
 * Normalizes answer text:
 * 1. Ensures numbered lists like "1.Question" have a space: "1. Question"
 * 2. Normalizes streaming partial asterisks so unfinished markers don't flash raw symbols
 * 3. Converts citation markers [Passage N] outside code blocks into markdown citation links
 */
function normalizeMarkdownText(raw: string, isStreaming = false): string {
  if (!raw) return '';
  let text = raw;

  // 1. Ensure numbered lists have space: "1.Question" -> "1. Question"
  text = text.replace(/(^|\n)(\s*\d+)\.([^\s\d])/g, '$1$2. $3');

  // 2. Hide unclosed trailing asterisks during streaming
  if (isStreaming) {
    if (text.endsWith('**')) {
      text = text.slice(0, -2);
    } else if (text.endsWith('*')) {
      text = text.slice(0, -1);
    }
  }

  // 3. Strip stray unpaired double asterisks if count is odd
  const doubleAsteriskCount = (text.match(/\*\*/g) || []).length;
  if (doubleAsteriskCount % 2 !== 0) {
    const lastIdx = text.lastIndexOf('**');
    if (lastIdx !== -1) {
      text = text.slice(0, lastIdx) + text.slice(lastIdx + 2);
    }
  }

  // 4. Convert citations [Passage N] or [N] or [1, 2] outside code blocks to citation links
  const codeBlocks: string[] = [];
  const withPlaceholders = text.replace(/(```[\s\S]*?```|`[^`\n]+`)/g, (match) => {
    const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
    codeBlocks.push(match);
    return placeholder;
  });

  const withCitations = withPlaceholders
    .replace(
      /\[((?:(?:Passage\s+|passage\s+)?\d+\s*,\s*)+(?:Passage\s+|passage\s+)?\d+)\]/gi,
      (_m, inner) => {
        return inner
          .split(',')
          .map((p: string) => {
            const num = p.replace(/\D/g, '');
            return num ? `[${num}](citation:${num})` : '';
          })
          .filter(Boolean)
          .join(' ');
      }
    )
    .replace(
      /\[(?:Passage\s+|passage\s+)?(\d+)\]/gi,
      (_m, num) => `[${num}](citation:${num})`
    );

  text = withCitations.replace(/__CODE_BLOCK_(\d+)__/g, (_m, idx) => {
    return codeBlocks[parseInt(idx, 10)] || '';
  });

  return text;
}

export const MessageItem: React.FC<MessageProps> = ({ message, isLatest }) => {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [highlightedSourceIdx, setHighlightedSourceIdx] = useState<number | null>(null);
  const [isSourcesExpanded, setIsSourcesExpanded] = useState<boolean>(false);
  const { sendMessage, isLoading } = useChat();

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerate = () => {
    if (message.standalone_query) {
      sendMessage(message.standalone_query);
    }
  };

  const handleCitationClick = useCallback((passageNum: number) => {
    const index = passageNum - 1; // 1-based index to 0-based
    if (message.sources && message.sources[index]) {
      setIsSourcesExpanded(true);
      setHighlightedSourceIdx(index);
      setTimeout(() => {
        setHighlightedSourceIdx(null);
      }, 1500);
    }
  }, [message.sources]);

  // Clean & normalize content
  const processedContent = useMemo(() => {
    if (isUser) return message.content;
    const isStreamingThis = Boolean(isLatest && isLoading);
    return normalizeMarkdownText(message.content, isStreamingThis);
  }, [message.content, isUser, isLatest, isLoading]);

  // Custom markdown components
  const markdownComponents = useMemo(() => {
    return {
      p: ({ children }: any) => (
        <p className="mb-3.5 last:mb-0 leading-[1.68] font-sans text-[15px] sm:text-[15.5px] dark:text-[#E5E7EB] text-[#374151]">
          {children}
        </p>
      ),
      strong: ({ children }: any) => (
        <strong className="font-semibold dark:text-white text-[#1F2937]">
          {children}
        </strong>
      ),
      em: ({ children }: any) => (
        <em className="italic dark:text-[#E5E7EB] text-[#374151]">
          {children}
        </em>
      ),
      h1: ({ children }: any) => (
        <h1 className="text-lg font-medium dark:text-[#F3F4F6] text-[#1F2937] mt-4 mb-2 tracking-tight">
          {children}
        </h1>
      ),
      h2: ({ children }: any) => (
        <h2 className="text-base font-medium dark:text-[#F3F4F6] text-[#1F2937] mt-3.5 mb-1.5 tracking-tight">
          {children}
        </h2>
      ),
      h3: ({ children }: any) => (
        <h3 className="text-sm font-medium dark:text-[#F3F4F6] text-[#1F2937] mt-3 mb-1">
          {children}
        </h3>
      ),
      ol: ({ children }: any) => (
        <ol className="list-decimal list-outside pl-5 mb-3.5 space-y-1.5 font-sans text-[15px] sm:text-[15.5px] dark:text-[#E5E7EB] text-[#374151]">
          {children}
        </ol>
      ),
      ul: ({ children }: any) => (
        <ul className="list-disc list-outside pl-5 mb-3.5 space-y-1.5 font-sans text-[15px] sm:text-[15.5px] dark:text-[#E5E7EB] text-[#374151]">
          {children}
        </ul>
      ),
      li: ({ children }: any) => (
        <li className="pl-1 leading-relaxed">
          {children}
        </li>
      ),
      blockquote: ({ children }: any) => (
        <blockquote className="border-l-2 border-[#10B981]/50 pl-3.5 my-2.5 dark:text-[#9CA3AF] text-[#4B5563] italic">
          {children}
        </blockquote>
      ),
      a: ({ href, children }: any) => {
        // Citation link handler: citation:N
        if (href?.startsWith('citation:')) {
          const passageNum = parseInt(href.replace('citation:', ''), 10);
          const sourceIdx = passageNum - 1;
          const matchingSource = message.sources && message.sources[sourceIdx];

          if (matchingSource) {
            return (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleCitationClick(passageNum);
                }}
                className="inline-flex items-center justify-center px-1.5 py-0.5 mx-0.5 rounded-md dark:bg-emerald-950/40 bg-emerald-50 border border-emerald-300 dark:border-emerald-700/60 text-[11px] font-mono font-semibold text-[#059669] dark:text-[#10B981] hover:bg-[#10B981] hover:text-white dark:hover:bg-[#10B981] dark:hover:text-white transition-all cursor-pointer align-baseline select-none shadow-2xs"
                title={`${matchingSource.file_name} · Page ${matchingSource.page_number}`}
                aria-label={`Citation: Passage ${passageNum}, ${matchingSource.file_name}, page ${matchingSource.page_number}`}
              >
                [{passageNum}]
              </button>
            );
          }
          return <span className="dark:text-[#9CA3AF] text-[#6B7280] font-mono text-xs">[{passageNum}]</span>;
        }

        // Standard link
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#10B981] hover:underline font-medium cursor-pointer"
          >
            {children}
          </a>
        );
      },
      code: ({ inline, className, children, ...props }: any) => {
        if (inline) {
          return (
            <code
              className="px-1.5 py-0.5 rounded-md dark:bg-[#25272C] bg-[#F0EFEA] border dark:border-[#33363D] border-[#E5E4DE] font-mono text-[13px] dark:text-[#E5E7EB] text-[#2C2D30] break-words"
              {...props}
            >
              {children}
            </code>
          );
        }
        return (
          <pre className="my-3 p-3 rounded-xl dark:bg-[#191A1D] bg-[#F7F6F2] border dark:border-[#2D3036] border-[#E5E4DE] overflow-x-auto text-xs font-mono dark:text-[#F3F4F6] text-[#2C2D30]">
            <code className={className} {...props}>
              {children}
            </code>
          </pre>
        );
      },
      table: ({ children }: any) => (
        <div className="overflow-x-auto my-3 max-w-full rounded-xl border dark:border-[#2D3036] border-[#E5E4DE]">
          <table className="w-full text-left border-collapse text-xs">
            {children}
          </table>
        </div>
      ),
      th: ({ children }: any) => (
        <th className="border-b dark:border-[#2D3036] border-[#E5E4DE] dark:bg-[#25272C] bg-[#F0EFEA] px-3 py-2 font-medium dark:text-[#F3F4F6] text-[#2C2D30] text-xs uppercase tracking-wider">
          {children}
        </th>
      ),
      td: ({ children }: any) => (
        <td className="border-b dark:border-[#2D3036]/60 border-[#E5E4DE] px-3 py-2 dark:text-[#9CA3AF] text-[#4B5563] text-xs">
          {children}
        </td>
      ),
      hr: () => <hr className="my-4 border-t dark:border-[#2D3036] border-[#E5E4DE]" />,
    };
  }, [message.sources, handleCitationClick]);

  if (isUser) {
    return (
      <div className="flex justify-end my-3 animate-fade-in">
        <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl dark:bg-[#1E2024] bg-[#F0EFEA] border border-[#E5E4DE] dark:border-[#2D3036] dark:text-[#F3F4F6] text-[#2C2D30] px-4 sm:px-5 py-3 text-[14.5px] sm:text-[15px] font-sans leading-relaxed select-text shadow-xs">
          {message.content}
        </div>
      </div>
    );
  }

  const isRefusal =
    message.found === false ||
    message.content.toLowerCase().includes('not contain sufficient evidence') ||
    message.content.toLowerCase().includes('does not provide enough information');

  return (
    <div className="my-4 sm:my-5 animate-fade-in group max-w-[720px] w-full">
      {/* Assistant Response Body: Clean Open Markdown Text Layout (No Bulky Bubble, No Serif) */}
      <div className="text-[15px] sm:text-[15.5px] font-sans dark:text-[#F3F4F6] text-[#2C2D30] leading-[1.68] select-text break-words">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {processedContent}
        </ReactMarkdown>
      </div>

      {/* Friendly not-found notice */}
      {isRefusal && <InsufficientEvidenceWarning />}

      {/* Sources Citations Drawer */}
      {message.sources && message.sources.length > 0 && (
        <CitationsDrawer
          sources={message.sources}
          isExpanded={isSourcesExpanded}
          onToggleExpand={() => setIsSourcesExpanded(!isSourcesExpanded)}
          highlightedIndex={highlightedSourceIdx}
        />
      )}

      {/* Actions (Copy and Regenerate appear on hover) */}
      <div className="flex items-center gap-1.5 mt-2.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150 dark:text-[#8E9097] text-[#9CA3AF]">
        <button
          type="button"
          onClick={handleCopy}
          className="p-1 rounded-full dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] dark:text-[#8E9097] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] transition cursor-pointer"
          title="Copy answer"
          aria-label="Copy answer"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-[#10B981] stroke-[2.5]" /> : <Copy className="w-3.5 h-3.5 stroke-[1.75]" />}
        </button>

        {isLatest && !isLoading && (
          <button
            type="button"
            onClick={handleRegenerate}
            className="p-1 rounded-full dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] dark:text-[#8E9097] text-[#9CA3AF] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] transition cursor-pointer"
            title="Regenerate response"
            aria-label="Regenerate response"
          >
            <RotateCw className="w-3.5 h-3.5 stroke-[1.75]" />
          </button>
        )}
      </div>
    </div>
  );
};