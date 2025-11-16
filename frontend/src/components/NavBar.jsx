import React from 'react';
import { Link, useLocation } from "react-router-dom";
import '../styles/NavBar.css';
import ShardLogo from './Shard_Logo.png'; 


function NavBar({ toggleLogin }) {
  const location = useLocation();
  
  return (
    <nav className="navbar">
      <div className="logo">
        <img src={ShardLogo} alt="App Logo" className="logo-img" />
      </div>
      <ul className="nav-links">
        <li className={`nav-item${location.pathname === "/" ? " active" : ""}`}>
          <Link to="/">Home</Link>
        </li>
        <li className={`nav-item${location.pathname === "/contact-us" ? " active" : ""}`}>
          <Link to="/contact-us">Contact Us</Link>
        </li>
        <li className="nav-item">Tutorial</li>
        <li className="nav-item">Demo</li>
      </ul>
      <button className="login-btn" onClick={toggleLogin}>Log In</button>
    </nav>
  );
}

export default NavBar;
