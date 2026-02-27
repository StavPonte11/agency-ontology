/** @type {import('next').NextConfig} */
const nextConfig = {
    // Allow building even with TS errors during early dev; remove before prod
    typescript: {
        ignoreBuildErrors: false,
    },
}

module.exports = nextConfig
