import { Routes, Route, Link, Navigate } from "react-router-dom";
import InputPage from "./pages/InputPage";
import ResultPage from "./pages/ResultPage";
import HistoryPage from "./pages/HistoryPage";

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="bg-white border-b">
        <nav className="max-w-2xl mx-auto px-4 py-3 flex gap-4">
          <Link to="/" className="font-medium">提交评估</Link>
          <Link to="/history" className="text-gray-600">历史记录</Link>
        </nav>
      </header>
      <main className="max-w-2xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<InputPage />} />
          <Route path="/result/:id" element={<ResultPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
