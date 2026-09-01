"use client";

import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";

type Status = "checking" | "connected" | "offline";

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let mounted = true;
    void getHealth()
      .then(() => mounted && setStatus("connected"))
      .catch(() => mounted && setStatus("offline"));

    return () => {
      mounted = false;
    };
  }, []);

  const label =
    status === "connected" ? "Backend connected" : status === "offline" ? "Backend unavailable" : "Checking backend";

  return <p className={`status status--${status}`}>{label}</p>;
}

