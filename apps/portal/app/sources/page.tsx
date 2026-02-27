import { Database, Plus, RefreshCw, FileText, Globe, Settings, ExternalLink } from "lucide-react"

export default function SourcesPage() {
    const sources = [
        {
            id: "SRC-001",
            name: "OpenMetadata (קטלוג נתונים)",
            type: "OPENMETADATA",
            status: "ACTIVE",
            lastSync: "לפני שעתיים",
            documents: 4520,
            icon: Database,
            basePath: "http://openmetadata:8585"
        },
        {
            id: "SRC-002",
            name: "פקודות מטכ\"ל (PDF)",
            type: "PDF_DIR",
            status: "ACTIVE",
            lastSync: "אתמול, 14:30",
            documents: 312,
            icon: FileText,
            basePath: "/data/docs/pkalim"
        },
        {
            id: "SRC-003",
            name: "תו\"ל יבשה (PDF)",
            type: "PDF_DIR",
            status: "ERROR",
            lastSync: "נכשל - שגיאת רשת",
            documents: 84,
            icon: FileText,
            basePath: "/data/docs/toral"
        },
        {
            id: "SRC-004",
            name: "פורטל הארגון (Confluence)",
            type: "WEB_CRAWLER",
            status: "PAUSED",
            lastSync: "לפני שבוע",
            documents: 12050,
            icon: Globe,
            basePath: "https://confluence.idf.local"
        }
    ]

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">מקורות מידע (Sources)</h2>
                    <p className="text-muted-foreground mt-1">ניהול קונקטורים המזינים את תהליך החילוץ</p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground shadow-sm rounded-md text-sm font-medium hover:bg-primary/90">
                    <Plus className="w-4 h-4" />
                    חיבור מקור חדש
                </button>
            </div>

            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                {sources.map((source) => (
                    <div key={source.id} className="bg-card border border-border rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow relative overflow-hidden group">
                        <div className="absolute top-0 right-0 w-1.5 h-full"
                            style={{ backgroundColor: source.status === 'ACTIVE' ? 'var(--emerald-500, #10b981)' : source.status === 'ERROR' ? 'var(--destructive, #ef4444)' : 'var(--muted-foreground, #71717a)' }}>
                        </div>

                        <div className="flex justify-between items-start mb-4">
                            <div className="w-10 h-10 rounded-md bg-secondary flex items-center justify-center text-secondary-foreground">
                                <source.icon className="w-5 h-5" />
                            </div>
                            <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase
                ${source.status === 'ACTIVE' ? 'bg-emerald-500/10 text-emerald-500' :
                                    source.status === 'ERROR' ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground'}`
                            }>
                                {source.status === 'ACTIVE' ? 'פעיל' : source.status === 'ERROR' ? 'שגיאה' : 'מושהה'}
                            </span>
                        </div>

                        <h3 className="text-lg font-bold mb-1 truncate" title={source.name}>{source.name}</h3>

                        <div className="text-sm font-mono text-muted-foreground mb-4 truncate flex items-center gap-1" title={source.basePath}>
                            <span dir="ltr">{source.basePath}</span>
                            {source.type !== 'PDF_DIR' && <ExternalLink className="w-3 h-3 opacity-50" />}
                        </div>

                        <div className="grid grid-cols-2 gap-4 py-4 border-t border-border/50 text-sm">
                            <div>
                                <div className="text-muted-foreground text-xs mb-1">סנכרון אחרון</div>
                                <div className="font-medium text-foreground">{source.lastSync}</div>
                            </div>
                            <div>
                                <div className="text-muted-foreground text-xs mb-1">מסמכים נסרקו</div>
                                <div className="font-medium text-foreground">{source.documents.toLocaleString()}</div>
                            </div>
                        </div>

                        <div className="mt-4 flex gap-2 w-full">
                            <button
                                className="flex-1 flex items-center justify-center gap-2 py-2 bg-secondary text-secondary-foreground rounded-md text-xs font-medium hover:bg-secondary/80 transition-colors"
                                disabled={source.status === 'PAUSED'}
                            >
                                <RefreshCw className={`w-3 h-3 ${source.status === 'ACTIVE' ? 'group-hover:animate-spin' : ''}`} />
                                סנכרן כעת
                            </button>
                            <button className="px-3 py-2 bg-background border border-border text-muted-foreground rounded-md hover:bg-accent hover:text-foreground transition-colors">
                                <Settings className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                ))}

                {/* Add New Source Card */}
                <button className="bg-muted/20 border-2 border-dashed border-border rounded-lg shadow-sm p-6 hover:bg-muted/40 transition-colors flex flex-col items-center justify-center gap-4 text-muted-foreground hover:text-foreground min-h-[280px]">
                    <div className="w-12 h-12 rounded-full bg-background border flex items-center justify-center">
                        <Plus className="w-6 h-6" />
                    </div>
                    <div className="text-center">
                        <h3 className="text-lg font-bold">הוסף מקור</h3>
                        <p className="text-sm mt-1">חיבור ל-DB, קבצים, או API</p>
                    </div>
                </button>
            </div>
        </div>
    )
}
