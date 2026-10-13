import { useCallback, useEffect, useRef, useState } from "react";

import { loadDevices, mediaErrorMessage, openMedia, saveDevices, stopStream } from "../../utils/media";
import { Alert, Button, Spinner } from "../ui";

function MicLevel({ stream }) {
  const barRef = useRef(null);

  useEffect(() => {
    if (!stream?.getAudioTracks().length) return undefined;
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    let frame;

    const draw = () => {
      analyser.getByteTimeDomainData(samples);
      let peak = 0;
      for (const s of samples) peak = Math.max(peak, Math.abs(s - 128));
      if (barRef.current) barRef.current.style.width = `${Math.min(100, (peak / 128) * 200)}%`;
      frame = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(frame);
      context.close();
    };
  }, [stream]);

  return (
    <div className="h-2 rounded-full bg-gray-200">
      <div ref={barRef} className="h-2 w-0 rounded-full bg-green-500 transition-[width] duration-75" />
    </div>
  );
}

function DeviceSelect({ label, value, devices, onChange, disabled }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-gray-700">{label}</span>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || devices.length === 0}
        className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50"
      >
        {!value && <option value="">{devices.length ? `Select ${label.toLowerCase()}` : "None found"}</option>}
        {devices.map((d, i) => (
          <option key={d.deviceId} value={d.deviceId}>
            {d.label || `${label} ${i + 1}`}
          </option>
        ))}
      </select>
    </label>
  );
}

// Camera / microphone check before entering the room. On "Join now" the open stream is
// handed to onJoin(stream); from then on the caller owns it and must stop it.
export default function DeviceCheck({ title, subtitle, onJoin, onBack }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const requestRef = useRef(0); // ignores results of older device requests
  const handedOff = useRef(false);
  const [stream, setStream] = useState(null);
  const [devices, setDevices] = useState({ cameras: [], mics: [] });
  const [selected, setSelected] = useState({});
  const [starting, setStarting] = useState(true);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [joinError, setJoinError] = useState("");
  const [joining, setJoining] = useState(false);

  const refreshDevices = useCallback(async () => {
    const list = await navigator.mediaDevices.enumerateDevices();
    setDevices({
      cameras: list.filter((d) => d.kind === "videoinput" && d.deviceId),
      mics: list.filter((d) => d.kind === "audioinput" && d.deviceId),
    });
  }, []);

  const start = useCallback(
    (choice) => {
      const id = ++requestRef.current;
      const current = () => id === requestRef.current; // false after a newer request or unmount
      openMedia(choice)
        .then((result) => {
          if (!current()) {
            stopStream(result.stream);
            return undefined;
          }
          streamRef.current = result.stream;
          setStream(result.stream);
          setWarning(result.warning);
          setSelected({
            cameraId: result.stream.getVideoTracks()[0]?.getSettings().deviceId || "",
            micId: result.stream.getAudioTracks()[0]?.getSettings().deviceId || "",
          });
          return refreshDevices(); // device names are only available after permission
        })
        .catch((err) => current() && setError(mediaErrorMessage(err, err.device)))
        .finally(() => current() && setStarting(false));
    },
    [refreshDevices]
  );

  useEffect(() => {
    start(loadDevices());
    navigator.mediaDevices?.addEventListener("devicechange", refreshDevices);
    return () => {
      requestRef.current += 1;
      navigator.mediaDevices?.removeEventListener("devicechange", refreshDevices);
      if (!handedOff.current) stopStream(streamRef.current);
    };
  }, [start, refreshDevices]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = stream;
  }, [stream]);

  // Close the current devices and open the chosen ones
  const restart = (choice) => {
    stopStream(streamRef.current);
    streamRef.current = null;
    setStream(null);
    setStarting(true);
    setError("");
    setWarning("");
    start(choice);
  };

  const choose = (key, value) => restart({ ...selected, [key]: value });

  const join = async () => {
    saveDevices(selected);
    setJoining(true);
    setJoinError("");
    handedOff.current = true;
    try {
      await onJoin(streamRef.current);
    } catch (err) {
      handedOff.current = false;
      setJoinError(err.message || "Could not join the interview.");
      setJoining(false);
    }
  };

  const hasVideo = Boolean(stream?.getVideoTracks().length);
  const hasAudio = Boolean(stream?.getAudioTracks().length);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-4xl rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}

        <div className="mt-5 grid gap-6 md:grid-cols-[3fr_2fr]">
          <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-gray-900">
            <video ref={videoRef} autoPlay playsInline muted className={`h-full w-full -scale-x-100 object-cover ${hasVideo ? "" : "hidden"}`} />
            {!hasVideo && (
              <div className="text-sm text-gray-300">
                {starting ? <Spinner /> : "Camera is not available"}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <DeviceSelect
              label="Camera"
              value={selected.cameraId}
              devices={devices.cameras}
              onChange={(v) => choose("cameraId", v)}
              disabled={starting || joining}
            />
            <DeviceSelect
              label="Microphone"
              value={selected.micId}
              devices={devices.mics}
              onChange={(v) => choose("micId", v)}
              disabled={starting || joining}
            />
            <div className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-gray-700">Microphone level</span>
              <MicLevel stream={stream} />
              <span className="text-xs text-gray-500">Speak to check that the bar moves.</span>
            </div>

            {error && (
              <Alert type="error">
                <p>{error}</p>
                <button type="button" onClick={() => restart(selected)} className="mt-2 font-medium underline">
                  Try again
                </button>
              </Alert>
            )}
            {warning && <Alert type="info">{warning}</Alert>}
            {joinError && <Alert type="error">{joinError}</Alert>}

            <div className="mt-auto flex justify-end gap-2">
              {onBack && (
                <Button variant="secondary" onClick={onBack} disabled={joining}>
                  Back
                </Button>
              )}
              <Button onClick={join} loading={joining} disabled={starting || !hasAudio}>
                Join now
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
