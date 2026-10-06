import { Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";
import CandidateHome from "./pages/CandidateHome";
import Candidates from "./pages/Candidates";
import Dashboard from "./pages/Dashboard";
import Interviews from "./pages/Interviews";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import KnowledgeBase from "./pages/KnowledgeBase";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Reports from "./pages/Reports";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute role="interviewer" />}>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="knowledge-base" element={<KnowledgeBase />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="interviews" element={<Interviews />} />
          <Route path="reports" element={<Reports />} />
        </Route>
      </Route>

      <Route element={<ProtectedRoute role="candidate" />}>
        <Route path="candidate" element={<CandidateHome />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
