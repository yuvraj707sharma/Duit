import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 20 },  // Ramp up to 20 users
    { duration: '30s', target: 50 },  // Sustained load at 50 VUs
    { duration: '10s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<150'], // 95% of requests must complete below 150ms
    http_req_failed: ['rate<0.01'],    // Error rate under 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  // Test 1: Ingest WhatsApp Webhook
  const webhookPayload = JSON.stringify({
    event: 'messages.upsert',
    data: {
      key: {
        remoteJid: `9198765432${__VU}@s.whatsapp.net`,
        fromMe: false,
        id: `K6_MSG_${__VU}_${__ITER}`
      },
      message: {
        conversation: 'Move my 4pm meeting to tomorrow 5pm'
      }
    }
  });

  const headers = {
    'Content-Type': 'application/json',
    'apikey': 'evolution_dev_api_key_12345'
  };

  const res1 = http.post(`${BASE_URL}/api/webhooks/evolution`, webhookPayload, { headers });
  check(res1, {
    'webhook status is 200': (r) => r.status === 200,
    'cascade processed successfully': (r) => r.json().status === 'processed',
  });

  // Test 2: Fetch Metrics
  const res2 = http.get(`${BASE_URL}/api/metrics`);
  check(res2, {
    'metrics status is 200': (r) => r.status === 200,
    'stage latencies present': (r) => r.json().stage_latencies_ms !== undefined,
  });

  sleep(0.5);
}
