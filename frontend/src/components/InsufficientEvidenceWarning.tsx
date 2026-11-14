import React from 'react';
import { Info } from 'lucide-react';

export const InsufficientEvidenceWarning: React.FC = () => {
  return (
    <div className="mt-2.5 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md dark:bg-[#25272C] bg-[#F3F4F6] border dark:border-[#2D3036] border-[#EBEAE5] text-xs dark:text-[#A1A1AA] text-[#4B5563] font-sans">
      <Info className="w-3.5 h-3.5 dark:text-[#A1A1AA] text-[#6B7280] shrink-0" />
      <span>I couldn't find sufficient evidence for this in your selected documents.</span>
    </div>
  );
};
