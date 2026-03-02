"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
    AlertTriangle, Shield, Eye, Activity, TrendingUp,
    MapPin, GitBranch, Clock, CheckCircle, XCircle
} from "lucide-react"

// ── Types ─────────────────────────────────────────────────────────────────────

interface CoverageMetrics {
    total_locations: number
    locations_with_deps: number
    coverage_score: number
    target_coverage: number
    is_operational_ready: boolean
}

interface RecentQuery {
    trigger: string
    critical: number
    high: number
    monitor: number
    timestamp: string
}

// ── Impact Dashboard ──────────────────────────────────────────────────────────

export default function ImpactDashboard() {
    const [coverage, setCoverage] = useState<CoverageMetrics | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetch("/api/v1/impact/coverage")
            .then(r => r.json())
            .then(setCoverage)
            .catch(() => setCoverage(null))
            .finally(() => setLoading(false))
    }, [])

    const recentQueries: RecentQuery[] = [
        { trigger: "Location Alpha", critical: 3, high: 7, monitor: 14, timestamp: "לפני 12 דקות" },
        { trigger: "Location Beta", critical: 0, high: 2, monitor: 9, timestamp: "לפני שעה" },
        { trigger: "Location Gamma", critical: 5, high: 3, monitor: 8, timestamp: "לפני 3 שעות" },
    ]

    const tierColor = (tier: "CRITICAL" | "HIGH" | "MONITOR") =>
        ({ CRITICAL: "text-red-500", HIGH: "text-amber-500", MONITOR: "text-emerald-500" })[tier]

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">לוח ניתוח השפעה</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        Impact Analysis &amp; Consequence Mapping — Five-Layer Stack
                    </p>
                </div>
                <Link
                    href="/impact/query"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 text-black font-semibold text-sm hover:bg-amber-400 transition-colors"
                >
                    <AlertTriangle className="w-4 h-4" />
                    הפעל ניתוח חדש
                </Link>
            </div>

            {/* Stats row */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">

                {/* Coverage Gauge */}
                <Card className="border-amber-500/20 bg-amber-500/5">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">כיסוי נתוני תלות</CardTitle>
                        <TrendingUp className="h-4 w-4 text-amber-500" />
                    </CardHeader>
                    <CardContent>
                        {loading ? (
                            <div className="h-8 w-24 bg-muted animate-pulse rounded" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold text-amber-500">
                                    {coverage ? `${coverage.coverage_score}%` : "—"}
                                </div>
                                <div className="mt-2 w-full h-2 rounded-full bg-muted overflow-hidden">
                                    <div
                                        className="h-full rounded-full bg-amber-500 transition-all duration-700"
                                        style={{ width: `${coverage?.coverage_score ?? 0}%` }}
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    יעד: {coverage?.target_coverage ?? 85}% •{" "}
                                    {coverage?.is_operational_ready ? "✓ מוכן" : "⚠ לא מוכן"}
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Total Locations */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">מיקומים ממופים</CardTitle>
                        <MapPin className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {coverage ? `${coverage.locations_with_deps} / ${coverage.total_locations}` : "—"}
                        </div>
                        <p className="text-xs text-muted-foreground">עם גרף תלויות מלא</p>
                    </CardContent>
                </Card>

                {/* Critical bridges */}
                <Card className="border-red-500/20 bg-red-500/5">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">נקודות כשל יחיד</CardTitle>
                        <XCircle className="h-4 w-4 text-red-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-red-500">—</div>
                        <p className="text-xs text-muted-foreground">
                            ישויות ללא גיבוי עם תלויות קריטיות
                        </p>
                    </CardContent>
                </Card>

                {/* Engine status */}
                <Card className="border-emerald-500/20 bg-emerald-500/5">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">מנוע ניתוח</CardTitle>
                        <Activity className="h-4 w-4 text-emerald-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-500">פעיל</div>
                        <p className="text-xs text-muted-foreground">Five-Layer propagation ready</p>
                    </CardContent>
                </Card>
            </div>

            {/* Main grid */}
            <div className="grid gap-4 md:grid-cols-7">

                {/* Impact tier legend & quick-links */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle className="text-base">מבנה שכבות ההשפעה — Five-Layer Stack</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {[
                            { trigger: "1. טריגר", desc: "מיקום / ישות שנפגעה", color: "border-l-4 border-l-red-500 pl-3" },
                            { trigger: "2. תוצאות ישירות", desc: "מחלקות / נכסים המתארחים במיקום", color: "border-l-4 border-l-orange-500 pl-3" },
                            { trigger: "3. ישויות תפעוליות", desc: "פרויקטים / תהליכים שמפעילות המחלקות", color: "border-l-4 border-l-amber-500 pl-3" },
                            { trigger: "4. בעלי עניין", desc: "לקוחות / חובות שהפרויקטים משרתים", color: "border-l-4 border-l-yellow-500 pl-3" },
                            { trigger: "5. השלכות מערכתיות", desc: "הסלמה, הפרת SLA, אירוע היסטורי", color: "border-l-4 border-l-emerald-500 pl-3" },
                        ].map((layer, i) => (
                            <div key={i} className={`${layer.color} py-1`}>
                                <p className="text-sm font-medium">{layer.trigger}</p>
                                <p className="text-xs text-muted-foreground">{layer.desc}</p>
                            </div>
                        ))}

                        <div className="pt-2 flex gap-2">
                            <Link href="/impact/graph" className="text-xs px-3 py-1.5 rounded-md bg-muted hover:bg-accent transition-colors">
                                → גרף תלויות
                            </Link>
                            <Link href="/impact/locations" className="text-xs px-3 py-1.5 rounded-md bg-muted hover:bg-accent transition-colors">
                                → מפת מיקומים
                            </Link>
                            <Link href="/impact/sources" className="text-xs px-3 py-1.5 rounded-md bg-muted hover:bg-accent transition-colors">
                                → טעינת Excel
                            </Link>
                        </div>
                    </CardContent>
                </Card>

                {/* Recent propagation queries */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle className="text-base">שאילתות אחרונות</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {recentQueries.map((q, i) => (
                                <div key={i} className="flex items-start gap-3">
                                    <GitBranch className="w-4 h-4 mt-0.5 text-muted-foreground shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate">{q.trigger}</p>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <span className={`text-xs font-semibold ${tierColor("CRITICAL")}`}>קריטי: {q.critical}</span>
                                            <span className={`text-xs font-semibold ${tierColor("HIGH")}`}>גבוה: {q.high}</span>
                                            <span className={`text-xs ${tierColor("MONITOR")}`}>ניטור: {q.monitor}</span>
                                        </div>
                                    </div>
                                    <span className="text-xs text-muted-foreground shrink-0 flex items-center gap-1">
                                        <Clock className="w-3 h-3" />{q.timestamp}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Quick action cards */}
            <div className="grid gap-4 md:grid-cols-3">
                {[
                    {
                        title: "הפעל ניתוח השפעה",
                        desc: "בחר מיקום, הגדר סוג שיבוש, קבל דוח מצב מובנה",
                        href: "/impact/query",
                        icon: AlertTriangle,
                        color: "text-amber-500 bg-amber-500/10",
                    },
                    {
                        title: "עיין בגרף תלויות",
                        desc: "חקור ויזואלית את גרף הפרויקטים, הלקוחות וקשרי הגיבוי",
                        href: "/impact/graph",
                        icon: GitBranch,
                        color: "text-blue-500 bg-blue-500/10",
                    },
                    {
                        title: "טען קובץ Excel",
                        desc: "זיהוי סכמה, עיון בתצוגה מקדימה, קבל גרף תלויות מלא",
                        href: "/impact/sources",
                        icon: Shield,
                        color: "text-emerald-500 bg-emerald-500/10",
                    },
                ].map((card, i) => (
                    <Link key={i} href={card.href}>
                        <Card className="hover:border-primary/40 transition-colors cursor-pointer h-full">
                            <CardContent className="pt-6">
                                <div className={`w-10 h-10 rounded-lg ${card.color} flex items-center justify-center mb-4`}>
                                    <card.icon className="w-5 h-5" />
                                </div>
                                <h3 className="font-semibold text-sm mb-1">{card.title}</h3>
                                <p className="text-xs text-muted-foreground">{card.desc}</p>
                            </CardContent>
                        </Card>
                    </Link>
                ))}
            </div>
        </div>
    )
}
