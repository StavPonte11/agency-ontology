"use client"

import { useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Search, Zap, AlertTriangle, Shield, Eye, Clock, ChevronLeft } from "lucide-react"
import Link from "next/link"

interface ImpactedEntityRow {
    name: string
    entity_type: string
    operational_status: string
    impact_tier: "CRITICAL" | "HIGH" | "MONITOR"
    hop_distance: number
    mitigation_available: boolean
    propagation_path: string[]
}

interface PropagationResult {
    trigger_entity: string
    disruption_type: string
    critical_entities: ImpactedEntityRow[]
    high_entities: ImpactedEntityRow[]
    monitor_entities: ImpactedEntityRow[]
    total_affected: number
    coverage_confidence: number
    is_simulation: boolean
}

export default function ImpactQueryRunner() {
    const [entityName, setEntityName] = useState("")
    const [disruption, setDisruption] = useState("UNKNOWN")
    const [maxDepth, setMaxDepth] = useState(5)
    const [isScenario, setIsScenario] = useState(false)
    const [loading, setLoading] = useState(false)
    const [result, setResult] = useState<PropagationResult | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [activeTab, setActiveTab] = useState<"summary" | "critical" | "high" | "monitor">("summary")

    const runQuery = useCallback(async () => {
        if (!entityName.trim()) return
        setLoading(true)
        setError(null)
        setResult(null)
        try {
            const endpoint = isScenario ? "/api/v1/impact/scenario" : "/api/v1/impact/propagate"
            const res = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    entity_name: entityName,
                    disruption_type: disruption,
                    max_depth: maxDepth,
                    include_mitigation: true,
                    include_historical: true,
                    hypothetical: isScenario,
                }),
            })
            if (!res.ok) {
                const err = await res.json()
                setError(err.error || `HTTP ${res.status}`)
                return
            }
            setResult(await res.json())
            setActiveTab("summary")
        } catch (e: any) {
            setError(e.message || "שגיאת רשת")
        } finally {
            setLoading(false)
        }
    }, [entityName, disruption, maxDepth, isScenario])

    const tierBadge = (tier: string) => {
        if (tier === "CRITICAL") return "text-red-400 bg-red-500/15 border border-red-500/30"
        if (tier === "HIGH") return "text-amber-400 bg-amber-500/15 border border-amber-500/30"
        return "text-emerald-400 bg-emerald-500/15 border border-emerald-500/30"
    }

    const tierIcon = (tier: string) => {
        if (tier === "CRITICAL") return <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
        if (tier === "HIGH") return <Zap className="w-3.5 h-3.5 text-amber-400" />
        return <Eye className="w-3.5 h-3.5 text-emerald-400" />
    }

    const EntityTable = ({ entities }: { entities: ImpactedEntityRow[] }) => (
        <div className="space-y-2">
            {entities.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-6">אין ישויות בקטגוריה זו</p>
            )}
            {entities.map((e, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors">
                    <div className="mt-0.5">{tierIcon(e.impact_tier)}</div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm">{e.name}</span>
                            <span className="text-xs text-muted-foreground">[{e.entity_type}]</span>
                            {e.mitigation_available && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
                                    ✓ יש הפחתה
                                </span>
                            )}
                            {e.operational_status === "PLANNED" && (
                                <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-400">
                                    PLANNED — אין נזק פעיל
                                </span>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                            נתיב: {e.propagation_path?.slice(-3).join(" → ")} · עומק {e.hop_distance}
                        </p>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${tierBadge(e.impact_tier)}`}>
                        {e.impact_tier}
                    </span>
                </div>
            ))}
        </div>
    )

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center gap-3">
                <Link href="/impact" className="text-muted-foreground hover:text-foreground transition-colors">
                    <ChevronLeft className="w-5 h-5" />
                </Link>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">ניתוח השפעה</h2>
                    <p className="text-sm text-muted-foreground mt-1">Impact Query Runner — Five-Layer propagation engine</p>
                </div>
            </div>

            {/* Query form */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">הגדרת שאילתת השפעה</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid md:grid-cols-4 gap-4">
                        <div className="col-span-2">
                            <label className="text-xs text-muted-foreground mb-1 block">מיקום / ישות טריגר *</label>
                            <div className="relative">
                                <Search className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                                <input
                                    type="text"
                                    value={entityName}
                                    onChange={e => setEntityName(e.target.value)}
                                    onKeyDown={e => e.key === "Enter" && runQuery()}
                                    placeholder="לדוגמה: Location Alpha"
                                    className="w-full pr-9 pl-3 py-2 rounded-md bg-muted border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="text-xs text-muted-foreground mb-1 block">סוג שיבוש</label>
                            <select
                                value={disruption}
                                onChange={e => setDisruption(e.target.value)}
                                className="w-full px-3 py-2 rounded-md bg-muted border border-border text-sm"
                            >
                                <option value="UNKNOWN">לא ידוע</option>
                                <option value="PHYSICAL">פיזי</option>
                                <option value="POWER">חשמל</option>
                                <option value="ACCESS">גישה</option>
                                <option value="COMMUNICATIONS">תקשורת</option>
                                <option value="CYBER">סייבר</option>
                            </select>
                        </div>

                        <div>
                            <label className="text-xs text-muted-foreground mb-1 block">עומק מקסימלי ({maxDepth})</label>
                            <input
                                type="range"
                                min={1} max={10} step={1}
                                value={maxDepth}
                                onChange={e => setMaxDepth(Number(e.target.value))}
                                className="w-full mt-2"
                            />
                        </div>
                    </div>

                    <div className="flex items-center justify-between mt-4">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={isScenario}
                                onChange={e => setIsScenario(e.target.checked)}
                                className="rounded"
                            />
                            <span className="text-sm text-muted-foreground">
                                מצב סימולציה [SIMULATION] — אין שינוי במסד הנתונים
                            </span>
                        </label>

                        <button
                            onClick={runQuery}
                            disabled={!entityName.trim() || loading}
                            className="inline-flex items-center gap-2 px-6 py-2 rounded-lg bg-amber-500 text-black font-semibold text-sm hover:bg-amber-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {loading ? (
                                <span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                            ) : (
                                <Zap className="w-4 h-4" />
                            )}
                            {loading ? "מחשב..." : isScenario ? "הפעל סימולציה" : "הפעל ניתוח"}
                        </button>
                    </div>
                </CardContent>
            </Card>

            {/* Error */}
            {error && (
                <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                    ⚠ {error}
                </div>
            )}

            {/* Results */}
            {result && (
                <div className="space-y-4">
                    {/* Summary bar */}
                    <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50 border border-border">
                        {result.is_simulation && (
                            <span className="text-xs px-2 py-1 rounded bg-blue-500/20 text-blue-400 font-mono">
                                [SIMULATION]
                            </span>
                        )}
                        <div className="flex-1 font-semibold text-sm">{result.trigger_entity}</div>
                        <div className="flex items-center gap-4">
                            <span className="flex items-center gap-1 text-red-400 text-sm font-semibold">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                {result.critical_entities.length} קריטי
                            </span>
                            <span className="flex items-center gap-1 text-amber-400 text-sm font-semibold">
                                <Zap className="w-3.5 h-3.5" />
                                {result.high_entities.length} גבוה
                            </span>
                            <span className="flex items-center gap-1 text-emerald-400 text-sm">
                                <Eye className="w-3.5 h-3.5" />
                                {result.monitor_entities.length} ניטור
                            </span>
                            <span className="text-xs text-muted-foreground">
                                · כיסוי {(result.coverage_confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div className="flex gap-1 p-1 bg-muted rounded-lg w-fit">
                        {(["summary", "critical", "high", "monitor"] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === tab ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                            >
                                {tab === "summary" ? "סיכום" : tab === "critical" ? `קריטי (${result.critical_entities.length})` : tab === "high" ? `גבוה (${result.high_entities.length})` : `ניטור (${result.monitor_entities.length})`}
                            </button>
                        ))}
                    </div>

                    {/* Tab content */}
                    <Card>
                        <CardContent className="pt-4">
                            {activeTab === "summary" && (
                                <div className="space-y-4">
                                    <div className="grid grid-cols-3 gap-4">
                                        {[
                                            { label: "קריטי — פעולה מיידית", count: result.critical_entities.length, color: "text-red-400", icon: AlertTriangle },
                                            { label: "גבוה — רגיש לזמן", count: result.high_entities.length, color: "text-amber-400", icon: Zap },
                                            { label: "ניטור — ללא פעולה מיידית", count: result.monitor_entities.length, color: "text-emerald-400", icon: Eye },
                                        ].map((s, i) => (
                                            <div key={i} className="text-center p-4 rounded-lg bg-muted/50">
                                                <s.icon className={`w-6 h-6 mx-auto mb-2 ${s.color}`} />
                                                <p className={`text-2xl font-bold ${s.color}`}>{s.count}</p>
                                                <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                                            </div>
                                        ))}
                                    </div>
                                    <p className="text-xs text-muted-foreground text-center">
                                        סה"כ {result.total_affected} ישויות מושפעות · סוג שיבוש: {result.disruption_type}
                                    </p>
                                    {result.critical_entities.length > 0 && (
                                        <div>
                                            <p className="text-sm font-semibold mb-2 text-red-400">⚠ ישויות קריטיות — פעולה מיידית</p>
                                            <EntityTable entities={result.critical_entities.slice(0, 3)} />
                                            {result.critical_entities.length > 3 && (
                                                <button onClick={() => setActiveTab("critical")} className="text-xs text-primary mt-2">
                                                    הצג את כל {result.critical_entities.length} →
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                            {activeTab === "critical" && <EntityTable entities={result.critical_entities} />}
                            {activeTab === "high" && <EntityTable entities={result.high_entities} />}
                            {activeTab === "monitor" && <EntityTable entities={result.monitor_entities} />}
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    )
}
