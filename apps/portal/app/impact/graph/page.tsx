"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Search, ChevronLeft, GitBranch, AlertTriangle, Filter, Info } from "lucide-react"
import Link from "next/link"

// ── Note: In production this integrates with ReactFlow ─────────────────────────
// This page provides a static graph explorer that sends reverse-query API calls.
// The full ReactFlow integration (node-drag, zoom, cluster) is a future iteration
// planned in Phase 6.1 of the spec.

interface GraphNode {
    id: string
    name: string
    entityType: string
    operationalStatus: string
    criticalityLevel: string
    downstreamCount: number
    x: number
    y: number
}

interface GraphEdge {
    id: string
    from: string
    to: string
    edgeType: string
    criticality: string
    mitigationAvailable: boolean
}

const MOCK_NODES: GraphNode[] = [
    { id: "loc-l", name: "Location L", entityType: "LOCATION", operationalStatus: "ACTIVE", criticalityLevel: "CRITICAL", downstreamCount: 8, x: 100, y: 200 },
    { id: "dept-x", name: "Department X", entityType: "DEPARTMENT", operationalStatus: "ACTIVE", criticalityLevel: "HIGH", downstreamCount: 7, x: 350, y: 200 },
    { id: "proj-a", name: "Project A", entityType: "PROJECT", operationalStatus: "ACTIVE", criticalityLevel: "HIGH", downstreamCount: 3, x: 620, y: 80 },
    { id: "proj-b", name: "Project B", entityType: "PROJECT", operationalStatus: "PLANNED", criticalityLevel: "HIGH", downstreamCount: 1, x: 620, y: 200 },
    { id: "proj-c", name: "Project C", entityType: "PROJECT", operationalStatus: "ACTIVE", criticalityLevel: "CRITICAL", downstreamCount: 1, x: 620, y: 320 },
]

const MOCK_EDGES: GraphEdge[] = [
    { id: "e1", from: "loc-l", to: "dept-x", edgeType: "HOSTS", criticality: "CRITICAL", mitigationAvailable: false },
    { id: "e2", from: "dept-x", to: "proj-a", edgeType: "RUNS", criticality: "HIGH", mitigationAvailable: false },
    { id: "e3", from: "dept-x", to: "proj-b", edgeType: "RUNS", criticality: "HIGH", mitigationAvailable: false },
    { id: "e4", from: "dept-x", to: "proj-c", edgeType: "RUNS", criticality: "CRITICAL", mitigationAvailable: false },
]

const nodeColor = (n: GraphNode) => {
    if (n.operationalStatus === "PLANNED") return "#3b82f6"
    if (n.criticalityLevel === "CRITICAL") return "#ef4444"
    if (n.criticalityLevel === "HIGH") return "#f59e0b"
    return "#6b7280"
}

const edgeColor = (e: GraphEdge) => {
    if (e.criticality === "CRITICAL") return "#ef4444"
    if (e.criticality === "HIGH") return "#f59e0b"
    return "#6b7280"
}

