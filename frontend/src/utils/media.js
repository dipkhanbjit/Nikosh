// Camera / microphone helpers for the interview room

const STORAGE_KEY = "nikosh.devices";

// Devices chosen on this browser: { cameraId, micId }
export function loadDevices() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

export function saveDevices(devices) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(devices));
  } catch {
    // storage blocked: the browser default is used next time
  }
}

export function stopStream(stream) {
  stream?.getTracks().forEach((track) => track.stop());
}

// A saved id is only preferred, so a missing device falls back to the default one
const constraint = (deviceId) => (deviceId ? { deviceId } : true);

// Opens camera + microphone. If only the camera fails (missing or in use by the other
// browser in a same-PC test), continues with the microphone and returns a warning.
export async function openMedia({ cameraId, micId } = {}) {
  if (!navigator.mediaDevices?.getUserMedia) {
    const err = new Error("Media devices not supported");
    err.name = "NotSupportedError";
    throw err;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: constraint(cameraId), audio: constraint(micId) });
    return { stream, warning: "" };
  } catch (err) {
    if (err.name === "NotAllowedError" || err.name === "SecurityError") throw err;
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: constraint(micId) });
    } catch (micErr) {
      micErr.device = "microphone";
      throw micErr;
    }
    return { stream, warning: `${mediaErrorMessage(err, "camera")} You can join with your microphone only.` };
  }
}

export function mediaErrorMessage(err, device = "camera or microphone") {
  switch (err?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Access to the camera and microphone was denied. Allow it in the browser's site settings (address bar), then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return `No ${device} was found. Please connect one and try again.`;
    case "NotReadableError":
    case "AbortError":
      return `The ${device} is being used by another app or browser.`;
    case "NotSupportedError":
      return "This browser cannot use the camera here. Open the site on localhost or HTTPS.";
    default:
      return `Could not start the ${device}.`;
  }
}
