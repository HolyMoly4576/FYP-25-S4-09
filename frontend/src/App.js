import { useState } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ContactUs from "./pages/ContactUs";
import LoginForm from "./components/LoginForm";
import RegisterForm from "./components/RegisterForm";
import Layout from "./components/Layout";

function App() {
  const [showLogin, setShowLogin] = useState(false);
  const [showRegister, setShowRegister] = useState(false);

  const toggleLogin = () => setShowLogin((prev) => !prev);
  const toggleRegister = () => setShowRegister((prev) => !prev);

  // Optional: callback when registration succeeds
  const handleRegisterSuccess = (userData) => {
    // Show login popup or do other actions here
    setShowRegister(false);
    setShowLogin(true);
  };

  return (
    <Router>
      <Layout toggleLogin={toggleLogin}>
        <Routes>
          <Route path="/" element={<HomePage toggleLogin={toggleLogin} toggleRegister={toggleRegister}/>} />
          <Route path="/contact-us" element={<ContactUs />} />
          {/* other routes */}
        </Routes>
        {showLogin && <LoginForm toggle={toggleLogin} />}
        {showRegister && (
          <RegisterForm
            onClose={toggleRegister}
            onRegisterSuccess={handleRegisterSuccess}
          />
        )}
      </Layout>
    </Router>
  );
}

export default App;
