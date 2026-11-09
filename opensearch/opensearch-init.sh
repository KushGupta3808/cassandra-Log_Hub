#!/bin/sh
# Runs once before Fluent Bit starts: installs the index template (so level,
# node, thread and source are exact-match keyword fields) and a 7-day
# retention policy for the cassandra-logs-* indices.
set -eu

OS_URL="${OS_URL:-http://opensearch:9200}"

echo "Waiting for OpenSearch at $OS_URL ..."
until curl -fs "$OS_URL/_cluster/health" >/dev/null; do sleep 2; done

echo "Installing index template cassandra-logs ..."
curl -fsS -X PUT "$OS_URL/_index_template/cassandra-logs" \
  -H 'Content-Type: application/json' --data-binary @/init/index-template.json
echo

echo "Installing retention policy cassandra-logs-retention ..."
status=$(curl -s -o /dev/null -w '%{http_code}' "$OS_URL/_plugins/_ism/policies/cassandra-logs-retention")
if [ "$status" = "404" ]; then
  curl -fsS -X PUT "$OS_URL/_plugins/_ism/policies/cassandra-logs-retention" \
    -H 'Content-Type: application/json' --data-binary @/init/retention-policy.json
  echo
else
  echo "Policy already exists, leaving it unchanged."
fi

echo "OpenSearch setup complete."
