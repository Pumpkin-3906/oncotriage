import { Routes, Route, Link, Navigate, useNavigate } from "react-router-dom";
import InputPage from "./pages/InputPage";
import ResultPage from "./pages/ResultPage";
import HistoryPage from "./pages/HistoryPage";
import OnboardingPage from "./pages/OnboardingPage";

function RootRedirect() {
  const onboarded = localStorage.getItem("sz_onboarded");
  return onboarded ? <InputPage /> : <Navigate to="/onboarding" replace />;
}

function HelpButton() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/onboarding")}
      title="重新查看引导"
      aria-label="帮助"
      className="ml-auto w-7 h-7 rounded-full border text-sm text-gray-600 hover:bg-gray-50"
    >
      ?
    </button>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="bg-white border-b">
        <nav className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-4">
          <Link to="/" className="font-medium">提交评估</Link>
          <Link to="/history" className="text-gray-600">历史记录</Link>
          <HelpButton />
        </nav>
      </header>
      <main className="max-w-2xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/result/:id" element={<ResultPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
