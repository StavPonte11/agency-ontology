import { Activity, Server, Database, History, RefreshCcw, Search, BarChart2 } from "lucide-react"

export default function PipelinePage() {
    const workers = [
        { name: "Source Scanner", topic: "agency.ontology.raw", lag: 0, status: "IDLE", throughput: "12 msg/s" },
        { name: "PDF Processor", topic: "agency.ontology.extracted", lag: 145, status: "PROCESSING", throughput: "3 pages/s" },
        { name: "LLM Extractor", topic: "agency.ontology.llm.raw", lag: 89, status: "PROCESSING", throughput: "1.2 terms/s" },
        { name: "Entity Resolver", topic: "agency.ontology.resolved", lag: 12, status: "PROCESSING", throughput: "5.5 msg/s" },
        { name: "Graph Committer", topic: "agency.ontology.commit", lag: 0, status: "IDLE", throughput: "0 msg/s" },
        { name: "ES Indexer", topic: "agency.ontology.index", lag: 2, status: "PROCESSING", throughput: "15 msg/s" },
    ]

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">ניטור Pipeline</h2>
                    <p className="text-muted-foreground mt-1">מצב מערכת הקליטה ועיבוד הנתונים של האונטולוגיה (Kafka KRaft)</p>
                </div>
                <div className="flex items-center gap-2">
                    <button className="flex items-center gap-2 px-3 py-2 bg-background border border-border rounded-md shadow-sm text-sm hover:bg-accent font-medium text-muted-foreground">
                        <RefreshCcw className="w-4 h-4" />
                        רענן סטטוס
                    </button>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <div className="bg-card border border-border rounded-lg p-6 shadow-sm flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-500 shrink-0">
                        <Activity className="w-5 h-5" />
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold text-muted-foreground">סטטוס קלאסטר</h4>
                        <p className="text-2xl font-bold text-emerald-500 mt-1">בריא</p>
                        <p className="text-xs text-muted-foreground mt-1">3 ברוקרים פעילים</p>
                    </div>
                </div>

                <div className="bg-card border border-border rounded-lg p-6 shadow-sm flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-500 shrink-0">
                        <History className="w-5 h-5" />
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold text-muted-foreground">Lag כולל במערכת</h4>
                        <p className="text-2xl font-bold mt-1">248<span className="text-sm font-normal text-muted-foreground mr-1">הודעות</span></p>
                        <p className="text-xs text-muted-foreground mt-1">צוואר בקבוק עיקרי: חילוץ PDF</p>
                    </div>
                </div>

                <div className="bg-card border border-border rounded-lg p-6 shadow-sm flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-500 shrink-0">
                        <Server className="w-5 h-5" />
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold text-muted-foreground">שרתי Worker</h4>
                        <p className="text-2xl font-bold mt-1">6 / 6</p>
                        <p className="text-xs text-muted-foreground mt-1">כל השירותים רצים (Uptime 14d)</p>
                    </div>
                </div>

                <div className="bg-card border border-border rounded-lg p-6 shadow-sm flex items-start gap-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary shrink-0">
                        <Database className="w-5 h-5" />
                    </div>
                    <div>
                        <h4 className="text-sm font-semibold text-muted-foreground">Throughput לגרף</h4>
                        <p className="text-2xl font-bold mt-1">14.2<span className="text-sm font-normal text-muted-foreground mr-1">ב/שניות</span></p>
                        <p className="text-xs text-emerald-500 mt-1">+2.4% מהשעה האחרונה</p>
                    </div>
                </div>
            </div>

            {/* Visual Pipeline Logic Mockup */}
            <h3 className="text-xl font-bold pt-4 border-b border-border pb-2">תור הודעות ושירותים (Consumer Groups)</h3>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 pt-4">
                {workers.map((worker, i) => (
                    <div key={i} className="bg-card border border-border rounded-lg shadow-sm p-5 relative overflow-hidden flex flex-col pt-10">
                        <div className={`absolute top-0 right-0 w-full h-1 
              ${worker.status === 'PROCESSING' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30'}`}>
                        </div>

                        <div className="absolute top-3 left-3 flex gap-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide
                ${worker.lag === 0 ? 'bg-emerald-500/10 text-emerald-500' :
                                    worker.lag > 100 ? 'bg-destructive/10 text-destructive' : 'bg-amber-500/10 text-amber-500'}`}>
                                Lag: {worker.lag}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide border
                ${worker.status === 'PROCESSING' ? 'border-primary/50 text-primary' : 'border-border text-muted-foreground'}`}>
                                {worker.status}
                            </span>
                        </div>

                        <h4 className="text-lg font-bold">{worker.name}</h4>
                        <div className="flex gap-2 text-xs font-mono text-muted-foreground mt-1 mb-6" dir="ltr">
                            <span className="text-foreground/50">topic:</span> {worker.topic}
                        </div>

                        <div className="mt-auto grid grid-cols-2 gap-2 text-sm">
                            <div className="bg-muted/30 p-2 rounded border border-border/50 text-center">
                                <div className="text-xs text-muted-foreground mb-1">תפוקה אחרונה</div>
                                <div className="font-medium text-foreground" dir="ltr">{worker.throughput}</div>
                            </div>
                            <div className="bg-muted/30 p-2 rounded border border-border/50 text-center flex items-center justify-center cursor-pointer hover:bg-muted/50 hover:text-primary transition-colors">
                                <BarChart2 className="w-5 h-5 mx-auto" />
                                <span className="sr-only">הצג לוגים מלאים בגראפנה</span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <div className="pt-8">
                <div className="bg-muted/30 border-2 border-dashed border-border rounded-lg p-12 text-center text-muted-foreground">
                    <p className="text-sm flex flex-col items-center justify-center gap-2">
                        <Search className="w-8 h-8 opacity-50 mb-2" />
                        מידע טלמטריה מפורט זמין במערכת הגראפנה (Grafana)
                        <a href="http://localhost:3000/d/agency-pipeline" target="_blank" className="text-primary hover:underline mt-2">
                            פתח דשבורד מפורט (OpenTelemetry) &rarr;
                        </a>
                    </p>
                </div>
            </div>
        </div>
    )
}
