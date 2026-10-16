import { Button, Modal } from "./ui";

const displayName = (c) => c?.full_name || c?.cv_filename || "this candidate";

// Delete confirmation; Google Form applications also ask whether to delete the CV from Drive
export default function DeleteCandidateModal({ candidate, busy, onCancel, onDelete, note }) {
  const fromForm = candidate?.source === "form";

  return (
    <Modal
      open={Boolean(candidate)}
      title="Delete Candidate"
      onClose={onCancel}
      footer={
        fromForm ? (
          <>
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
            <Button variant="secondary" onClick={() => onDelete(false)} disabled={busy}>
              No, only from Nikosh
            </Button>
            <Button variant="danger" onClick={() => onDelete(true)} loading={busy}>
              Yes, delete from Drive
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => onDelete(false)} loading={busy}>
              Delete
            </Button>
          </>
        )
      }
    >
      {fromForm ? (
        <div className="flex flex-col gap-2 text-sm text-gray-700">
          <p>
            Delete <span className="font-semibold">{displayName(candidate)}</span>? Do you also want to delete
            their CV from Google Drive?
          </p>
          <ul className="list-disc space-y-1 pl-5 text-gray-600">
            <li>
              <span className="font-medium">Yes:</span> the CV is removed from Drive and will never be imported
              again.
            </li>
            <li>
              <span className="font-medium">No:</span> removed from Nikosh only; it will be imported again on the
              next sync.
            </li>
          </ul>
        </div>
      ) : (
        <p className="text-sm text-gray-700">
          Delete <span className="font-semibold">{displayName(candidate)}</span>? Their record and CV file will be
          permanently removed.
        </p>
      )}
      {note && <p className="mt-3 text-sm text-gray-700">{note}</p>}
    </Modal>
  );
}
