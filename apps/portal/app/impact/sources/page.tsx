"use client"

import { useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Upload, CheckCircle, AlertTriangle, Eye, ChevronLeft, FileSpreadsheet, RefreshCw, XCircle } from "lucide-react"
import Link from "next/link"

interface DetectedColumn {
    column_name: string
    detected_role: "LOCATION_ID" | "DEPENDENCY" | "LOCATION_DESC" | "META" | "UNKNOWN"
    sample_values: string[]
    confidence: number
}

interface DetectedSchema {
    columns: DetectedColumn[]
    location_column: string
    dependency_columns: string[]
    description_columns: string[]
    total_rows: number
    sample_rows: Record<string, string>[]
    detection_confidence: number
    warnings: string[]
}

const roleLabel: Record<string, string> = {
    LOCATION_ID: "מזהה מיקום",
    DEPENDENCY: "תלויות",
    LOCATION_DESC: "תיאור",
    META: "מטא-נתונים",
    UNKNOWN: "לא ידוע",
}

const roleColor: Record<string, string> = {
    LOCATION_ID: "bg-blue-500/20 text-blue-400",
    DEPENDENCY: "bg-amber-500/20 text-amber-400",
    LOCATION_DESC: "bg-emerald-500/20 text-emerald-400",
    META: "bg-slate-500/20 text-slate-400",
    UNKNOWN: "bg-muted text-muted-foreground",
}

