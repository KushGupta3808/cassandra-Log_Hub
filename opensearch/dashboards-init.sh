#!/bin/sh
# Runs once after OpenSearch Dashboards is up: creates the cassandra-logs-*
# index pattern and makes it the default, so Discover opens straight onto the logs.
set -eu

OSD_URL="${OSD_URL:-http://dashboards:5601}"

echo "Waiting for OpenSearch Dashboards at $OSD_URL ..."
until curl -fs "$OSD_URL/api/status" >/dev/null; do sleep 3; done

echo "Creating index pattern cassandra-logs-* ..."
curl -fsS -X POST "$OSD_URL/api/saved_objects/index-pattern/cassandra-logs?overwrite=true" \
  -H 'osd-xsrf: true' -H 'Content-Type: application/json' \
  -d '{"attributes":{"title":"cassandra-logs-*","timeFieldName":"@timestamp"}}'
echo

curl -fsS -X POST "$OSD_URL/api/opensearch-dashboards/settings" \
  -H 'osd-xsrf: true' -H 'Content-Type: application/json' \
  -d '{"changes":{"defaultIndex":"cassandra-logs"}}'
echo

echo "Dashboards setup complete. Open http://localhost:5601 and go to Discover."
