import React, { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import UsersNavBar from "./UsersNavBar";
import { getStorageUsage } from "../../services/UserService";

const UserLayout = () => {
  const [storageUsage, setStorageUsage] = useState(null);
  const [loadingUsage, setLoadingUsage] = useState(true);
  const [usageError, setUsageError] = useState(null);

  useEffect(() => {
    let isMounted = true;

    const loadUsage = async () => {
      try {
        const data = await getStorageUsage();
        if (isMounted) {
          setStorageUsage(data);
          setUsageError(null);
        }
      } catch (err) {
        if (isMounted) {
          console.error("Failed to load storage usage", err);
          setUsageError(err.message || "Failed to load storage usage");
        }
      } finally {
        if (isMounted) {
          setLoadingUsage(false);
        }
      }
    };

    loadUsage();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="user-layout">
      <UsersNavBar
        storageUsage={storageUsage}
        loadingUsage={loadingUsage}
        usageError={usageError}
      />
      <main className="user-main-content">
        <Outlet />
      </main>
    </div>
  );
};

export default UserLayout;