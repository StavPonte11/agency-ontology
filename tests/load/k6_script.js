import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '30s', target: 20 },  // Ramp up to 20 users
        { duration: '1m', target: 20 },   // Stay at 20 users for 1 min
        { duration: '30s', target: 80 },  // Spike to 80 users
        { duration: '1m', target: 80 },   // Stay at 80 users for 1 min
        { duration: '30s', target: 0 },   // Ramp down
    ],
    thresholds: {
        http_req_duration: ['p(95)<500'], // 95% of requests should be below 500ms
    },
};

const BASE_URL = 'http://localhost:8000';

export default function () {
    // 1. Test Semantic Search Endpoint
    const searchPayload = JSON.stringify({
        query: "מי מפקד על חטיבת הצנחנים חי\"ר?",
        limit: 5,
        domain: "Operations"
    });

    const searchParams = {
        headers: { 'Content-Type': 'application/json' },
    };

    const searchRes = http.post(`${BASE_URL}/api/v1/retrieval/search`, searchPayload, searchParams);
    check(searchRes, {
        'Search status is 200': (r) => r.status === 200,
        'Search response time < 800ms': (r) => r.timings.duration < 800,
    });

    sleep(1);

    // 2. Test Exact Match Lookup Endpoint
    const lookupRes = http.get(`${BASE_URL}/api/v1/retrieval/lookup/C-101`);
    check(lookupRes, {
        'Lookup status is 200 or 404': (r) => r.status === 200 || r.status === 404,
    });

    sleep(1);
}
