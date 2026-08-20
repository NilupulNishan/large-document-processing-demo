"use client";

import { useCallback, useRef, useState } from "react";
import type { SpeechRecognizer } from "microsoft-cognitiveservices-speech-sdk";

import { speechToken, transcribe } from "@/lib/api";
import { toWav16k } from "@/lib/audio";

export type DictationState = "idle" | "starting" | "listening" | "transcribing";
/** Which path the current attempt took. The caller must not have to read an error
 *  message to find out whether it is streaming or recording. */
export type DictationMode = "live" | "recording" | null;

/** Dictation. It never sends: the caller puts the words in the box and the user decides.
 *
 *  Live recognition streams to Azure and reports each revision as it talks. If that cannot
 *  start — a blocked WebSocket, a token the browser could not fetch — it falls back to
 *  recording and transcribing on stop, which is slower but survives a hostile network (D36). */
export function useDictation(onText: (text: string) => void) {
  const [state, setState] = useState<DictationState>("idle");
  const [mode, setMode] = useState<DictationMode>(null);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognizerRef = useRef<SpeechRecognizer | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  // Starting is slow — a token fetch, a 7 MB dynamic import and a socket — and the
  // button stays clickable throughout. Without this a second click opens a second
  // recogniser on the same microphone and every phrase arrives twice.
  const startingRef = useRef(false);

  const startLive = useCallback(async () => {
    const { token, region } = await speechToken();
    // Imported here, not at module scope: 7 MB the page never loads unless someone dictates.
    const sdk = await import("microsoft-cognitiveservices-speech-sdk");

    const config = sdk.SpeechConfig.fromAuthorizationToken(token, region);
    config.speechRecognitionLanguage = "en-US";
    const recognizer = new sdk.SpeechRecognizer(
      config,
      sdk.AudioConfig.fromDefaultMicrophoneInput(),
    );

    // Revised constantly while talking, so it stays out of the textarea until it is final.
    recognizer.recognizing = (_, event) => setInterim(event.result.text);
    recognizer.recognized = (_, event) => {
      setInterim("");
      if (event.result.reason === sdk.ResultReason.RecognizedSpeech && event.result.text) {
        onText(event.result.text);
      }
    };
    recognizer.canceled = (_, event) => {
      setError(event.errorDetails || "Recognition stopped unexpectedly.");
      setInterim("");
      setMode(null);
      setState("idle");
    };

    try {
      await new Promise<void>((resolve, reject) =>
        recognizer.startContinuousRecognitionAsync(resolve, reject),
      );
    } catch (error) {
      recognizer.close();
      throw error;
    }
    recognizerRef.current = recognizer;
    setMode("live");
    setState("listening");
  }, [onText]);

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks: Blob[] = [];
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
        const text = await transcribe(await toWav16k(new Blob(chunks, { type: recorder.mimeType })));
        if (text) onText(text);
        else setError("Nothing was heard. Try again, closer to the microphone.");
      } catch {
        setError("Could not reach the speech service.");
      } finally {
        setMode(null);
        setState("idle");
      }
    };

    recorder.start();
    setMode("recording");
    setState("listening");
  }, [onText]);

  const start = useCallback(async () => {
    if (startingRef.current || recognizerRef.current || recorderRef.current) return;
    startingRef.current = true;
    setError(null);
    setInterim("");
    setMode(null);
    setState("starting");
    try {
      await startLive();
    } catch {
      try {
        setError("Live transcription unavailable — recording instead.");
        await startRecording();
      } catch {
        setError("Microphone unavailable. Check the browser's permission for this site.");
        setMode(null);
        setState("idle");
      }
    } finally {
      startingRef.current = false;
    }
  }, [startLive, startRecording]);

  const stop = useCallback(() => {
    const recognizer = recognizerRef.current;
    if (recognizer) {
      recognizerRef.current = null;
      recognizer.stopContinuousRecognitionAsync(() => {
        recognizer.close();
        setInterim("");
        setMode(null);
        setState("idle");
      });
      return;
    }
    recorderRef.current?.stop();
  }, []);

  return { state, mode, interim, error, start, stop };
}
