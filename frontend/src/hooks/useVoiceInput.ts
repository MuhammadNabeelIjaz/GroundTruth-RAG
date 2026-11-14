import { useState, useRef, useEffect, useCallback } from 'react';

export type VoiceState = 'idle' | 'requesting' | 'recording' | 'error';

export interface UseVoiceInputReturn {
  supported: boolean;
  state: VoiceState;
  transcript: string;
  interimTranscript: string;
  analyserNode: AnalyserNode | null;
  error: string | null;
  hint: string | null;
  elapsedSeconds: number;
  currentLang: 'en-IN' | 'hi-IN';
  setLang: (lang: 'en-IN' | 'hi-IN') => void;
  start: () => Promise<void>;
  stop: () => void;
  cancel: () => void;
}

const VOICE_LANG_KEY = 'rag.voiceLang.v1';

export function useVoiceInput(
  onTranscriptUpdate?: (fullDictatedText: string, interimText: string) => void,
  onAutoConfirm?: (finalText: string) => void
): UseVoiceInputReturn {
  const SpeechRecognitionClass =
    typeof window !== 'undefined'
      ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      : null;

  const isSecure =
    typeof window !== 'undefined' &&
    (window.isSecureContext ||
      window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1');

  const supported = Boolean(SpeechRecognitionClass && isSecure);

  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState<string>('');
  const [interimTranscript, setInterimTranscript] = useState<string>('');
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  const [currentLang, setCurrentLangState] = useState<'en-IN' | 'hi-IN'>(() => {
    try {
      const saved = localStorage.getItem(VOICE_LANG_KEY);
      if (saved === 'en-IN' || saved === 'hi-IN') return saved;
      if (typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('hi')) {
        return 'hi-IN';
      }
    } catch {}
    return 'en-IN';
  });

  const setLang = useCallback((lang: 'en-IN' | 'hi-IN') => {
    setCurrentLangState(lang);
    try {
      localStorage.setItem(VOICE_LANG_KEY, lang);
    } catch {}
  }, []);

  // Internal references
  const recognitionRef = useRef<any>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const isIntentionalRecordingRef = useRef<boolean>(false);
  const committedTextRef = useRef<string>('');
  const interimTextRef = useRef<string>('');
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxSilenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up audio streams and context
  const cleanupAudio = useCallback(() => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (maxSilenceTimerRef.current) {
      clearTimeout(maxSilenceTimerRef.current);
      maxSilenceTimerRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {}
      });
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current) {
      try {
        audioContextRef.current.close().catch(() => {});
      } catch {}
      audioContextRef.current = null;
    }

    setAnalyserNode(null);
  }, []);

  const resetSilenceTimers = useCallback(() => {
    setHint(null);
    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
    if (maxSilenceTimerRef.current) clearTimeout(maxSilenceTimerRef.current);

    // 8 seconds of silence: gentle hint
    silenceTimerRef.current = setTimeout(() => {
      if (isIntentionalRecordingRef.current) {
        setHint('Listening… say something');
      }
    }, 8000);

    // 30 seconds of silence: auto-stop and confirm
    maxSilenceTimerRef.current = setTimeout(() => {
      if (isIntentionalRecordingRef.current) {
        // Auto-stop and keep captured text
        const finalText = (committedTextRef.current + (interimTextRef.current ? ' ' + interimTextRef.current : '')).trim();
        isIntentionalRecordingRef.current = false;
        cleanupAudio();
        if (recognitionRef.current) {
          try {
            recognitionRef.current.stop();
          } catch {}
        }
        setState('idle');
        onAutoConfirm?.(finalText);
      }
    }, 30000);
  }, [cleanupAudio, onAutoConfirm]);

  const start = useCallback(async () => {
    if (!supported || !SpeechRecognitionClass) {
      console.warn('SpeechRecognition is not supported or context is insecure.');
      return;
    }

    setError(null);
    setHint(null);
    setState('requesting');
    committedTextRef.current = '';
    interimTextRef.current = '';
    setTranscript('');
    setInterimTranscript('');
    setElapsedSeconds(0);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
    } catch (err: any) {
      const name = err?.name;
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setError('Microphone access is blocked. Allow it in your browser’s site settings to use voice input.');
      } else {
        setError('No microphone available.');
      }
      setState('error');
      return;
    }

    // Set up Web Audio Analyser
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.5;
      source.connect(analyser);
      setAnalyserNode(analyser);
    } catch (e) {
      console.warn('AudioContext failed to initialize:', e);
    }

    // Set up SpeechRecognition
    const recognition = new SpeechRecognitionClass();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = currentLang;

    recognition.onresult = (event: any) => {
      resetSilenceTimers();
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const res = event.results[i];
        if (res.isFinal) {
          const phrase = res[0].transcript.trim();
          if (phrase) {
            committedTextRef.current += (committedTextRef.current ? ' ' : '') + phrase;
          }
        } else {
          interim += res[0].transcript;
        }
      }
      interimTextRef.current = interim;
      setTranscript(committedTextRef.current);
      setInterimTranscript(interim);

      const combined = (committedTextRef.current + (interim ? ' ' + interim : '')).trim();
      onTranscriptUpdate?.(combined, interim);
    };

    recognition.onerror = (event: any) => {
      const err = event.error;
      if (err === 'not-allowed') {
        setError('Microphone access is blocked. Allow it in your browser’s site settings to use voice input.');
        setState('error');
        isIntentionalRecordingRef.current = false;
        cleanupAudio();
      } else if (err === 'audio-capture') {
        setError('No microphone available.');
        setState('error');
        isIntentionalRecordingRef.current = false;
        cleanupAudio();
      } else if (err === 'network') {
        setError('Voice input interrupted. Please try again.');
        // Keep text already captured
        stop();
      } else if (err === 'no-speech') {
        // Normal silence timeout handled by onend auto-restart
      }
    };

    recognition.onend = () => {
      // Chrome ends recognition after periods of silence; auto-restart if still recording!
      if (isIntentionalRecordingRef.current) {
        try {
          recognition.start();
        } catch {
          // If restart fails, retry shortly
          setTimeout(() => {
            if (isIntentionalRecordingRef.current) {
              try {
                recognition.start();
              } catch {}
            }
          }, 250);
        }
      }
    };

    recognitionRef.current = recognition;
    isIntentionalRecordingRef.current = true;

    try {
      recognition.start();
      setState('recording');
      resetSilenceTimers();

      // Start elapsed timer
      timerIntervalRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
      setError('Could not start voice recognition.');
      setState('error');
      cleanupAudio();
    }
  }, [supported, SpeechRecognitionClass, currentLang, resetSilenceTimers, cleanupAudio, onTranscriptUpdate]);

  // Stop recording and KEEP dictated text (Confirm)
  const stop = useCallback(() => {
    isIntentionalRecordingRef.current = false;
    cleanupAudio();
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }
    setState('idle');
    setHint(null);
  }, [cleanupAudio]);

  // Cancel recording and DISCARD dictated text
  const cancel = useCallback(() => {
    isIntentionalRecordingRef.current = false;
    cleanupAudio();
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {}
      recognitionRef.current = null;
    }
    committedTextRef.current = '';
    interimTextRef.current = '';
    setTranscript('');
    setInterimTranscript('');
    setState('idle');
    setHint(null);
  }, [cleanupAudio]);

  // Handle visibility change (tab hidden) & window unmount
  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden && isIntentionalRecordingRef.current) {
        stop();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      cleanupAudio();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
    };
  }, [stop, cleanupAudio]);

  return {
    supported,
    state,
    transcript,
    interimTranscript,
    analyserNode,
    error,
    hint,
    elapsedSeconds,
    currentLang,
    setLang,
    start,
    stop,
    cancel,
  };
}

