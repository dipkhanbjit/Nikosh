import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-gray-50">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="text-indigo-600">Go to Dashboard</Link>
    </div>
  );
}
