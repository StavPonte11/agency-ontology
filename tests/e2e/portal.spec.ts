import { test, expect } from "@playwright/test"

test.describe("Portal Smoke Tests", () => {
    test("dashboard loads with Hebrew content", async ({ page }) => {
        await page.goto("/")
        await expect(page.locator("h2")).toContainText("מבט על")
        await expect(page.locator("nav")).toBeVisible()
    })

    test("explore page loads with React Flow canvas", async ({ page }) => {
        await page.goto("/explore")
        await expect(page.locator(".react-flow")).toBeVisible()
        await expect(page.getByPlaceholder("חיפוש צומת...")).toBeVisible()
    })

    test("concepts page renders table", async ({ page }) => {
        await page.goto("/concepts")
        await expect(page.locator("table")).toBeVisible()
        await expect(page.locator("th").first()).toContainText("מזהה")
    })

    test("review queue page shows pending items", async ({ page }) => {
        await page.goto("/review")
        await expect(page.locator("h2")).toContainText("תור סקירה")
        // Should have at least one review card
        const cards = page.locator('[data-testid="review-card"], .bg-card')
        await expect(cards.first()).toBeVisible()
    })

    test("RTL layout is applied", async ({ page }) => {
        await page.goto("/")
        const htmlDir = await page.locator("html").getAttribute("dir")
        expect(htmlDir).toBe("rtl")
    })

    test("sources page renders connector cards", async ({ page }) => {
        await page.goto("/sources")
        await expect(page.locator("h2")).toContainText("מקורות מידע")
        // At least 2 connector cards
        const cards = page.locator(".bg-card").all()
        expect((await cards).length).toBeGreaterThanOrEqual(2)
    })

    test("pipeline page shows Kafka workers", async ({ page }) => {
        await page.goto("/pipeline")
        await expect(page.locator("h2")).toContainText("ניטור Pipeline")
    })

    test("settings page renders LLM config form", async ({ page }) => {
        await page.goto("/settings")
        await expect(page.locator("h2")).toContainText("הגדרות מערכת")
        await expect(page.locator("select").first()).toBeVisible()
    })
})
