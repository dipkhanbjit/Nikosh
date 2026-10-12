import { useEffect, useState } from "react";

import { DEFAULT_SCORE_WEIGHTS, getScoreWeights, SCORE_DIMENSIONS, updateScoreWeights } from "../api/jobs";
import { Alert, Badge, Button, Card } from "./ui";

export default function ScoringWeightsCard({ job, onSaved }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(DEFAULT_SCORE_WEIGHTS);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    getScoreWeights(job.id)
      .then((d) => {
        setData(d);
        setForm(d.weights);
      })
      .catch((err) => setError(err.message));
  }, [job.id]);

  const total = SCORE_DIMENSIONS.reduce((sum, d) => sum + (Number(form[d.key]) || 0), 0);

  const startEdit = () => {
    setForm(data.weights);
    setError("");
    setNotice("");
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const body = Object.fromEntries(SCORE_DIMENSIONS.map((d) => [d.key, Number(form[d.key]) || 0]));
      const saved = await updateScoreWeights(job.id, body);
      setData(saved);
      setEditing(false);
      setNotice(`Weights saved. Overall scores recalculated for ${saved.recalculated} candidate(s).`);
      onSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      title="Scoring Weights"
      actions={
        data && !editing && (
          <Button variant="secondary" className="px-3 py-1" onClick={startEdit}>
            Edit
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        {error && <Alert type="error">{error}</Alert>}
        {notice && <Alert type="success">{notice}</Alert>}
        {!data ? (
          <p className="text-gray-500">Loading…</p>
        ) : editing ? (
          <>
            {SCORE_DIMENSIONS.map((d) => (
              <div key={d.key} className="flex items-center justify-between gap-3">
                <label htmlFor={`w-${d.key}`} className="text-gray-700">
                  {d.label}
                </label>
                <div className="flex items-center gap-1">
                  <input
                    id={`w-${d.key}`}
                    type="number"
                    min="0"
                    max="100"
                    value={form[d.key]}
                    onChange={(e) => setForm({ ...form, [d.key]: e.target.value })}
                    className="w-20 rounded-md border border-gray-300 px-2 py-1 text-right outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <span className="text-gray-500">%</span>
                </div>
              </div>
            ))}
            <div className="flex justify-between border-t border-gray-100 pt-2">
              <span className="font-medium text-gray-700">Total</span>
              <span className={`font-semibold ${total === 100 ? "text-green-700" : "text-red-600"}`}>{total}%</span>
            </div>
            {total !== 100 && <p className="text-xs text-red-600">Weights must add up to 100%.</p>}
            <div className="flex justify-between gap-2">
              <Button variant="secondary" className="px-3 py-1" onClick={() => setForm(DEFAULT_SCORE_WEIGHTS)}>
                Reset to default
              </Button>
              <div className="flex gap-2">
                <Button variant="secondary" className="px-3 py-1" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
                <Button className="px-3 py-1" onClick={handleSave} loading={saving} disabled={total !== 100}>
                  Save
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            {data.is_default && (
              <div>
                <Badge color="gray">Default weights</Badge>
              </div>
            )}
            {SCORE_DIMENSIONS.map((d) => (
              <div key={d.key}>
                <div className="flex justify-between">
                  <span className="text-gray-600">{d.label}</span>
                  <span className="font-medium text-gray-800">{data.weights[d.key]}%</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-gray-100">
                  <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${data.weights[d.key]}%` }} />
                </div>
              </div>
            ))}
            <p className="text-xs text-gray-500">
              Overall score = weighted average of the dimension scores. Changing weights recalculates scores
              instantly without re-running the AI.
            </p>
          </>
        )}
      </div>
    </Card>
  );
}