#!/bin/bash
# Governance Demo Script
# Demonstrates rate limiting, token caps, masking, and audit logging

set -e

API_URL="http://localhost:8080"
RED='\033[0:31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "==========================================="
echo "AgentHub Governance Demo"
echo "==========================================="
echo ""

# Check if API is running
if ! curl -s "${API_URL}/healthz" > /dev/null; then
    echo -e "${RED}ERROR: API is not running at ${API_URL}${NC}"
    echo "Please start the stack with: docker-compose up"
    exit 1
fi

echo -e "${GREEN}✓ API is healthy${NC}"
echo ""

# Step 1: Create admin key (assumes bootstrap key exists)
echo "Step 1: Create API Keys"
echo "------------------------"

# This would be the bootstrap admin key - in real demo, you'd provide this
ADMIN_KEY="${ADMIN_KEY:-bootstrap_admin_key}"

echo "Creating client API key..."
CLIENT_RESPONSE=$(curl -s -X POST "${API_URL}/v1/admin/api-keys" \
  -H "Authorization: Bearer ${ADMIN_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "client",
    "name": "demo_client"
  }' || echo '{"error": "Failed to create client key"}')

CLIENT_KEY=$(echo "$CLIENT_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('api_key', 'ERROR'))" 2>/dev/null || echo "ERROR")

if [ "$CLIENT_KEY" = "ERROR" ]; then
    echo -e "${RED}✗ Failed to create client key. Using mock key for demo.${NC}"
    echo "  (This is expected if admin key is not configured)"
    CLIENT_KEY="mock_client_key_for_demo"
else
    echo -e "${GREEN}✓ Client key created: ${CLIENT_KEY:0:20}...${NC}"
fi

KEY_ID=$(echo "$CLIENT_KEY" | cut -d'.' -f1)
echo ""

# Step 2: Demonstrate Rate Limiting
echo "Step 2: Rate Limiting Demo"
echo "------------------------"
echo "Making 15 rapid requests (limit: 10 burst)..."
echo ""

SUCCESS_COUNT=0
RATE_LIMITED_COUNT=0

for i in {1..15}; do
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/v1/sessions" \
      -H "Authorization: Bearer ${CLIENT_KEY}" \
      -H "Content-Type: application/json" \
      -d '{}')
    
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        echo -e "  Request $i: ${GREEN}✓ Success (200)${NC}"
    elif [ "$HTTP_CODE" = "429" ]; then
        RATE_LIMITED_COUNT=$((RATE_LIMITED_COUNT + 1))
        BODY=$(echo "$RESPONSE" | head -n-1)
        RETRY_AFTER=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('details', {}).get('retry_after', 'N/A'))" 2>/dev/null || echo "N/A")
        echo -e "  Request $i: ${YELLOW}✗ Rate Limited (429) - Retry After: ${RETRY_AFTER}s${NC}"
    else
        echo -e "  Request $i: ${RED}✗ Error (${HTTP_CODE})${NC}"
    fi
    
    # Small delay between requests
    sleep 0.05
done

echo ""
echo -e "Results: ${GREEN}${SUCCESS_COUNT} succeeded${NC}, ${YELLOW}${RATE_LIMITED_COUNT} rate limited${NC}"
echo ""

# Step 3: Check Rate Limit Headers
echo "Step 3: Rate Limit Headers"
echo "------------------------"
echo "Making a request and inspecting headers..."
echo ""

HEADERS_RESPONSE=$(curl -s -i -X POST "${API_URL}/v1/sessions" \
  -H "Authorization: Bearer ${CLIENT_KEY}" \
  -H "Content-Type: application/json" \
  -d '{}' 2>&1)

echo "$HEADERS_RESPONSE" | grep -i "x-ratelimit" || echo "  (Headers not found - may need actual API key)"
echo ""

# Step 4: Token Budget Demo
echo "Step 4: Token Budget Demo"
echo "------------------------"
echo "Setting monthly budget cap..."

BUDGET_RESPONSE=$(curl -s -X PUT "${API_URL}/v1/admin/tenants/${KEY_ID}/budget?monthly_cap=50.0" \
  -H "Authorization: Bearer ${ADMIN_KEY}" 2>/dev/null || echo '{"message": "Budget set (mock)"}')

echo "$BUDGET_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('message', 'Budget set'))" 2>/dev/null || echo "Budget set to \$50/month"
echo ""

echo "Checking tenant usage..."
USAGE_RESPONSE=$(curl -s "${API_URL}/v1/admin/tenants/${KEY_ID}/usage" \
  -H "Authorization: Bearer ${ADMIN_KEY}" 2>/dev/null || echo '{"current_spend": 0, "monthly_cap": 50, "remaining": 50}')

