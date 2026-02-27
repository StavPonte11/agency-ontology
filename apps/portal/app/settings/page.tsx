import { Save, Bell, Shield, Database, Globe, RefreshCcw } from "lucide-react"

export default function SettingsPage() {
    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center justify-between border-b border-border pb-4">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">הגדרות מערכת</h2>
                    <p className="text-muted-foreground mt-1">ניהול תצורת האונטולוגיה, מודלי שפה, והרשאות</p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground shadow-sm rounded-md text-sm font-medium hover:bg-primary/90">
                    <Save className="w-4 h-4" />
                    שמור שינויים
                </button>
            </div>

            <div className="grid gap-6 md:grid-cols-4">
                {/* Navigation Sidebar inside Settings */}
                <div className="space-y-1">
                    <button className="w-full flex items-center gap-3 px-3 py-2 bg-accent text-accent-foreground font-medium rounded-md text-sm">
                        <Database className="w-4 h-4" />
                        מודלי שפה (LLM)
                    </button>
                    <button className="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-accent/50 hover:text-foreground font-medium rounded-md text-sm transition-colors">
                        <Globe className="w-4 h-4" />
                        שפות ונירמול טקסט
                    </button>
                    <button className="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-accent/50 hover:text-foreground font-medium rounded-md text-sm transition-colors">
                        <Shield className="w-4 h-4" />
                        אבטחה וסיווג
                    </button>
                    <button className="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-accent/50 hover:text-foreground font-medium rounded-md text-sm transition-colors">
                        <RefreshCcw className="w-4 h-4" />
                        מנגנוני Cache
                    </button>
                </div>

                {/* Settings Content Area */}
                <div className="col-span-3 space-y-6">
                    <div className="bg-card border border-border rounded-lg shadow-sm p-6">
                        <h3 className="text-lg font-bold mb-4">תצורת מודלי חילוץ מתקדם</h3>

                        <div className="space-y-4 max-w-xl">
                            <div className="space-y-2">
                                <label className="text-sm font-medium">מודל עיקרי לחילוץ (Primary Extractor)</label>
                                <select className="w-full p-2 bg-background border border-border rounded-md text-sm focus:ring-1 focus:ring-primary outline-none">
                                    <option>openai/gpt-4-turbo-preview</option>
                                    <option>anthropic/claude-3-opus</option>
                                    <option>local/llama3.3:70b-instruct</option>
                                </select>
                                <p className="text-xs text-muted-foreground">המודל הראשי המשמש קריאות LangChain structured_output</p>
                            </div>

                            <div className="space-y-2 pt-2">
                                <label className="text-sm font-medium">מודל חלופי (Fallback via Instructor)</label>
                                <select className="w-full p-2 bg-background border border-border rounded-md text-sm focus:ring-1 focus:ring-primary outline-none">
                                    <option>local/llama3.3:70b-instruct</option>
                                    <option>openai/gpt-4-turbo-preview</option>
                                    <option>openai/gpt-3.5-turbo</option>
                                </select>
                                <p className="text-xs text-muted-foreground">יופעל קריאת Instructor fallback אם המודל הראשי נכשל ב-JSON Schema</p>
                            </div>

                            <div className="space-y-2 pt-2">
                                <label className="text-sm font-medium">מודל Embedding סמנטי</label>
                                <div className="flex gap-2">
                                    <input type="text" defaultValue="mxbai-embed-large" className="w-full p-2 bg-background border border-border rounded-md text-sm focus:ring-1 focus:ring-primary outline-none" dir="ltr" />
                                </div>
                                <p className="text-xs text-muted-foreground">מודל ליצירת וקטורים צפופים ל-Elasticsearch HNSW (מומלץ mxbai לטקסט מעורב עברית/אנגלית)</p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-card border border-border rounded-lg shadow-sm p-6">
                        <h3 className="text-lg font-bold mb-4 text-destructive flex items-center gap-2">
                            <Shield className="w-5 h-5" />
                            אזור ניהול סווג ביטחוני
                        </h3>
                        <p className="text-sm text-muted-foreground mb-4">
                            הגדרות אלו משפיעות באופן רוחבי על הרשאות הגישה של סוכנים למידע האונטולוגי.
                        </p>
                        <div className="flex items-center gap-3">
                            <input type="checkbox" id="strict" className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary" defaultChecked />
                            <label htmlFor="strict" className="text-sm font-medium cursor-pointer">
                                אכיפת סיווג נוקשה (Strict Clearance Pattern) - סוכנים ללא סיווג מפורש יחסמו
                            </label>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
