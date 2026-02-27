"use client"

import { Handle, Position } from "reactflow"
import {
    Activity,
    Database,
    FolderTree,
    Scale,
    Users,
    Box,
    Tag,
    Key,
    type LucideIcon,
} from "lucide-react"

// Map concept types to icons — all imports declared before use
const ICONS: Record<string, LucideIcon> = {
    UNIT: Users,
    SYSTEM: Box,
    METRIC: Activity,
    ROLE: Tag,
    PROCESS: FolderTree,
    REGULATION: Scale,
    DATA_ASSET: Database,
    TERM: Key,
    UNKNOWN: Box,
}

// Map concept types to color classes
const COLORS: Record<string, string> = {
    UNIT: "bg-blue-500/10 border-blue-500/50 text-blue-500",
    SYSTEM: "bg-purple-500/10 border-purple-500/50 text-purple-500",
    METRIC: "bg-emerald-500/10 border-emerald-500/50 text-emerald-500",
    ROLE: "bg-amber-500/10 border-amber-500/50 text-amber-500",
    PROCESS: "bg-orange-500/10 border-orange-500/50 text-orange-500",
    REGULATION: "bg-rose-500/10 border-rose-500/50 text-rose-500",
    DATA_ASSET: "bg-cyan-500/10 border-cyan-500/50 text-cyan-500",
    TERM: "bg-slate-500/10 border-slate-500/50 text-slate-500",
    UNKNOWN: "bg-muted border-border text-foreground",
}

interface ConceptNodeData {
    label: string
    conceptType: string
    status: "APPROVED" | "DRAFT" | "NEEDS_REVIEW" | string
}

export function ConceptNode({ data }: { data: ConceptNodeData }) {
    const type = data.conceptType ?? "UNKNOWN"
    const Icon = ICONS[type] ?? ICONS.UNKNOWN
    const colors = COLORS[type] ?? COLORS.UNKNOWN

    return (
        <div className={`relative px-4 py-2 shadow-sm rounded-md border-2 bg-background min-w-[150px] ${colors}`}>
            <Handle type="target" position={Position.Top} className="w-2 h-2" />

            <div className="flex items-center gap-2">
                <Icon className="w-4 h-4 shrink-0" />
                <div className="flex flex-col">
                    <span className="font-bold text-sm text-foreground">{data.label}</span>
                    <span className="text-[10px] uppercase opacity-80">{type}</span>
                </div>
            </div>

            {data.status === "DRAFT" && (
                <div className="absolute -top-2 -right-2 px-1.5 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-bold">
                    טיוטה
                </div>
            )}

            <Handle type="source" position={Position.Bottom} className="w-2 h-2" />
        </div>
    )
}
