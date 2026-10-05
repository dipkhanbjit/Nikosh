export default function Card({ title, actions, className = "", children }) {
  return (
    <div className={`rounded-lg border border-gray-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}
