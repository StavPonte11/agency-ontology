import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Activity, AlertTriangle, Database, Network } from "lucide-react"

export default function Dashboard() {
    return (
        <div className="flex-1 space-y-6 p-8 pt-6">
            <div className="flex items-center justify-between space-y-2">
                <h2 className="text-3xl font-bold tracking-tight">מבט על</h2>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">מושגים באונטולוגיה</CardTitle>
                        <Network className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">12,450</div>
                        <p className="text-xs text-muted-foreground">+201 מיום קודם</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">נכסי מידע מקושרים</CardTitle>
                        <Database className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">8,234</div>
                        <p className="text-xs text-muted-foreground">+54 מיפויים חדשים</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">ממתינים לאישור (תור סקירה)</CardTitle>
                        <AlertTriangle className="h-4 w-4 text-amber-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">142</div>
                        <p className="text-xs text-muted-foreground">3 סומנו כדחופים</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">בריאות ה-Pipeline</CardTitle>
                        <Activity className="h-4 w-4 text-emerald-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-500">תקין</div>
                        <p className="text-xs text-muted-foreground">0 שגיאות ב-24 שעות האחרונות</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>קצב צמיחת האונטולוגיה</CardTitle>
                    </CardHeader>
                    <CardContent className="pl-2 h-[300px] flex items-center justify-center text-muted-foreground border-2 border-dashed m-4 rounded-lg">
                        {/* Placeholder for Recharts / Visx chart */}
                        [תרשים קצב הוספת מושגים]
                    </CardContent>
                </Card>
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>פעילות אחרונה</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-8">
                            {[
                                { term: "רמת מוכנות", action: "נוסף על ידי", source: "פקודת מטכ\"ל ה'", time: "לפני 5 דקות" },
                                { term: "מערכת צי\"ד", action: "עודכן ממקור", source: "OpenMetadata", time: "לפני שעה" },
                                { term: "שח\"ר", action: "אושר בתור סקירה", source: "משתמש א'", time: "לפני שעתיים" },
                                { term: "קמ\"ן", action: "מוזג עם (קצין מודיעין)", source: "Entity Resolver", time: "לפני 3 שעות" },
                            ].map((item, i) => (
                                <div key={i} className="flex items-center">
                                    <div className="ml-4 space-y-1">
                                        <p className="text-sm font-medium leading-none">{item.term}</p>
                                        <p className="text-sm text-muted-foreground">
                                            {item.action} <span className="text-primary">{item.source}</span>
                                        </p>
                                    </div>
                                    <div className="mr-auto font-medium text-xs text-muted-foreground">{item.time}</div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
