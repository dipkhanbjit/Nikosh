import { Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";
import CandidateAssessment from "./pages/CandidateAssessment";
import CandidateComparison from "./pages/CandidateComparison";
import CandidateHome from "./pages/CandidateHome";
import CandidateRoom from "./pages/CandidateRoom";
import Candidates from "./pages/Candidates";
import Dashboard from "./pages/Dashboard";
import InterviewerRoom from "./pages/InterviewerRoom";
import InterviewJoin from "./pages/InterviewJoin";
import Interviews from "./pages/Interviews";
import InterviewAnalysis from "./pages/InterviewAnalysis";
import InterviewTranscript from "./pages/InterviewTranscript";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import JDAssistant from "./pages/JDAssistant";
import KnowledgeBase from "./pages/KnowledgeBase";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Reports from "./pages/Reports";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/interview/join/:token" element={<InterviewJoin />} />
      <Route path="/interview/join/:token/room" element={<CandidateRoom />} />

      <Route element={<ProtectedRoute role="interviewer" />}>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="knowledge-base" element={<KnowledgeBase />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="jobs/:id/jd" element={<JDAssistant />} />
          <Route path="jobs/:id/comparison" element={<CandidateComparison />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="candidates/:id/assessment" element={<CandidateAssessment />} />
          <Route path="interviews" element={<Interviews />} />
          <Route path="interviews/:id/transcript" element={<InterviewTranscript />} />
          <Route path="interviews/:id/analysis" element={<InterviewAnalysis />} />
          <Route path="reports" element={<Reports />} />
        </Route>
        {/* full screen, outside the app layout */}
        <Route path="interviews/:id/room" element={<InterviewerRoom />} />
      </Route>

      <Route element={<ProtectedRoute role="candidate" />}>
        <Route path="candidate" element={<CandidateHome />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
