import { useState } from "react";

export default function RequirementsEditor({ requirements, onChange, editable }) {
  const [newText, setNewText] = useState("");

  // Editing the text clears the category so the backend re-detects it.
  const updateText = (index, text) =>
    onChange(requirements.map((r, i) => (i === index ? { text, category: null } : r)));

  const removeIfEmpty = (index) => {
    if (!requirements[index].text.trim()) remove(index);
  };

  const remove = (index) => onChange(requirements.filter((_, i) => i !== index));

  const add = () => {
    const text = newText.trim();
    if (!text) return;
    onChange([...requirements, { text, category: null }]);
    setNewText("");
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-gray-500">
        Every requirement is mandatory. Candidates must meet (or partially meet) all of them to be eligible.
      </p>

      {requirements.length === 0 ? (
        <p className="text-sm text-gray-500">No requirements yet.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {requirements.map((r, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="mt-2 w-5 shrink-0 text-right text-xs text-gray-400">{i + 1}.</span>
              {editable ? (
                <>
                  <input
                    value={r.text}
                    onChange={(e) => updateText(i, e.target.value)}
                    onBlur={() => removeIfEmpty(i)}
                    className="flex-1 rounded-md border border-gray-300 px-2 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    className="mt-1.5 text-xs text-gray-400 hover:text-red-600"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <p className="mt-1 flex-1 text-gray-800">{r.text}</p>
              )}
            </li>
          ))}
        </ol>
      )}

      {editable && (
        <div className="flex gap-2">
          <input
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            placeholder="Add a requirement, e.g. At least 3 years of experience with React"
            className="flex-1 rounded-md border border-gray-300 px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            type="button"
            onClick={add}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}