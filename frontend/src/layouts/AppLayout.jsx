import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/knowledge-base", label: "Knowledge Base" },
  { to: "/jobs", label: "Jobs" },
  { to: "/candidates", label: "Candidates" },
  { to: "/interviews", label: "Interviews" },
  { to: "/reports", label: "Reports" },
];

export default function AppLayout() {
  return (
    <div className="flex min-h-screen bg-gray-50 text-gray-900">
      <aside className="w-60 shrink-0 border-r border-gray-200 bg-white">
        <div className="px-6 py-5 text-xl font-bold text-indigo-600">Nikosh</div>
        <nav className="flex flex-col gap-1 px-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-6">
          <span className="text-sm text-gray-500">
            AI Recruitment & Interview Intelligence
          </span>
          <NavLink to="/login" className="text-sm font-medium text-indigo-600">
            Login
          </NavLink>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
