export type CarouselCardKind =
  | "news"
  | "instagram"
  | "leads"
  | "trending"
  | "activity"
  | "business"
  | "system";

export type CarouselCardAccent =
  | "cyan"
  | "pink"
  | "red"
  | "orange"
  | "gold"
  | "green";

export interface CarouselCardData {
  id: string;
  kind: CarouselCardKind;
  title: string;
  accent: CarouselCardAccent;
  lines: string[];
  footer?: string;
  badge?: string;
  emphasis?: boolean;
}

export interface CarouselSnapshot {
  cards: CarouselCardData[];
  updatedAt: string;
  prospectionMode?: boolean;
}
