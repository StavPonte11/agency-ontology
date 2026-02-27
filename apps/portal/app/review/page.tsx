import { Check, X, MessageSquare, AlertCircle, Clock, CheckCircle2 } from "lucide-react"

export default function ReviewQueuePage() {
    const reviews = [
        {
            id: "REV-1001",
            term: "קמ\"ן",
            type: "ALIAS_PROPOSAL",
            source: "doc:pakal_modiin_2023.pdf",
            confidence: 0.88,
            status: "PENDING",
            timestamp: "לפני 10 דקות",
            urgency: "NORMAL",
            details: {
                proposedAction: "הוספת לשם נרדף למושג 'קצין מודיעין' (C-105)",
                context: "...באישור קמ\"ן האוגדה, יורדו הפקודות לרמת החטיבה...",
                reasoning: "LLM זיהה קשר סמנטי כמעט ודאי בהקשר צבאי-תורני.",
            }
        },
        {
            id: "REV-1002",
            term: "שח\"ר",
            type: "NEW_CONCEPT",
            source: "openmetadata:table:idf.crm.shachar_users",
            confidence: 0.62, // Low confidence -> Needs review
            status: "PENDING",
            timestamp: "לפני 45 דקות",
            urgency: "HIGH",
            details: {
                proposedAction: "יצירת מושג חדש מסוג SYSTEM",
                context: "שירות חיילי רשתי / שילוב חרדים (קונפליקט פיענוח)",
                reasoning: "זוהו שתי משמעויות שונות לראשי התיבות 'שח\"ר' בארגון. דורש הכרעת אנוש האם לפצל ל-2 מושגים או שזו טעות חילוץ.",
            }
        },
        {
            id: "REV-1003",
            term: "נוהל קרב",
            type: "RELATION_PROPOSAL",
            source: "doc:torat_lahima.pdf",
            confidence: 0.95,
            status: "PENDING",
            timestamp: "לפני שעתיים",
            urgency: "NORMAL",
            details: {
                proposedAction: "יצירת קשר 'PRECEDES' (קודם ל-) אל מושג 'פקודת מבצע'",
                context: "עם סיום אלמנטרי של נוהל הקרב, תופץ פקודת המבצע המלאה לכוחות...",
                reasoning: "קשר סיבתי וסדר כרונולוגי זוהה בטקסט.",
            }
        }
    ]

    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center justify-between border-b border-border pb-4">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">תור סקירה (Review Queue)</h2>
                    <p className="text-muted-foreground mt-1">אישורים אנושיים להצעות צינור חילוץ המידע (Human-in-the-loop)</p>
                </div>
                <div className="flex items-center gap-4 bg-muted/50 px-4 py-2 rounded-md border border-border">
                    <div className="text-sm font-medium">
                        ממתינים לאישור: <span className="text-foreground text-lg ml-1 font-bold">{reviews.length}</span>
                    </div>
                    <div className="h-6 w-px bg-border mx-2"></div>
                    <div className="text-sm font-medium flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-destructive animate-pulse"></span>
                        דחופים: <span className="text-foreground text-lg ml-1 font-bold">1</span>
                    </div>
                </div>
            </div>

            <div className="grid gap-6">
                {reviews.map((review) => (
                    <div key={review.id} className="bg-card border border-border rounded-lg shadow-sm overflow-hidden flex flex-col md:flex-row">

                        {/* Action Bar (Left on screen, right in RTL) */}
                        <div className="bg-muted/30 p-4 border-b md:border-b-0 md:border-l border-border flex md:flex-col items-center justify-center gap-3 md:w-24 shrink-0">
                            <button
                                title="אשר (Approve)"
                                className="w-10 h-10 rounded-full bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500 hover:text-white flex items-center justify-center transition-colors border border-emerald-500/20 hover:border-emerald-500"
                            >
                                <Check className="w-5 h-5" />
                            </button>
                            <button
                                title="דחה (Reject)"
                                className="w-10 h-10 rounded-full bg-destructive/10 text-destructive hover:bg-destructive hover:text-white flex items-center justify-center transition-colors border border-destructive/20 hover:border-destructive"
                            >
                                <X className="w-5 h-5" />
                            </button>
                            <button
                                title="הערה (Comment)"
                                className="w-10 h-10 rounded-full bg-background text-muted-foreground hover:bg-accent hover:text-foreground flex items-center justify-center transition-colors border border-border mt-auto"
                            >
                                <MessageSquare className="w-4 h-4" />
                            </button>
                        </div>

                        {/* Content Body */}
                        <div className="p-6 flex-1 flex flex-col gap-4">
                            <div className="flex justify-between items-start">
                                <div className="flex items-center gap-3">
                                    <h3 className="text-xl font-bold flex items-center gap-2">
                                        {review.urgency === 'HIGH' && <AlertCircle className="w-5 h-5 text-destructive" />}
                                        {review.term}
                                    </h3>
                                    <span className="px-2.5 py-1 bg-secondary text-secondary-foreground text-xs font-semibold rounded-md border border-border">
                                        {review.type === 'ALIAS_PROPOSAL' ? 'הצעת שם נרדף' :
                                            review.type === 'NEW_CONCEPT' ? 'מושג חדש' : 'יצירת קשר'}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <Clock className="w-4 h-4" />
                                    {review.timestamp}
                                </div>
                            </div>

                            <div className="text-lg text-foreground font-medium border-r-4 border-primary/50 pr-4 mt-2">
                                {review.details.proposedAction}
                            </div>

                            <div className="grid md:grid-cols-2 gap-4 mt-2">
                                <div className="space-y-2 bg-muted/20 p-4 rounded-md border border-border/50">
                                    <div className="text-sm font-semibold text-muted-foreground flex justify-between">
                                        <span>הקשר (Context)</span>
                                        <span className="text-xs font-mono bg-background px-1 border border-border rounded">{review.source}</span>
                                    </div>
                                    <p className="text-sm font-serif leading-relaxed italic bg-accent/30 p-2 rounded">
                                        "{review.details.context}"
                                    </p>
                                </div>

                                <div className="space-y-2 bg-muted/20 p-4 rounded-md border border-border/50">
                                    <div className="text-sm font-semibold text-muted-foreground flex justify-between">
                                        <span>הסבר חילוץ (Reasoning)</span>
                                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${review.confidence > 0.8 ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500'}`}>
                                            ביטחון: {(review.confidence * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <p className="text-sm leading-relaxed text-muted-foreground">
                                        {review.details.reasoning}
                                    </p>
                                </div>
                            </div>

                        </div>
                    </div>
                ))}

                {reviews.length === 0 && (
                    <div className="text-center py-24 text-muted-foreground border-2 border-dashed border-border rounded-lg">
                        <CheckCircle2 className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                        <h3 className="text-lg font-medium">אין משימות סקירה ממתינות</h3>
                        <p className="text-sm">צינור חילוץ המידע נקי מקונפליקטים.</p>
                    </div>
                )}
            </div>
        </div>
    )
}
