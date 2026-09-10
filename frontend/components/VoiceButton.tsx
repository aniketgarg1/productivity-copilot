"use client";

import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { MicIcon } from "@/components/Icons";

/**
 * Records a short clip and sends it to /voice/transcribe.
 *
 * MediaRecorder is unavailable in some browsers and over plain HTTP on a
 * non-localhost origin, so the button hides itself rather than failing on click.
 */
export function VoiceButton({
  onTranscribed,
  onError,
  disabled,
}: {
  onTranscribed: (text: string) => void;
  onError: (e: unknown) => void;
  disabled?: boolean;
}) {
  const [recording, setRecording] = useState(false);
  const [working, setWorking] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  // Detect support after mount. Checking it during render makes the server
  // output (no button) disagree with the client's, which fails hydration.
  const [supported, setSupported] = useState(false);
  useEffect(() => {
    setSupported(
      !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined",
    );
  }, []);

  if (!supported) return null;

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (blob.size === 0) return;

        setWorking(true);
        try {
          const { text } = await api.transcribe(blob);
          if (text.trim()) onTranscribed(text.trim());
        } catch (e) {
          onError(e);
        } finally {
          setWorking(false);
        }
      };

      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch (e) {
      onError(
        new Error(
          e instanceof DOMException && e.name === "NotAllowedError"
            ? "Microphone access was blocked. Allow it in your browser to dictate."
            : "Could not start recording.",
        ),
      );
    }
  }

  function stop() {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
  }

  return (
    <button
      type="button"
      className="btn"
      onClick={recording ? stop : start}
      disabled={disabled || working}
      title={recording ? "Stop and transcribe" : "Dictate your answer"}
      aria-label={recording ? "Stop recording and transcribe" : "Record your answer"}
      style={{
        padding: "11px 13px",
        borderColor: recording ? "var(--accent)" : undefined,
        background: recording ? "var(--accent-soft)" : undefined,
      }}
    >
      {working ? (
        <span className="spinner" />
      ) : (
        <MicIcon stroke={recording ? "var(--accent)" : "var(--muted)"} />
      )}
    </button>
  );
}
