import React from "react";
import { Link } from "react-router-dom";
import "../styles/Footer.css";

// Instagram Icon SVG
const IGIcon = () => (
  <svg width="24" height="24" viewBox="0 0 448 448">
    <rect width="448" height="448" rx="96" fill="#fff"/>
    <radialGradient id="IGg" cx="0.7" cy="0.3" r="1" gradientTransform="scale(1.6)">
      <stop stopColor="#fae100"/>
      <stop offset="0.31" stopColor="#d62976"/>
      <stop offset="0.6" stopColor="#962fbf"/>
      <stop offset="1" stopColor="#4f5bd5"/>
    </radialGradient>
    <rect x="32" y="32" width="384" height="384" rx="96" fill="url(#IGg)"/>
    <circle cx="224" cy="224" r="80" fill="#fff"/>
    <circle cx="224" cy="224" r="60" fill="url(#IGg)"/>
    <circle cx="320" cy="128" r="16" fill="#fff"/>
  </svg>
);

// Facebook Icon SVG
const FBIcon = () => (
  <svg width="24" height="24" viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="24" fill="#fff" />
    <path
      d="M34 24C34 18.477 29.523 14 24 14C18.477 14 14 18.477 14 24C14 29.013 17.656 33.154 22.438 33.879V27.438H19.898V24H22.438V21.797C22.438 19.305 23.93 17.938 26.2 17.938C27.281 17.938 28.422 18.125 28.422 18.125V20.594H27.228C26.05 20.594 25.75 21.313 25.75 22.053V24H28.312L27.906 27.438H25.75V33.879C30.544 33.149 34 29.014 34 24Z"
      fill="#1877F2"
    />
  </svg>
);

// TikTok Icon SVG (official brand shape)
const TikTokIcon = () => (
  <svg width="24" height="24" viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="24" fill="#fff"/>
    <path d="M31.107 17.391a5.438 5.438 0 0 0 2.71.749v3.096a8.51 8.51 0 0 1-3.239-.619v7.633c0 4.194-3.472 7.606-7.603 7.606-4.13 0-7.491-3.336-7.491-7.466 0-3.932 3.694-7.203 7.754-7.466v3.177c-2.607.258-4.226 2.08-4.226 4.289 0 2.331 1.753 4.043 4.192 4.043 2.474 0 4.191-1.743 4.191-4.537V14.75h3.212v2.641Z" fill="#111"/>
    <path d="M31.897 18.957v3.096a8.51 8.51 0 0 1-3.239-.619v7.633c0 4.194-3.472 7.606-7.603 7.606v-3.035c2.432 0 4.191-1.812 4.191-4.537V14.75h3.211v2.641a5.44 5.44 0 0 0 2.44.749Z" fill="#25F4EE"/>
    <path d="M28.658 14.75v16.318c0 2.725-1.759 4.537-4.191 4.537v3.035c4.13 0 7.603-3.412 7.603-7.606v-7.633a8.508 8.508 0 0 0 3.239.619v-3.096a5.438 5.438 0 0 1-2.651-.749v-2.641h-4Z" fill="#FE2C55"/>
  </svg>
);


function Footer() {
  return (
    <footer className="footer">
      <div className="footer-links">
        <a href="/privacy_policy.pdf" download className="footer-link">
          Privacy Policy
        </a>
        <Link to="/contact-us" className="footer-link">
          Contact Us
        </Link>
      </div>
      <div className="footer-social">
        <span>Follow  us on our Social Media:</span>
        <a href="https://instagram.com/" target="_blank" rel="noopener noreferrer" aria-label="Instagram" className="social-icon">
          <IGIcon />
        </a>
        <a href="https://facebook.com/" target="_blank" rel="noopener noreferrer" aria-label="Facebook" className="social-icon">
          <FBIcon />
        </a>
        <a href="https://tiktok.com/" target="_blank" rel="noopener noreferrer" aria-label="TikTok" className="social-icon">
          <TikTokIcon />
        </a>
      </div>
      <div className="footer-copyright">
        Copyright 2025 Shard Group FYP-25-S4-09
      </div>
    </footer>
  );
}

export default Footer;
