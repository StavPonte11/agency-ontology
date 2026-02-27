import { Bell } from "lucide-react"

export function Header() {
    return (
        <header className="h-14 border-b border-border/40 bg-card/50 backdrop-blur-sm flex items-center justify-between px-6 shrink-0">
            <div className="flex items-center gap-4">
                {/* Placeholder for breadcrumbs or current page title */}
            </div>
            <div className="flex items-center gap-4">
                <button className="relative p-2 text-muted-foreground hover:bg-accent rounded-full transition-colors">
                    <Bell className="w-5 h-5" />
                    <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-destructive rounded-full"></span>
                </button>
                <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-sm font-medium text-primary-foreground">
                    א
                </div>
            </div>
        </header>
    )
}
