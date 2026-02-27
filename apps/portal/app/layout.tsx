import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
    title: "Agency Ontology Portal",
    description: "Enterprise Semantic Knowledge Graph for The Agency",
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="he" dir="rtl" className="dark">
            <body className={`${inter.className} bg-background text-foreground h-screen flex overflow-hidden`}>
                <Sidebar className="w-64 border-l border-border/40 shrink-0 bg-card hidden md:flex flex-col" />
                <div className="flex-1 flex flex-col min-w-0 h-full">
                    <Header />
                    <main className="flex-1 overflow-auto bg-muted/30">
                        {children}
                    </main>
                </div>
            </body>
        </html>
    )
}
