import { useEffect, useRef, useState } from "react";

import { ACCEPTED_TYPES, deleteDocument, listDocuments, uploadDocument } from "../api/knowledge";
import { Alert, Button, Modal, PageHeader, Spinner, Table } from "../components/ui";

export default function KnowledgeBase() {
  const fileInput = useRef(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deletingDoc, setDeletingDoc] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    listDocuments()
      .then(setDocuments)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleFiles = async (e) => {
    const files = Array.from(e.target.files);
    e.target.value = "";
    if (files.length === 0) return;

    setUploading(true);
    setError("");
    setNotice("");
    const added = [];
    const skipped = [];
    const failed = [];

    for (const file of files) {
      try {
        const doc = await uploadDocument(file);
        if (documents.some((d) => d.id === doc.id) || added.some((d) => d.id === doc.id)) {
          skipped.push(file.name);
        } else {
          added.push(doc);
        }
      } catch (err) {
        failed.push(`${file.name}: ${err.message}`);
      }
    }

    setDocuments((prev) => [...added, ...prev]);
    if (added.length) setNotice(`${added.length} document(s) added to the knowledge base.`);
    if (skipped.length) setNotice((n) => `${n} Already present: ${skipped.join(", ")}.`.trim());
    if (failed.length) setError(failed.join(" · "));
    setUploading(false);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteDocument(deletingDoc.id);
      setDocuments(documents.filter((d) => d.id !== deletingDoc.id));
      setDeletingDoc(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  const columns = [
    { key: "filename", label: "Document", render: (d) => <span className="font-medium text-gray-800">{d.filename}</span> },
    { key: "chunk_count", label: "Chunks" },
    { key: "created_at", label: "Uploaded", render: (d) => new Date(d.created_at).toLocaleString() },
    {
      key: "actions",
      label: "",
      render: (d) => (
        <div className="flex justify-end">
          <Button variant="secondary" className="px-3 py-1 text-red-600" onClick={() => setDeletingDoc(d)}>
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Knowledge Base"
        subtitle="Company documents used by the AI to generate job descriptions."
        actions={
          <Button onClick={() => fileInput.current.click()} loading={uploading}>
            {uploading ? "Processing…" : "Upload Documents"}
          </Button>
        }
      />
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPTED_TYPES}
        multiple
        onChange={handleFiles}
        className="hidden"
      />

      <p className="mb-4 text-xs text-gray-500">
        Accepted formats: PDF, DOCX, TXT, MD (max 10 MB). Scanned PDFs are read with OCR.
      </p>

      {notice && (
        <div className="mb-4">
          <Alert type="success">{notice}</Alert>
        </div>
      )}
      {error && (
        <div className="mb-4">
          <Alert type="error">{error}</Alert>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12 text-indigo-600">
          <Spinner size="lg" />
        </div>
      ) : (
        <Table columns={columns} data={documents} emptyMessage="No documents yet. Upload company documents to get started." />
      )}

      <Modal
        open={Boolean(deletingDoc)}
        title="Delete Document"
        onClose={() => setDeletingDoc(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeletingDoc(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleting} onClick={handleDelete}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-gray-700">
          Delete <span className="font-semibold">{deletingDoc?.filename}</span>? Its content will no
          longer be used for JD generation. Existing JDs are not affected.
        </p>
      </Modal>
    </div>
  );
}