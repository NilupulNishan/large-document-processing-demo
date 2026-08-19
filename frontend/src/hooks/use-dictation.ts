"use client";

import { useCallback, useRef, useState } from "react";

import { transcribe } from "@/lib/api";
import { toWav16k } from "@/lib/audio";

export type DictationState = "idle" | "recording" | "transcribing";

/** Records a question and returns its text. It never sends: the caller puts the words in
 *  the box and the user decides. Transcription is least reliable exactly where the manual
 *  is most exact, so the human check stays in (D35). */
export function useDictation(onText: (text: string) => void) {
  const [state, setState] = useState<DictationState>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const stop = useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const start = useCallback(async () => {
    setError(null);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone permission was refused.");
      return;
    }

    const chunks: Blob[] = [];
    // Whatever this browser records is fine; it is decoded and re-encoded before it is sent.
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };

    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      setState("transcribing");
      try {
        const wav = await toWav16k(new Blob(chunks, { type: recorder.mimeType }));
        const text = await transcribe(wav);
        if (text) onText(text);
        else setError("Nothing was heard. Try again, closer to the microphone.");
      } catch {
        setError("Could not reach the speech service.");
      } finally {
        setState("idle");
      }
    };

    recorder.start();
    setState("recording");
  }, [onText]);

  return { state, error, start, stop, clearError: () => setError(null) };
}