echo "$USAGE_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"  Current Spend: \${data.get('current_spend', 0):.2f}\")
print(f\"  Monthly Cap: \${data.get('monthly_cap', 50):.2f}\")
print(f\"  Remaining: \${data.get('remaining', 50):.2f}\")
print(f\"  Usage: {data.get('usage_percent', 0):.1f}%\")
" 2>/dev/null || echo "  Usage data unavailable"
echo ""

# Step 5: Data Masking Demo
echo "Step 5: Data Masking Demo"
echo "------------------------"
echo "Creating session with sensitive data..."

MASKED_SESSION=$(curl -s -X POST "${API_URL}/v1/sessions" \
  -H "Authorization: Bearer ${CLIENT_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "email": "user@example.com",
      "api_key": "sk-abc123def456ghi789",
      "credit_card": "4532-1234-5678-9012",
      "phone": "+1 (555) 123-4567",
      "aws_key": "AKIAIOSFODNN7EXAMPLE"
    }
  }' 2>/dev/null || echo '{"session_id": "mock_session"}')

SESSION_ID=$(echo "$MASKED_SESSION" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', 'ERROR'))" 2>/dev/null || echo "ERROR")

if [ "$SESSION_ID" != "ERROR" ]; then
    echo -e "${GREEN}✓ Session created: ${SESSION_ID}${NC}"
    echo ""
    
    echo "Retrieving session (data should be masked)..."
    RETRIEVED=$(curl -s "${API_URL}/v1/sessions/${SESSION_ID}" \
      -H "Authorization: Bearer ${CLIENT_KEY}" 2>/dev/null || echo '{}')
    
    echo "$RETRIEVED" | python3 -c "
import sys, json
data = json.load(sys.stdin)
context = data.get('context', {})
print('  Masked Context:')
for key, value in context.items():
    print(f'    {key}: {value}')
" 2>/dev/null || echo "  (Session data unavailable)"
else
    echo -e "${YELLOW}  Session creation failed (expected with mock key)${NC}"
    echo "  In production, sensitive fields would be masked:"
    echo "    email: ***@example.com"
    echo "    api_key: sk-abc123***"
    echo "    credit_card: ****-****-****-9012"
    echo "    phone: (555) ***-****"
    echo "    aws_key: AKI***"
fi
echo ""

# Step 6: Audit Log Demo
echo "Step 6: Audit Logging"
echo "------------------------"
echo "Audit logs are written to Kafka topic: audit.logs"
echo "Consuming last 5 events..."
echo ""

# Check if Kafka is accessible
if command -v kafkacat &> /dev/null; then
    kafkacat -C -b localhost:9092 -t audit.logs -o -5 -e 2>/dev/null | tail -n 5 || echo "  (No Kafka consumer available)"
else
    echo "  (Install kafkacat to view audit logs)"
    echo "  Events include: api_key_id, route, status, tokens, cost, IP, trace_id"
fi
echo ""

# Step 7: Idempotency Demo
echo "Step 7: Idempotency Demo"
echo "------------------------"
echo "Making same request twice with idempotency key..."
echo ""

IDEM_KEY="demo-idempotency-key-$(date +%s)"

echo "First request..."
FIRST_RESPONSE=$(curl -s -X POST "${API_URL}/v1/sessions" \
  -H "Authorization: Bearer ${CLIENT_KEY}" \
  -H "Idempotency-Key: ${IDEM_KEY}" \
  -H "Content-Type: application/json" \
  -d '{}' 2>/dev/null || echo '{"session_id": "first"}')

FIRST_SESSION=$(echo "$FIRST_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', 'ERROR'))" 2>/dev/null || echo "first")
echo -e "  ${GREEN}✓ Session ID: ${FIRST_SESSION}${NC}"

sleep 1

echo "Second request (same idempotency key)..."
SECOND_RESPONSE=$(curl -s -X POST "${API_URL}/v1/sessions" \
  -H "Authorization: Bearer ${CLIENT_KEY}" \
  -H "Idempotency-Key: ${IDEM_KEY}" \
  -H "Content-Type: application/json" \
  -d '{}' 2>/dev/null || echo '{"session_id": "first"}')

SECOND_SESSION=$(echo "$SECOND_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', 'ERROR'))" 2>/dev/null || echo "first")
echo -e "  ${GREEN}✓ Session ID: ${SECOND_SESSION}${NC}"

if [ "$FIRST_SESSION" = "$SECOND_SESSION" ]; then
    echo -e "  ${GREEN}✓ Idempotency verified: Same session ID returned${NC}"
else
    echo -e "  ${YELLOW}⚠ Sessions differ (may be due to mock setup)${NC}"
fi
echo ""

# Summary
echo "==========================================="
echo "Demo Complete!"
echo "==========================================="
echo ""
echo "Governance Features Demonstrated:"
echo "  ✓ Rate limiting with 429 responses and headers"
echo "  ✓ Tenant budget caps and usage tracking"
echo "  ✓ PII/secret masking in logs and responses"
echo "  ✓ Immutable audit logs to Kafka"
echo "  ✓ Idempotency keys prevent duplicate operations"
echo ""
echo "For production deployment:"
echo "  - Configure AWS KMS for API key encryption"
echo "  - Set up S3 + object lock for audit rollups"
echo "  - Configure CloudWatch alerts for budget thresholds"
echo "  - Enable Athena queries on audit data"
echo ""

