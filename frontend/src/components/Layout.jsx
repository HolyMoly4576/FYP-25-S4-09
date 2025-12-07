import React from "react";
import { Outlet } from "react-router-dom";
import NavBar from "./NavBar";
import Footer from "./Footer";

function Layout({ toggleLogin }) {
  return (
    <div className="home-container">
      <NavBar toggleLogin={toggleLogin} />
      <div className="main-content">
        <Outlet /> {/* HomePage / ContactUs will appear here */}
      </div>
      <Footer />
    </div>
  );
}

export default Layout;
