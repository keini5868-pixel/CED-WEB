"use client";

import { createContext, useContext } from "react";

const CedOwnerUiContext = createContext(false);

/** Privilegio de dueño (super admin): ROBOT + ASIST. juntos. El resto solo ve ASIST. */
export function CedOwnerUiProvider({
  isOwner,
  children,
}: {
  isOwner: boolean;
  children: React.ReactNode;
}) {
  return <CedOwnerUiContext.Provider value={Boolean(isOwner)}>{children}</CedOwnerUiContext.Provider>;
}

export function useCedOwnerUi(): boolean {
  return useContext(CedOwnerUiContext);
}
