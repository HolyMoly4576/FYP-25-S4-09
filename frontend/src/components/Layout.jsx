import React from "react";
import NavBar from "./NavBar";
import Footer from "./Footer";

function Layout({ children, toggleLogin }) {
  return (
    <div className="home-container">
      <NavBar toggleLogin={toggleLogin} />
      <div className="main-content">{children}</div>
      <Footer />
    </div>
  );
}

export default Layout;
