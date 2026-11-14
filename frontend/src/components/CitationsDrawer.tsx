import React, { useState, useEffect } from 'react';
import { ChevronDown, FileText, Check, Copy } from 'lucide-react';
import type { SourceCitation } from '../types';

interface CitationsDrawerProps {
  sources: SourceCitation[];
  isExpanded?: boolean;
  onToggleExpand?: () => void;
  highlightedIndex?: number | null;
}

function cleanExcerptText(excerpt: string): string {
  if (!excerpt) return '';
  return excerpt
    .replace(/^["'\s*]+|["'\s]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export const CitationsDrawer: React.FC<CitationsDrawerProps> = ({
  sources,
  isExpanded: controlledExpanded,
  onToggleExpand,
  highlightedIndex,
}) => {
  const [internalExpanded, setInternalExpanded] = useState<boolean>(false);
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const toggleExpand = onToggleExpand || (() => setInternalExpanded(!internalExpanded));

  const [selectedSource, setSelectedSource] = useState<SourceCitation | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  // If highlightedIndex is specified, open drawer and select that source
  useEffect(() => {
    if (highlightedIndex !== null && highlightedIndex !== undefined && sources[highlightedIndex]) {
      setSelectedSource(sources[highlightedIndex]);
      if (!isExpanded) {
        if (onToggleExpand) {
          onToggleExpand();
        } else {
          setInternalExpanded(true);
        }
      }
    }
  }, [highlightedIndex, sources]);

  if (!sources || sources.length === 0) return null;

  const handleCopyExcerpt = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-3 select-none">
      {/* Small muted expander: "Sources · N" */}
      <button
        type="button"
        onClick={toggleExpand}
        className="inline-flex items-center gap-1.5 text-xs dark:text-[#8E9097] text-[#6B7280] hover:text-[#2C2D30] dark:hover:text-[#F3F4F6] transition-colors cursor-pointer"
        aria-expanded={isExpanded}
      >
        <span className="font-medium">Sources · {sources.length}</span>
        <ChevronDown
          className={`w-3.5 h-3.5 transition-transform duration-150 ${isExpanded ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Expanded: all sources listed as pills like user's design */}
      {isExpanded && (
        <div className="mt-2.5 space-y-2.5 animate-fade-in">
          <div className="flex flex-wrap gap-1.5">
            {sources.map((src, idx) => {
              const isSelected = selectedSource?.chunk_id
                ? selectedSource.chunk_id === src.chunk_id
                : selectedSource === src;
              const isHighlighted = highlightedIndex === idx;

              return (
                <button
                  key={src.chunk_id || idx}
                  type="button"
                  onClick={() => setSelectedSource(isSelected ? null : src)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-sans transition-colors cursor-pointer ${
                    isHighlighted
                      ? 'dark:bg-[#25272C] bg-[#ECEBE5] text-[#10B981] font-medium border border-[#10B981]'
                      : isSelected
                      ? 'dark:bg-emerald-950/40 bg-emerald-50 text-[#059669] dark:text-[#10B981] font-medium border border-[#10B981]/50 shadow-xs'
                      : 'dark:bg-[#1E2024] bg-[#F4F3EE] dark:hover:bg-[#25272C] hover:bg-[#ECEBE5] dark:text-[#9CA3AF] text-[#4B5563] dark:hover:text-[#F3F4F6] hover:text-[#2C2D30] dark:border-[#2D3036] border-[#E5E4DE] shadow-xs'
                  }`}
                  title={`Click to view passage from ${src.file_name}`}
                >
                  <FileText className="w-3.5 h-3.5 text-[#10B981] shrink-0 stroke-[1.75]" />
                  <span className="truncate max-w-[180px]">{src.file_name}</span>
                  <span className="dark:text-[#8E9097] text-[#9CA3AF] font-normal font-mono text-[11px]">
                    · p.{src.page_number}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Active source snippet view (Warm muted background matching app aesthetic) */}
          {selectedSource && (
            <div className="p-3.5 rounded-xl dark:bg-[#1E2024] bg-[#F4F3EE] dark:border-[#2D3036] border-[#E5E4DE] text-xs space-y-2 animate-fade-in shadow-xs">
              <div className="flex items-center justify-between text-[11.5px] font-medium">
                <span className="text-[#10B981] truncate">
                  {selectedSource.file_name} · Page {selectedSource.page_number}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  {selectedSource.similarity !== undefined && (
                    <span className="text-[11px] dark:text-[#8E9097] text-[#9CA3AF] font-mono">
                      similarity: {(selectedSource.similarity * 100).toFixed(0)}%
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleCopyExcerpt(selectedSource.excerpt)}
                    className="p-1 rounded dark:hover:bg-[#25272C] hover:bg-[#F0EFEA] text-[#8E9097] hover:text-[#2C2D30] dark:hover:text-white transition cursor-pointer"
                    title="Copy excerpt"
                    aria-label="Copy excerpt"
                  >
                    {copied ? (
                      <Check className="w-3.5 h-3.5 text-[#10B981]" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>
              <p className="dark:text-[#D1D5DB] text-[#4B5563] font-sans leading-relaxed text-[12.5px]">
                "{cleanExcerptText(selectedSource.excerpt)}"
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
