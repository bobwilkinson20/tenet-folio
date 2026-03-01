import { useEffect, useState } from "react";
import { apiClient } from "@/api/client";

export function ProfileBadge() {
  const [profile, setProfile] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<{ profile: string | null }>("/config/profile")
      .then((res) => setProfile(res.data.profile))
      .catch((err) => {
        console.warn("ProfileBadge: could not fetch profile", err);
      });
  }, []);

  if (!profile) return null;

  return (
    <span className="rounded-full bg-tf-accent-muted px-2.5 py-0.5 text-[11px] font-medium text-tf-accent-hover">
      {profile}
    </span>
  );
}
