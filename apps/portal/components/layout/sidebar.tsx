import { LayoutDashboard, Network, BookOpen, Inbox, Database, Activity, BarChart3, Settings, AlertTriangle, Map, GitBranch, SearchCode, Upload } from "lucide-react"
import Link from "next/link"

const navItems = [
    { name: "דשבורד", href: "/", icon: LayoutDashboard },
    { name: "חקר גרף", href: "/explore", icon: Network },
    { name: "לקסיקון", href: "/concepts", icon: BookOpen },
    { name: "תור סקירה", href: "/review", icon: Inbox },
    { name: "מקורות מידע", href: "/sources", icon: Database },
    { name: "ניטור Pipeline", href: "/pipeline", icon: Activity },
    { name: "אנליטיקה", href: "/analytics", icon: BarChart3 },
    { name: "הגדרות", href: "/settings", icon: Settings },
]

const impactNavItems = [
    { name: "לוח השפעה", href: "/impact", icon: AlertTriangle },
    { name: "מפה לוגיסטית", href: "/impact/locations", icon: Map },
    { name: "גרף תלויות", href: "/impact/graph", icon: GitBranch },
    { name: "ניתוח השפעה", href: "/impact/query", icon: SearchCode },
    { name: "טעינת מקורות", href: "/impact/sources", icon: Upload },
]


export function Sidebar({ className }: { className?: string }) {
    return (
        <div className={className}>
            <div className="p-6">
                <h1 className="text-xl font-bold tracking-tight text-primary">Agency Ontology</h1>
                <p className="text-sm text-muted-foreground mt-1">ניהול ידע ארגוני מבצעי</p>
            </div>
            <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
                {navItems.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium hover:bg-accent hover:text-accent-foreground text-muted-foreground transition-colors group"
                    >
                        <item.icon className="w-4 h-4" />
                        {item.name}
                    </Link>
                ))}

                {/* Impact Analysis Section */}
                <div className="pt-4 pb-1">
                    <p className="px-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/50">
                        ניתוח השפעה
                    </p>
                </div>
                {impactNavItems.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium hover:bg-accent hover:text-accent-foreground text-muted-foreground transition-colors group"
                    >
                        <item.icon className="w-4 h-4 text-amber-500/70 group-hover:text-amber-500" />
                        {item.name}
                    </Link>
                ))}
            </nav>
            <div className="p-4 border-t border-border/40 text-xs text-muted-foreground/60 text-center">
                v1.0.0 • מאובטח
            </div>
        </div>
    )
}

