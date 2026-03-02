"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Search, MapPin, AlertTriangle, ChevronLeft, Activity } from "lucide-react"
import Link from "next/link"

interface Location {
    name: string
    criticality: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    operationalStatus: "ACTIVE" | "PLANNED" | "SUSPENDED" | "CLOSED"
    downstreamCount: number
    isSPOF: boolean
    locationsWithDeps: number
    totalLocations: number
    region?: string
}

const MOCK_LOCATIONS: Location[] = [
    { name: "Location Alpha", criticality: "CRITICAL", operationalStatus: "ACTIVE", downstreamCount: 47, isSPOF: true, locationsWithDeps: 3, totalLocations: 3 },
    { name: "Location Beta", criticality: "HIGH", operationalStatus: "ACTIVE", downstreamCount: 23, isSPOF: false, locationsWithDeps: 2, totalLocations: 2 },
    { name: "Location Gamma", criticality: "MEDIUM", operationalStatus: "ACTIVE", downstreamCount: 11, isSPOF: false, locationsWithDeps: 1, totalLocations: 1 },
    { name: "Location Delta", criticality: "HIGH", operationalStatus: "PLANNED", downstreamCount: 0, isSPOF: false, locationsWithDeps: 0, totalLocations: 0 },
]

const criticalityBadge = (c: string) => {
    const map: Record<string, string> = {
        CRITICAL: "bg-red-500/20 text-red-400 border-red-500/30",
        HIGH: "bg-amber-500/20 text-amber-400 border-amber-500/30",
        MEDIUM: "bg-blue-500/20 text-blue-400 border-blue-500/30",
        LOW: "bg-slate-500/20 text-slate-400 border-slate-500/30",
    }
    return map[c] ?? "bg-muted text-muted-foreground"
}

const statusBadge = (s: string) => {
    const map: Record<string, string> = {
        ACTIVE: "bg-emerald-500/20 text-emerald-400",
        PLANNED: "bg-blue-500/20 text-blue-400",
        SUSPENDED: "bg-orange-500/20 text-orange-400",
        CLOSED: "bg-slate-500/20 text-slate-400",
    }
    return map[s] ?? "bg-muted text-muted-foreground"
}

export default function LocationExplorer() {
    const [search, setSearch] = useState("")
    const [critFilter, setCritFilter] = useState<string>("ALL")
    const [statusFilter, setStatusFilter] = useState<string>("ALL")

    const filtered = MOCK_LOCATIONS.filter(loc => {
        const matchSearch = loc.name.toLowerCase().includes(search.toLowerCase())
        const matchCrit = critFilter === "ALL" || loc.criticality === critFilter
        const matchStatus = statusFilter === "ALL" || loc.operationalStatus === statusFilter
        return matchSearch && matchCrit && matchStatus
    })

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center gap-3">
                <Link href="/impact" className="text-muted-foreground hover:text-foreground transition-colors">
                    <ChevronLeft className="w-5 h-5" />
                </Link>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">מפת מיקומים לוגיסטיים</h2>
                    <p className="text-sm text-muted-foreground mt-1">Location Explorer — פרטי תלות וכיסוי נתונים</p>
                </div>
            </div>

            {/* Filters */}
            <Card>
                <CardContent className="pt-4">
                    <div className="flex flex-col md:flex-row gap-3">
                        <div className="relative flex-1">
                            <Search className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                            <input
                                type="text"
                                placeholder="חיפוש מיקום..."
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                className="w-full pr-9 pl-3 py-2 rounded-md bg-muted border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                        </div>
                        <select
                            value={critFilter}
                            onChange={e => setCritFilter(e.target.value)}
                            className="px-3 py-2 rounded-md bg-muted border border-border text-sm focus:outline-none"
                        >
                            <option value="ALL">כל הקריטיות</option>
                            <option value="CRITICAL">קריטי</option>
                            <option value="HIGH">גבוה</option>
                            <option value="MEDIUM">בינוני</option>
                        </select>
                        <select
                            value={statusFilter}
                            onChange={e => setStatusFilter(e.target.value)}
                            className="px-3 py-2 rounded-md bg-muted border border-border text-sm focus:outline-none"
                        >
                            <option value="ALL">כל הסטטוסים</option>
                            <option value="ACTIVE">פעיל</option>
                            <option value="PLANNED">מתוכנן</option>
                            <option value="SUSPENDED">מושהה</option>
                        </select>
                    </div>
                </CardContent>
            </Card>

            {/* Location cards */}
            <div className="grid gap-4 md:grid-cols-2">
                {filtered.map(loc => (
                    <Card key={loc.name} className="hover:border-primary/40 transition-colors">
                        <CardContent className="pt-5">
                            <div className="flex items-start justify-between gap-2 mb-3">
                                <div className="flex items-center gap-2">
                                    <MapPin className="w-4 h-4 text-muted-foreground shrink-0" />
                                    <span className="font-semibold text-sm">{loc.name}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className={`text-xs px-2 py-0.5 rounded-full border ${criticalityBadge(loc.criticality)}`}>
                                        {loc.criticality}
                                    </span>
                                    <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadge(loc.operationalStatus)}`}>
                                        {loc.operationalStatus}
                                    </span>
                                    {loc.isSPOF && (
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400">
                                            ⚠ SPOF
                                        </span>
                                    )}
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2 mb-4">
                                <div className="text-center p-2 rounded-md bg-muted/50">
                                    <p className="text-xs text-muted-foreground">ישויות תלויות</p>
                                    <p className="text-xl font-bold">{loc.downstreamCount}</p>
                                </div>
                                <div className="text-center p-2 rounded-md bg-muted/50">
                                    <p className="text-xs text-muted-foreground">סטטוס תפעולי</p>
                                    <div className={`text-sm font-semibold mt-1 ${loc.operationalStatus === "ACTIVE" ? "text-emerald-400" : "text-amber-400"}`}>
                                        {loc.operationalStatus === "ACTIVE" ? "✓ פעיל" : "⏳ לא פעיל"}
                                    </div>
                                </div>
                            </div>

                            <div className="flex gap-2">
                                <Link
                                    href={`/impact/graph?location=${encodeURIComponent(loc.name)}`}
                                    className="flex-1 text-xs text-center py-1.5 rounded-md bg-muted hover:bg-accent transition-colors"
                                >
                                    → גרף תלויות
                                </Link>
                                <Link
                                    href={`/impact/query?entity=${encodeURIComponent(loc.name)}`}
                                    className="flex-1 text-xs text-center py-1.5 rounded-md bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
                                >
                                    ⚡ ניתוח השפעה
                                </Link>
                            </div>
                        </CardContent>
                    </Card>
                ))}

                {filtered.length === 0 && (
                    <div className="col-span-2 text-center py-12 text-muted-foreground text-sm">
                        לא נמצאו מיקומים התואמים לסינון. טען נתוני תלות ב
                        <Link href="/impact/sources" className="text-primary underline mr-1">טעינת Excel</Link>.
                    </div>
                )}
            </div>
        </div>
    )
}
