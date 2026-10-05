export const COMMUNITY_TOKENS = [
  { id: "saludar", label: "Saludar" },
  { id: "pensar", label: "Pensar" },
  { id: "confundido", label: "No entiendo" },
  { id: "ok", label: "Va" },
  { id: "celebrar", label: "Celebrar" },
  { id: "gracias", label: "Gracias" },
  { id: "idea", label: "Idea" },
  { id: "video", label: "Video" },
  { id: "alto", label: "Alto" },
  { id: "listo", label: "Listo" },
] as const;

export type CommunityTokenId = (typeof COMMUNITY_TOKENS)[number]["id"];

export function tokenSrc(id: string): string {
  return `/community/tokens/${id}.jpg`;
}
