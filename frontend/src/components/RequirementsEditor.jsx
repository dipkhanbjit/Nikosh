const CATEGORY_LABELS = { skill: "Skill", experience: "Experience", qualification: "Qualification" };

export default function RequirementsEditor({ requirements, onChange, editable }) {
  const update = (index, changes) =>
    onChange(requirements.map((r, i) => (i === index ? { ...r, ...changes } : r)));

  const remove = (index) => onChange(requirements.filter((_, i) => i !== index));

  if (requirements.length === 0) {
    return <p className="text-sm text-gray-500">No requirements extracted yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
            <th className="py-2 pr-3 font-medium">Requirement</th>
            <th className="py-2 pr-3 font-medium">Category</th>
            <th className="py-2 pr-3 text-center font-medium">Mandatory</th>
            <th className="py-2 pr-3 text-center font-medium">Weight</th>
            {editable && <th className="py-2" />}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {requirements.map((r, i) => (
            <tr key={i}>
              <td className="py-2 pr-3 text-gray-800">{r.text}</td>
              <td className="py-2 pr-3 text-gray-500">{CATEGORY_LABELS[r.category]}</td>
              <td className="py-2 pr-3 text-center">
                <input
                  type="checkbox"
                  checked={r.mandatory}
                  disabled={!editable}
                  onChange={(e) => update(i, { mandatory: e.target.checked })}
                  className="h-4 w-4 accent-indigo-600"
                />
              </td>
              <td className="py-2 pr-3 text-center">
                {editable ? (
                  <select
                    value={r.weight}
                    onChange={(e) => update(i, { weight: Number(e.target.value) })}
                    className="rounded border border-gray-300 bg-white px-1.5 py-0.5 text-sm"
                  >
                    {[1, 2, 3, 4, 5].map((w) => (
                      <option key={w} value={w}>
                        {w}
                      </option>
                    ))}
                  </select>
                ) : (
                  r.weight
                )}
              </td>
              {editable && (
                <td className="py-2 text-right">
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    className="text-xs text-gray-400 hover:text-red-600"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}