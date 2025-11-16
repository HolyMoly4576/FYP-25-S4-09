import { useState } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ContactUs from "./pages/ContactUs";
import LoginForm from "./components/LoginForm";
import Layout from "./components/Layout"; // wherever you put Layout.jsx

function App() {
  const [showLogin, setShowLogin] = useState(false);

  const toggleLogin = () => setShowLogin((prev) => !prev);

  return (
    <Router>
      <Layout toggleLogin={toggleLogin}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/contact-us" element={<ContactUs />} />
          {/* other routes */}
        </Routes>
        {showLogin && <LoginForm toggle={toggleLogin} />}
      </Layout>
    </Router>
  );
}

export default App;
