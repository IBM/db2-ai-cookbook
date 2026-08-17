import "./App.css";
import CategoryBar from "./components/CategoryNavigation";
import Header from "./components/Header";
import ShoeList from "./components/ShoeList";
import SideNav from "./components/SideNav";
import ShoeDetails from "./components/ShoeDetails";
import { Routes, Route, useLocation } from "react-router-dom";

function App() {
  const location = useLocation();

  // Hide SideNav on detail page
  const hideSideNav = location.pathname.startsWith("/shoe/");

  return (
    <>
      <Header />
      <CategoryBar />
      {!hideSideNav && <SideNav />}
      <Routes>
        <Route path="/" element={<ShoeList />} />
        <Route path="/shoe/:id" element={<ShoeDetails />} />
      </Routes>
    </>
  );
}

export default App;