export default function DependencyGraph() {
    const [search, setSearch] = useState("")
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
    const [showMonitor, setShowMonitor] = useState(true)
    const [reverseResult, setReverseResult] = useState<any>(null)

    const filteredNodes = MOCK_NODES.filter(n => {
        if (!showMonitor && n.operationalStatus === "PLANNED") return false
        if (search) return n.name.toLowerCase().includes(search.toLowerCase())
        return true
    })

    const visibleIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = MOCK_EDGES.filter(e => visibleIds.has(e.from) && visibleIds.has(e.to))

    const handleNodeClick = async (node: GraphNode) => {
        setSelectedNode(node)
        try {
            const res = await fetch("/api/v1/impact/reverse", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ entity_name: node.name, max_depth: 3 }),
            })
            if (res.ok) setReverseResult(await res.json())
        } catch {
            setReverseResult(null)
        }
    }

    const svgWidth = 820
    const svgHeight = 400

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center gap-3">
                <Link href="/impact" className="text-muted-foreground hover:text-foreground transition-colors">
                    <ChevronLeft className="w-5 h-5" />
                </Link>
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">גרף תלויות</h2>
                    <p className="text-sm text-muted-foreground mt-1">Dependency Graph — Five-Layer Stack visualisation (ReactFlow integration planned)</p>
                </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-3">
                <div className="relative">
                    <Search className="absolute right-3 top-2.5 w-4 h-4 text-muted-foreground" />
                    <input
                        type="text"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="חפש ישות..."
                        className="pr-9 pl-3 py-2 rounded-md bg-muted border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                </div>
                <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                    <input type="checkbox" checked={showMonitor} onChange={e => setShowMonitor(e.target.checked)} />
                    הצג ישויות PLANNED
                </label>
                <Link
                    href="/impact/query"
                    className="mr-auto inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 text-black font-semibold text-sm hover:bg-amber-400 transition-colors text-sm"
                >
                    <AlertTriangle className="w-4 h-4" />
                    הפעל ניתוח השפעה
                </Link>
            </div>

            {/* Graph + detail panel */}
            <div className="grid grid-cols-12 gap-4">
                {/* SVG graph */}
                <Card className="col-span-8">
                    <CardHeader>
                        <CardTitle className="text-sm">
                            Part 1.4 — Canonical Example Graph
                            <span className="text-xs font-normal text-muted-foreground mr-2">(אינטגרציית ReactFlow מלאה מתוכננת)</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <svg
                            width={svgWidth}
                            height={svgHeight}
                            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                            className="w-full overflow-visible"
                        >
                            {/* Edges */}
                            {filteredEdges.map(edge => {
                                const fromNode = MOCK_NODES.find(n => n.id === edge.from)
                                const toNode = MOCK_NODES.find(n => n.id === edge.to)
                                if (!fromNode || !toNode) return null
                                const x1 = fromNode.x + 60, y1 = fromNode.y + 18
                                const x2 = toNode.x, y2 = toNode.y + 18
                                const mx = (x1 + x2) / 2
                                return (
                                    <g key={edge.id}>
                                        <path
                                            d={`M${x1},${y1} Q${mx},${y1} ${x2},${y2}`}
                                            fill="none"
                                            stroke={edgeColor(edge)}
                                            strokeWidth={edge.criticality === "CRITICAL" ? 2.5 : 1.5}
                                            strokeOpacity={0.7}
                                            strokeDasharray={edge.mitigationAvailable ? "6 3" : undefined}
                                        />
                                        <text x={mx} y={(y1 + y2) / 2 - 4} textAnchor="middle" fontSize="9" fill={edgeColor(edge)} opacity={0.7}>
                                            {edge.edgeType}
                                        </text>
                                    </g>
                                )
                            })}

                            {/* Nodes */}
                            {filteredNodes.map(node => {
                                const isSelected = selectedNode?.id === node.id
                                const isPlanned = node.operationalStatus === "PLANNED"
                                return (
                                    <g
                                        key={node.id}
                                        transform={`translate(${node.x}, ${node.y})`}
                                        className="cursor-pointer"
                                        onClick={() => handleNodeClick(node)}
                                    >
                                        <rect
                                            width={120} height={36}
                                            rx={6}
                                            fill={nodeColor(node)}
                                            fillOpacity={isPlanned ? 0.3 : 0.15}
                                            stroke={nodeColor(node)}
                                            strokeWidth={isSelected ? 2.5 : 1}
                                            strokeDasharray={isPlanned ? "5 3" : undefined}
                                        />
                                        <text x={60} y={14} textAnchor="middle" fontSize="9" fill="currentColor" opacity={0.6}>
                                            [{node.entityType}]
                                        </text>
                                        <text x={60} y={28} textAnchor="middle" fontSize="11" fill={nodeColor(node)} fontWeight={isSelected ? "bold" : "normal"}>
                                            {node.name.length > 14 ? node.name.slice(0, 14) + "…" : node.name}
                                        </text>
                                        {isPlanned && (
                                            <text x={60} y={46} textAnchor="middle" fontSize="9" fill="#3b82f6">
                                                PLANNED
                                            </text>
                                        )}
                                    </g>
                                )
                            })}
                        </svg>

                        {/* Legend */}
                        <div className="flex items-center gap-6 mt-4 text-xs text-muted-foreground">
                            {[
                                { color: "#ef4444", label: "קריטי" },
                                { color: "#f59e0b", label: "גבוה" },
                                { color: "#3b82f6", label: "PLANNED" },
                            ].map((l, i) => (
                                <span key={i} className="flex items-center gap-1">
                                    <span className="w-3 h-3 rounded-sm" style={{ background: l.color, opacity: 0.7 }} />
                                    {l.label}
                                </span>
                            ))}
                            <span className="flex items-center gap-1">
                                <span className="w-6 h-px border-t-2 border-dashed border-muted-foreground" />
                                עם הפחתה
                            </span>
                        </div>
                    </CardContent>
                </Card>

                {/* Detail panel */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle className="text-sm">
                            {selectedNode ? selectedNode.name : "בחר ישות בגרף"}
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {!selectedNode ? (
                            <p className="text-sm text-muted-foreground">לחץ על ישות בגרף לצפייה בפרטים ושאילתת תלות הפוכה.</p>
                        ) : (
                            <div className="space-y-3">
                                <div className="space-y-1.5 text-xs">
                                    {[
                                        { label: "סוג", value: selectedNode.entityType },
                                        { label: "סטטוס", value: selectedNode.operationalStatus },
                                        { label: "קריטיות", value: selectedNode.criticalityLevel },
                                        { label: "ישויות תלויות", value: String(selectedNode.downstreamCount) },
                                    ].map((r, i) => (
                                        <div key={i} className="flex justify-between">
                                            <span className="text-muted-foreground">{r.label}</span>
                                            <span className="font-mono font-medium">{r.value}</span>
                                        </div>
                                    ))}
                                </div>

                                {selectedNode.operationalStatus === "PLANNED" && (
                                    <div className="p-2 rounded-md bg-blue-500/10 border border-blue-500/30">
                                        <p className="text-xs text-blue-400">
                                            ⚠ ישות זו PLANNED — דחיית לו"ז בלבד, ללא נזק פעיל.
                                            ישויות תחתיה אינן מועלות לדרגת CRITICAL.
                                        </p>
                                    </div>
                                )}

                                {reverseResult?.dependent_entities?.length > 0 && (
                                    <div>
                                        <p className="text-xs text-muted-foreground mb-1">
                                            תלויות ב-{selectedNode.name}:
                                        </p>
                                        <div className="space-y-1">
                                            {reverseResult.dependent_entities.slice(0, 4).map((d: any, i: number) => (
                                                <div key={i} className="text-xs p-1.5 rounded bg-muted/50">
                                                    {d.name} <span className="text-muted-foreground">[{d.entity_type}]</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                <Link
                                    href={`/impact/query?entity=${encodeURIComponent(selectedNode.name)}`}
                                    className="block text-xs text-center py-2 rounded-md bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
                                >
                                    ⚡ הפעל ניתוח השפעה מישות זו
                                </Link>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
