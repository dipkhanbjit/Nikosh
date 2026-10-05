import { Navigate, Outlet } from "react-router-dom";

import { getUser, homePathFor } from "../utils/auth";

export default function ProtectedRoute({ role }) {
  const user = getUser();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={homePathFor(user.role)} replace />;
  return <Outlet />;
}
