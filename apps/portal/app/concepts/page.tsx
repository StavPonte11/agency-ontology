import { Search, Filter, Plus, FileDown, MoreHorizontal } from "lucide-react"

export default function ConceptsPage() {
    const concepts = [
        { id: "C-101", name: "מערכת צי\"ד", type: "SYSTEM", domain: "C4I", status: "APPROVED", date: "2024-03-20", confidence: 0.95 },
        { id: "C-102", name: "פצמ\"ר 120 מ\"מ", type: "SYSTEM", domain: "Artillery", status: "APPROVED", date: "2024-03-19", confidence: 0.88 },
        { id: "C-103", name: "אמ\"ן", type: "UNIT", domain: "Intelligence", status: "APPROVED", date: "2024-03-18", confidence: 0.99 },
        { id: "C-104", name: "נוהל קרב", type: "PROCESS", domain: "Operations", status: "DRAFT", date: "2024-03-21", confidence: 0.72 },
        { id: "C-105", name: "קמ\"ן", type: "ROLE", domain: "Intelligence", status: "NEEDS_REVIEW", date: "2024-03-22", confidence: 0.65 },
    ]

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">לקסיקון ארגוני</h2>
                    <p className="text-muted-foreground mt-1">רשימת כל המושגים המנוהלים באונטולוגיה</p>
                </div>
                <div className="flex items-center gap-2">
                    <button className="flex items-center gap-2 px-4 py-2 bg-background border border-border shadow-sm rounded-md text-sm font-medium hover:bg-accent hover:text-accent-foreground">
                        <FileDown className="w-4 h-4" />
                        ייצוא
                    </button>
                    <button className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground shadow-sm rounded-md text-sm font-medium hover:bg-primary/90">
                        <Plus className="w-4 h-4" />
                        מושג חדש
                    </button>
                </div>
            </div>

            <div className="flex items-center justify-between border-b border-border pb-4">
                <div className="flex items-center gap-4 flex-1">
                    <div className="relative w-72">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="חיפוש מושג או מזהה..."
                            className="pl-4 pr-9 py-2 w-full text-sm bg-background border border-border rounded-md shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                    </div>
                    <button className="flex items-center gap-2 px-3 py-2 bg-background border border-border rounded-md shadow-sm text-sm hover:bg-accent font-medium text-muted-foreground">
                        <Filter className="w-4 h-4" />
                        סוג מושג
                    </button>
                    <button className="flex items-center gap-2 px-3 py-2 bg-background border border-border rounded-md shadow-sm text-sm hover:bg-accent font-medium text-muted-foreground">
                        <Filter className="w-4 h-4" />
                        סטטוס
                    </button>
                </div>
                <div className="text-sm text-muted-foreground font-medium">
                    סה"כ {concepts.length} תוצאות
                </div>
            </div>

            <div className="bg-card border border-border rounded-lg shadow-sm overflow-hidden">
                <table className="w-full text-sm text-right">
                    <thead className="bg-muted/50 border-b border-border text-muted-foreground">
                        <tr>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80 w-24">מזהה</th>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80">שם מושג</th>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80">סוג</th>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80">תחום (Domain)</th>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80">סטטוס</th>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80">רמת ביטחון חילוץ</th>
                            <th className="px-4 py-3 font-medium cursor-pointer hover:bg-muted/80">עודכן לאחרונה</th>
                            <th className="px-4 py-3 w-12"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {concepts.map((concept) => (
                            <tr key={concept.id} className="hover:bg-muted/30 transition-colors group">
                                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{concept.id}</td>
                                <td className="px-4 py-3 font-medium">{concept.name}</td>
                                <td className="px-4 py-3">
                                    <span className="px-2 py-1 rounded bg-secondary text-secondary-foreground text-xs font-semibold tracking-wide">
                                        {concept.type}
                                    </span>
                                </td>
                                <td className="px-4 py-3 text-muted-foreground">{concept.domain}</td>
                                <td className="px-4 py-3">
                                    <span className={`px-2 py-1 rounded text-xs font-semibold
                    ${concept.status === 'APPROVED' ? 'bg-emerald-500/10 text-emerald-500' :
                                            concept.status === 'NEEDS_REVIEW' ? 'bg-amber-500/10 text-amber-500' : 'bg-muted text-muted-foreground'}`
                                    }>
                                        {concept.status === 'APPROVED' ? 'מאושר' : concept.status === 'NEEDS_REVIEW' ? 'דורש סקירה' : 'טיוטה'}
                                    </span>
                                </td>
                                <td className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <div className="h-2 w-16 bg-muted rounded-full overflow-hidden">
                                            <div
                                                className={`h-full ${concept.confidence > 0.8 ? 'bg-primary' : concept.confidence > 0.6 ? 'bg-amber-500' : 'bg-destructive'}`}
                                                style={{ width: `${concept.confidence * 100}%` }}
                                            />
                                        </div>
                                        <span className="text-xs text-muted-foreground">{(concept.confidence * 100).toFixed(0)}%</span>
                                    </div>
                                </td>
                                <td className="px-4 py-3 text-muted-foreground text-xs">{concept.date}</td>
                                <td className="px-4 py-3">
                                    <button className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-accent text-muted-foreground hover:text-foreground">
                                        <MoreHorizontal className="w-4 h-4" />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
