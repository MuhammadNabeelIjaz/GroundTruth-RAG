import React from 'react';

interface BrandLogoIconProps {
  className?: string;
}

/**
 * RAG QA Assistant Bespoke Brand Icon
 * An elevated, multi-dimensional knowledge symbol for Grounded Document QA:
 * - Layered background document (representing grounded document library retrieval)
 * - Crisp foreground document with folded corner and semantic text lines
 * - Dynamic 4-point AI intelligence spark (representing RAG question answering)
 */
export const BrandLogoIcon: React.FC<BrandLogoIconProps> = ({
  className = 'w-6 h-6 text-[#10B981]',
}) => {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <g transform="translate(0.5, -2)">
        {/* Background Document (representing grounded multi-doc library) */}
        <path
          d="M5 8.5C5 7.12 6.12 6 7.5 6H15.5L19 9.5V17.5C19 18.88 17.88 20 16.5 20"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="opacity-35"
        />

        {/* Primary Foreground Document */}
        <path
          d="M8.5 10.5C8.5 9.12 9.62 8 11 8H19L23 12V21.5C23 22.88 21.88 24 20.5 24H11C9.62 24 8.5 22.88 8.5 21.5V10.5Z"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Folded Corner */}
        <path
          d="M19 8V12H23"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Semantic Knowledge Lines */}
        <line
          x1="12"
          y1="15.5"
          x2="19.5"
          y2="15.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <line
          x1="12"
          y1="19.5"
          x2="16.5"
          y2="19.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />

        {/* Radiant 4-Point AI Intelligence Spark (Top Left) */}
        <path
          d="M5 6C5 6 5.8 4.4 6.5 3.7C7.2 3 8.8 2.2 8.8 2.2C8.8 2.2 7.2 1.4 6.5 0.7C5.8 0 5 -1.6 5 -1.6C5 -1.6 4.2 0 3.5 0.7C2.8 1.4 1.2 2.2 1.2 2.2C1.2 2.2 2.8 3 3.5 3.7C4.2 4.4 5 6 5 6Z"
          fill="currentColor"
          transform="translate(1.5, 4.5)"
        />
      </g>
    </svg>
  );
};
