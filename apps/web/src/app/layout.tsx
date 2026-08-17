import type { Metadata, Viewport } from "next";
import { Inter, Orbitron } from "next/font/google";
import "./globals.css";
import { ClientShell } from "@/components/ClientShell";

const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CED — Castillo de la Evolución Digital",
  description:
    "CED es un asistente virtual inteligente que ayuda a gestionar tareas de negocio y personales con voz, texto e imágenes, e inicio de sesión opcional con Google solo con tu permiso.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "CED",
    statusBarStyle: "black",
  },
};

export const viewport: Viewport = {
  themeColor: "#042830",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" data-ced-theme="petrol" suppressHydrationWarning className={`scroll-smooth ${orbitron.variable} ${inter.variable}`}>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("ced-theme");if(t==="light"||t==="petrol"){document.documentElement.setAttribute("data-ced-theme",t);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="antialiased">
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
