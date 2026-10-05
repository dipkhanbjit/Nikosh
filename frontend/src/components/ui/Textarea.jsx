export default function Textarea({ label, error, id, rows = 4, className = "", ...props }) {
  const textareaId = id || props.name;
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={textareaId} className="text-sm font-medium text-gray-700">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        rows={rows}
        className={`rounded-md border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500 ${
          error ? "border-red-500" : "border-gray-300"
        } ${className}`}
        {...props}
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
