import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { WatchlistList } from "./pages/WatchlistList";
import { WatchlistNew } from "./pages/WatchlistNew";
import { WatchlistDetail } from "./pages/WatchlistDetail";
import { WatchlistEdit } from "./pages/WatchlistEdit";

export default function App() {
  return (
    <BrowserRouter>
      <nav>
        <Link to="/watchlists">Watchlists</Link>
      </nav>
      <Routes>
        <Route path="/watchlists" element={<WatchlistList />} />
        <Route path="/watchlists/new" element={<WatchlistNew />} />
        <Route path="/watchlists/:id" element={<WatchlistDetail />} />
        <Route path="/watchlists/:id/edit" element={<WatchlistEdit />} />
      </Routes>
    </BrowserRouter>
  );
}
