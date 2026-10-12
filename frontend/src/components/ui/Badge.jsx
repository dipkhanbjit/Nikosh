const colors = {
  gray: "bg-gray-100 text-gray-700 ring-gray-200",
  green: "bg-green-50 text-green-700 ring-green-200",
  yellow: "bg-yellow-50 text-yellow-800 ring-yellow-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  purple: "bg-purple-50 text-purple-700 ring-purple-200",
};

export default function Badge({ color = "gray", children }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${colors[color] ?? colors.gray}`}
    >
      {children}
    </span>
  );
}