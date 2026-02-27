"use client"

import { useState, useCallback } from "react"
import ReactFlow, {
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    addEdge,
    Connection,
    Edge,
} from "reactflow"
import "reactflow/dist/style.css"
import { ConceptNode } from "@/components/graph/ConceptNode"
import { Search, Filter } from "lucide-react"

const nodeTypes = {
    concept: ConceptNode,
}

const initialNodes = [
    {
        id: "1",
        type: "concept",
        position: { x: 250, y: 100 },
        data: { label: "מערכת צי\"ד", conceptType: "SYSTEM", status: "APPROVED" },
    },
    {
        id: "2",
        type: "concept",
        position: { x: 100, y: 250 },
        data: { label: "אוגדה 36", conceptType: "UNIT", status: "APPROVED" },
    },
    {
        id: "3",
        type: "concept",
        position: { x: 400, y: 250 },
        data: { label: "קצין אג\"ם", conceptType: "ROLE", status: "DRAFT" },
    },
    {
        id: "4",
        type: "concept",
        position: { x: 250, y: 400 },
        data: { label: "פקודת מטכ\"ל ה'", conceptType: "REGULATION", status: "APPROVED" },
    },
]

const initialEdges = [
    { id: "e1-2", source: "1", target: "2", label: "USED_BY", animated: true },
    { id: "e1-3", source: "1", target: "3", label: "OPERATED_BY" },
    { id: "e4-1", source: "4", target: "1", label: "GOVERNS" },
]

export default function ExplorePage() {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
    const [selectedNode, setSelectedNode] = useState<any>(null)

    const onConnect = useCallback(
        (params: Edge | Connection) => setEdges((eds) => addEdge(params, eds)),
        [setEdges]
    )

    const onNodeClick = (_: any, node: any) => {
        setSelectedNode(node)
    }

    return (
        <div className="flex h-[calc(100vh-3.5rem)] relative">
            {/* Graph Area */}
            <div className="flex-1 bg-dot-pattern relative">
                <div className="absolute top-4 right-4 z-10 flex gap-2">
                    <div className="relative">
                        <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="חיפוש צומת..."
                            className="pl-4 pr-9 py-2 text-sm bg-background border border-border rounded-md shadow-sm w-64 focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                    </div>
                    <button className="flex items-center gap-2 px-3 py-2 bg-background border border-border rounded-md shadow-sm text-sm hover:bg-accent">
                        <Filter className="w-4 h-4" />
                        סינון
                    </button>
                </div>

                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onNodeClick={onNodeClick}
                    nodeTypes={nodeTypes}
                    fitView
                    dir="ltr" // ReactFlow calculation works best in LTR, UI labels stay RTL
                    className="bg-muted/10"
                >
                    <Background color="var(--border)" gap={16} size={1} />
                    <Controls className="bg-background border-border fill-foreground" />
                </ReactFlow>
            </div>

            {/* Detail Sidebar */}
            {selectedNode && (
                <div className="w-80 border-r border-border/40 bg-card p-6 overflow-y-auto shrink-0 animate-in slide-in-from-right-8">
                    <div className="flex justify-between items-start mb-6">
                        <div>
                            <div className="text-xs font-semibold text-muted-foreground mb-1 uppercase tracking-wider">
                                {selectedNode.data.conceptType}
                            </div>
                            <h3 className="text-2xl font-bold">{selectedNode.data.label}</h3>
                        </div>
                        <button
                            onClick={() => setSelectedNode(null)}
                            className="text-muted-foreground hover:text-foreground"
                        >
                            ✕
                        </button>
                    </div>

                    <div className="space-y-6">
                        <div>
                            <h4 className="text-sm font-semibold mb-2">תיאור</h4>
                            <p className="text-sm text-muted-foreground leading-relaxed">
                                מערכת השליטה והבקרה המרכזית המשמשת את כוחות היבשה לניהול תמונת המצב המבצעית הטאקטית בזמן אמת.
                            </p>
                        </div>

                        <div>
                            <h4 className="text-sm font-semibold mb-2">מטא-דאטה</h4>
                            <dl className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <dt className="text-muted-foreground">סטטוס</dt>
                                    <dd className="font-medium">{selectedNode.data.status}</dd>
                                </div>
                                <div className="flex justify-between">
                                    <dt className="text-muted-foreground">מקור</dt>
                                    <dd className="font-medium">מדריך צי"ד 2024</dd>
                                </div>
                                <div className="flex justify-between">
                                    <dt className="text-muted-foreground">רמת סיווג</dt>
                                    <dd className="font-medium text-amber-500">שמור</dd>
                                </div>
                            </dl>
                        </div>

                        <div className="pt-4 border-t border-border/40">
                            <button className="w-full py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 transition-colors">
                                ערוך מושג
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
