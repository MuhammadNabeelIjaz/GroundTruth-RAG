import React, { useEffect, useRef, useState } from 'react';

interface AudioWaveformProps {
  analyserNode: AnalyserNode | null;
  barCount?: number;
}

export const AudioWaveform: React.FC<AudioWaveformProps> = ({
  analyserNode,
  barCount = 24,
}) => {
  const [heights, setHeights] = useState<number[]>(() =>
    new Array(barCount).fill(4)
  );

  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const animFrameIdRef = useRef<number | null>(null);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const listener = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
    mediaQuery.addEventListener('change', listener);
    return () => mediaQuery.removeEventListener('change', listener);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion || !analyserNode) {
      setHeights(new Array(barCount).fill(4));
      return;
    }

    const bufferLength = analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    let lastRender = 0;

    const renderFrame = (now: number) => {
      // Limit to ~30 FPS (33ms interval) for performance
      if (now - lastRender >= 33) {
        lastRender = now;
        analyserNode.getByteFrequencyData(dataArray);

        // Calculate average or distributed frequency values across barCount
        const step = Math.max(1, Math.floor(bufferLength / barCount));
        const newHeights: number[] = [];

        for (let i = 0; i < barCount; i++) {
          const index = Math.min(i * step, bufferLength - 1);
          const value = dataArray[index] || 0;
          // Scale from 0-255 to 3px - 16px (fits cleanly within h-8 bar without layout shift)
          const normalized = value / 255;
          const height = Math.max(3, Math.round(normalized * 16));
          newHeights.push(height);
        }

        setHeights(newHeights);
      }

      animFrameIdRef.current = requestAnimationFrame(renderFrame);
    };

    animFrameIdRef.current = requestAnimationFrame(renderFrame);

    return () => {
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
    };
  }, [analyserNode, barCount, prefersReducedMotion]);

  if (prefersReducedMotion) {
    return (
      <div
        className="flex items-center gap-1.5 px-2 select-none h-6"
        aria-hidden="true"
      >
        <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
        <span className="text-[11px] text-[#10B981] font-medium">Listening</span>
      </div>
    );
  }

  return (
    <div
      className="flex items-center justify-center gap-[2.5px] h-6 px-1.5 select-none overflow-hidden"
      aria-hidden="true"
    >
      {heights.map((h, i) => (
        <span
          key={i}
          className="w-[2px] rounded-full bg-[#10B981] transition-[height] duration-75 ease-out"
          style={{ height: `${h}px` }}
        />
      ))}
    </div>
  );
};

