#!/bin/sh
set -e

echo "Running backend unit tests..."
docker compose exec api pytest unit_tests/ -v --tb=short

echo "Running backend API tests..."
docker compose exec api pytest API_tests/ -v --tb=short

echo "All tests passed."