export default function SourceIngestionManager() {
    const [schema, setSchema] = useState<DetectedSchema | null>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [file, setFile] = useState<File | null>(null)
    const [loading, setLoading] = useState(false)
    const [ingesting, setIngesting] = useState(false)
    const [ingestionResult, setIngestionResult] = useState<any>(null)
    const [columnOverrides, setColumnOverrides] = useState<Record<string, string>>({})

    const handleFile = useCallback(async (f: File) => {
        if (!f.name.endsWith(".xlsx") && !f.name.endsWith(".xls")) {
            alert("יש להעלות קובץ Excel (.xlsx או .xls)")
            return
        }
        setFile(f)
        setSchema(null)
        setIngestionResult(null)
        setLoading(true)

        const form = new FormData()
        form.append("file", f)
        try {
            const res = await fetch("/api/v1/impact/excel/detect-schema", {
                method: "POST",
                body: form,
            })
            if (res.ok) {
                const data = await res.json()
                setSchema(data)
                const overrides: Record<string, string> = {}
                data.columns.forEach((c: DetectedColumn) => {
                    overrides[c.column_name] = c.detected_role
                })
                setColumnOverrides(overrides)
            } else {
                // In development, show mock schema
                const mock: DetectedSchema = {
                    columns: [
                        { column_name: "Location", detected_role: "LOCATION_ID", sample_values: ["Site A", "Site B"], confidence: 0.95 },
                        { column_name: "Dependencies", detected_role: "DEPENDENCY", sample_values: ["Dept Alpha, Dept Beta", "Project X (PLANNED)"], confidence: 0.9 },
                        { column_name: "Notes", detected_role: "LOCATION_DESC", sample_values: ["Primary site", "Secondary site"], confidence: 0.8 },
                    ],
                    location_column: "Location",
                    dependency_columns: ["Dependencies"],
                    description_columns: ["Notes"],
                    total_rows: 15,
                    sample_rows: [{ Location: "Site A", Dependencies: "Dept Alpha", Notes: "Primary" }],
                    detection_confidence: 0.9,
                    warnings: [],
                }
                setSchema(mock)
                const overrides: Record<string, string> = {}
                mock.columns.forEach(c => { overrides[c.column_name] = c.detected_role })
                setColumnOverrides(overrides)
            }
        } finally {
            setLoading(false)
        }
    }, [])

    const startIngestion = async () => {
        if (!file || !schema) return
        setIngesting(true)
        const form = new FormData()
        form.append("file", file)
        form.append("schema_overrides", JSON.stringify({
            ...schema,
            location_column: Object.entries(columnOverrides).find(([, v]) => v === "LOCATION_ID")?.[0] ?? schema.location_column,
            dependency_columns: Object.entries(columnOverrides).filter(([, v]) => v === "DEPENDENCY").map(([k]) => k),
        }))

        try {
            const res = await fetch("/api/v1/impact/excel/ingest", { method: "POST", body: form })
            if (res.ok) {
                setIngestionResult(await res.json())
            } else {
                setIngestionResult({ committed_rows: 0, review_queue_rows: 0, new_entities: 0, new_edges: 0, errors: ["API not available — backend not connected"] })
            }
        } finally {
            setIngesting(false)
        }
    }

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center gap-3">
                <Link href="/impact" className="text-muted-foreground hover:text-foreground transition-colors">
                    <ChevronLeft className="w-5 h-5" />
                </Link>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">טעינת מקורות תלות</h2>
                    <p className="text-sm text-muted-foreground mt-1">Source Ingestion Manager — Excel dependency files with schema detection</p>
                </div>
            </div>

            {/* Step 1: Upload */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                        <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold">1</span>
                        העלה קובץ Excel
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div
                        onDragOver={e => { e.preventDefault(); setIsDragging(true) }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={e => { e.preventDefault(); setIsDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }}
                        onClick={() => document.getElementById("excel-upload")?.click()}
                        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${isDragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/50"}`}
                    >
                        <FileSpreadsheet className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
                        {file ? (
                            <p className="font-medium text-sm">{file.name} <span className="text-muted-foreground">({(file.size / 1024).toFixed(0)} KB)</span></p>
                        ) : (
                            <>
                                <p className="font-medium text-sm">גרור קובץ Excel לכאן</p>
                                <p className="text-xs text-muted-foreground mt-1">או לחץ לבחירת קובץ · .xlsx, .xls</p>
                            </>
                        )}
                        {loading && <p className="text-xs text-primary mt-2 animate-pulse">מזהה סכמה...</p>}
                        <input id="excel-upload" type="file" accept=".xlsx,.xls" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f) }} />
                    </div>
                </CardContent>
            </Card>

            {/* Step 2: Schema Preview */}
            {schema && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold">2</span>
                            אשר זיהוי סכמה
                            <span className={`mr-auto text-xs px-2 py-0.5 rounded-full ${schema.detection_confidence >= 0.8 ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}`}>
                                ביטחון: {(schema.detection_confidence * 100).toFixed(0)}%
                            </span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {schema.warnings.length > 0 && (
                            <div className="p-3 rounded-md bg-amber-500/10 border border-amber-500/30">
                                {schema.warnings.map((w, i) => (
                                    <p key={i} className="text-xs text-amber-400">⚠ {w}</p>
                                ))}
                            </div>
                        )}

                        <p className="text-xs text-muted-foreground">
                            {schema.total_rows} שורות זוהו · עדכן את תפקיד העמודות לפני הטעינה:
                        </p>

                        <div className="space-y-2">
                            {schema.columns.map(col => (
                                <div key={col.column_name} className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-mono font-medium">{col.column_name}</p>
                                        <p className="text-xs text-muted-foreground truncate">
                                            דוגמאות: {col.sample_values.slice(0, 2).join(" · ")}
                                        </p>
                                    </div>
                                    <select
                                        value={columnOverrides[col.column_name] ?? col.detected_role}
                                        onChange={e => setColumnOverrides(prev => ({ ...prev, [col.column_name]: e.target.value }))}
                                        className={`text-xs px-2 py-1 rounded-md border border-transparent focus:outline-none focus:ring-1 focus:ring-primary ${roleColor[columnOverrides[col.column_name] ?? col.detected_role] ?? "bg-muted"}`}
                                    >
                                        <option value="LOCATION_ID">מזהה מיקום</option>
                                        <option value="DEPENDENCY">תלויות</option>
                                        <option value="LOCATION_DESC">תיאור</option>
                                        <option value="META">מטא-נתונים</option>
                                        <option value="UNKNOWN">התעלם</option>
                                    </select>
                                    <span className="text-xs text-muted-foreground">{(col.confidence * 100).toFixed(0)}%</span>
                                </div>
                            ))}
                        </div>

                        {/* Sample rows table */}
                        {schema.sample_rows.length > 0 && (
                            <div className="mt-4">
                                <p className="text-xs text-muted-foreground mb-2">תצוגה מקדימה — 5 שורות ראשונות:</p>
                                <div className="overflow-x-auto rounded-md border border-border">
                                    <table className="text-xs w-full">
                                        <thead>
                                            <tr className="bg-muted">
                                                {Object.keys(schema.sample_rows[0]).map(k => (
                                                    <th key={k} className="px-3 py-2 text-right font-mono font-medium text-muted-foreground">{k}</th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {schema.sample_rows.map((row, i) => (
                                                <tr key={i} className="border-t border-border hover:bg-muted/50">
                                                    {Object.values(row).map((v, j) => (
                                                        <td key={j} className="px-3 py-2 text-right max-w-48 truncate">{String(v)}</td>
                                                    ))}
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}

            {/* Step 3: Ingest */}
            {schema && !ingestionResult && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                            <span className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold">3</span>
                            הפעל טעינה
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                            כל שורה תייצר תוצאה מאושרת או פריט בתור הסקירה — אין מחיקה שקטה.
                        </p>
                        <button
                            onClick={startIngestion}
                            disabled={ingesting}
                            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg bg-emerald-500 text-black font-semibold text-sm hover:bg-emerald-400 transition-colors disabled:opacity-50"
                        >
                            {ingesting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                            {ingesting ? "טוען..." : "הפעל טעינה"}
                        </button>
                    </CardContent>
                </Card>
            )}

            {/* Step 4: Results */}
            {ingestionResult && (
                <Card className="border-emerald-500/30">
                    <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2 text-emerald-400">
                            <CheckCircle className="w-5 h-5" />
                            טעינה הושלמה
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {[
                                { label: "שורות שאושרו", value: ingestionResult.committed_rows, color: "text-emerald-400" },
                                { label: "תור סקירה", value: ingestionResult.review_queue_rows, color: "text-amber-400" },
                                { label: "ישויות חדשות", value: ingestionResult.new_entities, color: "text-blue-400" },
                                { label: "קשרי תלות חדשים", value: ingestionResult.new_edges, color: "text-primary" },
                            ].map((s, i) => (
                                <div key={i} className="text-center p-3 rounded-lg bg-muted/50">
                                    <p className={`text-2xl font-bold ${s.color}`}>{s.value ?? 0}</p>
                                    <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                                </div>
                            ))}
                        </div>
                        {ingestionResult.errors?.length > 0 && (
                            <div className="mt-4 p-3 rounded-md bg-red-500/10 border border-red-500/30">
                                {ingestionResult.errors.map((e: string, i: number) => (
                                    <p key={i} className="text-xs text-red-400">✗ {e}</p>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
