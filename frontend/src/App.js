import { useState } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ContactUs from "./pages/ContactUs";
import LoginForm from "./components/LoginForm";
import RegisterForm from "./components/RegisterForm";
import Layout from "./components/Layout";
import UserLayout from "./components/Users/UserLayout";
import UserDashboard from "./pages/Users/UserDashboard";

function App() {
  const [showLogin, setShowLogin] = useState(false);
  const [showRegister, setShowRegister] = useState(false);

  const toggleLogin = () => setShowLogin((prev) => !prev);
  const toggleRegister = () => setShowRegister((prev) => !prev);

  // Optional: callback when registration succeeds
  const handleRegisterSuccess = (userData) => {
    setShowRegister(false);
    setShowLogin(true);
  };

  return (
    <Router>
      <Routes>
        {/* PUBLIC PAGES use Layout (with public navbar) */}
        <Route element={<Layout toggleLogin={toggleLogin} />}>
          <Route
            path="/"
            element={
              <HomePage
                toggleLogin={toggleLogin}
                toggleRegister={toggleRegister}
              />
            }
          />
          <Route path="/contact-us" element={<ContactUs />} />
        </Route>

        {/* REGISTERED USERS PAGES use UserLayout (with UsersNavBar only) */}
        <Route path="/user-dashboard" element={<UserLayout />}>
          <Route index element={<UserDashboard />} />
          {/* Future:
          <Route path="files" element={<UserDashboard />} />
          <Route path="shared" element={<SharedPage />} />
          <Route path="activity" element={<ActivityPage />} /> */}
        </Route>
      </Routes>

      {/* Global modals */}
      {showLogin && <LoginForm toggle={toggleLogin} />}
      {showRegister && (
        <RegisterForm
          onClose={toggleRegister}
          onRegisterSuccess={handleRegisterSuccess}
        />
      )}
    </Router>
  );
}

export default App;
