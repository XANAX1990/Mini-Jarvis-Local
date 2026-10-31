import type { Metadata } from "next";
import Nav from "@/components/Nav";
import { JarvisProvider } from "@/lib/jarvis";
import "./globals.css";

export const metadata: Metadata = {
  title: "Jarvis",
  description: "ควบคุม Jarvis บนเครื่องนี้",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="th" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <JarvisProvider>
          <Nav />
          <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-8">{children}</main>
        </JarvisProvider>
      </body>
    </html>
  );
}
