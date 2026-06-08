"use client";

import { useEffect, useState } from "react";

import { fetchUsageBalance } from "@/lib/api/usage";
import { TrialExpiredModal } from "@/components/billing/RechargeModal";

export function TrialExpiredBanner() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const data = await fetchUsageBalance();
        if (
          data &&
          (data as { access_message?: string }).access_message === "trial_expired"
        ) {
          setOpen(true);
        }
      } catch {
        /* ignore */
      }
    })();
  }, []);

  return (
    <TrialExpiredModal
      open={open}
      onClose={() => setOpen(false)}
    />
  );
}
