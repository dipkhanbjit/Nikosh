import { useState } from "react";

import { copyText } from "../utils/clipboard";
import { Alert, Button, Modal } from "./ui";

// One read-only value with a Copy button (used for the one-time candidate credentials)
function CopyField({ label, value }) {
  const [state, setState] = useState(""); // "", "copied" or "failed"

  const handleCopy = async () => setState((await copyText(value)) ? "copied" : "failed");

  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm font-medium text-gray-700">{label}</span>
      <div className="flex gap-2">
        <input
          readOnly
          value={value}
          onFocus={(e) => e.target.select()}
          className="min-w-0 flex-1 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-sm text-gray-800"
        />
        <Button variant="secondary" className="px-3 py-1" onClick={handleCopy}>
          {state === "copied" ? "Copied" : "Copy"}
        </Button>
      </div>
      {state === "failed" && <p className="text-xs text-red-600">Could not copy. Select the text and copy it manually.</p>}
    </div>
  );
}

export default function CredentialsModal({ credentials, onClose }) {
  const emailFailed = credentials?.invitationError?.includes("Email:");

  return (
    <Modal
      open={Boolean(credentials)}
      title="Candidate Login Details"
      onClose={onClose}
      closeOnBackdrop={false}
      footer={<Button onClick={onClose}>Done</Button>}
    >
      {credentials && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-gray-700">
            Login details for <span className="font-semibold">{credentials.name}</span>. They log in with this
            email and password, then open the interview link.
          </p>
          <CopyField label="Email" value={credentials.email} />
          <CopyField label="Password" value={credentials.password} />
          <CopyField label="Interview link" value={credentials.joinUrl} />
          {!emailFailed && <Alert type="info">Shown only once. Also sent to the candidate by email.</Alert>}
          {credentials.invitationError && (
            <Alert type="error">
              {emailFailed ? "The invitation email could not be sent. Please send these details yourself or use Resend on the Interviews page. " : ""}
              {credentials.invitationError}
            </Alert>
          )}
        </div>
      )}
    </Modal>
  );
}
