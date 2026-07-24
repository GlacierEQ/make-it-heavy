#!/bin/bash
# ci-deploy-fleet.sh — Batch CI deployment with advanced features
set -euo pipefail

# Configuration
LOG_FILE="/tmp/ci-deploy-fleet-$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="/tmp/ci-backups-$(date +%Y%m%d_%H%M%S)"
MAX_RETRIES=2
RETRY_DELAY=5

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

REPOS=()
LANG_OVERRIDE=""
DRY_RUN=false
UPGRADE=false
ALL_PYTHON=false
ALL_TYPESCRIPT=false
VERBOSE=false
VALIDATE_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --lang) LANG_OVERRIDE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --upgrade) UPGRADE=true; shift ;;
    --all-python) ALL_PYTHON=true; shift ;;
    --all-typescript) ALL_TYPESCRIPT=true; shift ;;
    --verbose) VERBOSE=true; shift ;;
    --validate-only) VALIDATE_ONLY=true; shift ;;
    --help) 
      echo "Usage: $0 [REPOS...] [--lang python|typescript|go] [--dry-run] [--upgrade] [--verbose] [--validate-only]"
      echo "Options:"
      echo "  --lang LANG        Force language for all repos"
      echo "  --dry-run          Show what would be done without doing it"
      echo "  --upgrade          Replace existing CI with new version"
      echo "  --verbose          Show detailed output"
      echo "  --validate-only    Only validate workflow syntax"
      echo "  --all-python       Deploy to all Python repos"
      echo "  --all-typescript   Deploy to all TypeScript repos"
      exit 0
      ;;
    *) REPOS+=("$1"); shift ;;
  esac
done

# Logging function
log() {
  local level=$1
  local message=$2
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
  
  case $level in
    INFO) echo -e "${BLUE}ℹ️  $message${NC}" ;;
    SUCCESS) echo -e "${GREEN}✅ $message${NC}" ;;
    WARNING) echo -e "${YELLOW}⚠️  $message${NC}" ;;
    ERROR) echo -e "${RED}❌ $message${NC}" ;;
    DEBUG) $VERBOSE && echo -e "🔍 $message" ;;
  esac
}

# Validate workflow syntax
validate_workflow() {
  local workflow=$1
  local repo=$2
  
  # Check required fields
  if ! echo "$workflow" | grep -q "name:"; then
    log ERROR "Missing 'name' field in workflow for $repo"
    return 1
  fi
  
  if ! echo "$workflow" | grep -q "on:"; then
    log ERROR "Missing 'on' trigger in workflow for $repo"
    return 1
  fi
  
  if ! echo "$workflow" | grep -q "jobs:"; then
    log ERROR "Missing 'jobs' section in workflow for $repo"
    return 1
  fi
  
  # Check for valid YAML structure (basic check)
  if echo "$workflow" | grep -q "	"; then
    log WARNING "Tabs detected in workflow for $repo - should use spaces"
  fi
  
  log DEBUG "Workflow validation passed for $repo"
  return 0
}

# Backup existing CI
backup_ci() {
  local repo=$1
  local sha=$2
  
  mkdir -p "$BACKUP_DIR"
  local backup_file="$BACKUP_DIR/${repo}_ci_$(date +%s).yml"
  
  gh api "repos/GlacierEQ/$repo/contents/.github/workflows/ci.yml" \
    --jq '.content' | base64 -d > "$backup_file" 2>/dev/null
  
  if [ -f "$backup_file" ]; then
    log DEBUG "Backed up CI for $repo to $backup_file"
  fi
}

# Retry logic
retry_command() {
  local cmd=$1
  local retries=0
  
  while [ $retries -lt $MAX_RETRIES ]; do
    if eval "$cmd"; then
      return 0
    fi
    
    ((retries++))
    if [ $retries -lt $MAX_RETRIES ]; then
      log WARNING "Retry $retries/$MAX_RETRIES after ${RETRY_DELAY}s delay..."
      sleep $RETRY_DELAY
    fi
  done
  
  return 1
}

export GITHUB_TOKEN="${GITHUB_TOKEN:-$(grep oauth_token ~/.config/gh/hosts.yml | head -1 | awk '{print $2}')}"

if $ALL_PYTHON; then
  REPOS=($(gh repo list GlacierEQ --limit 500 --json name,primaryLanguage -q '.[] | select(.primaryLanguage?.name == "Python") | .name'))
fi
if $ALL_TYPESCRIPT; then
  REPOS=($(gh repo list GlacierEQ --limit 500 --json name,primaryLanguage -q '.[] | select(.primaryLanguage?.name == "TypeScript") | .name'))
fi

log INFO "Starting CI deployment fleet"
log INFO "Log file: $LOG_FILE"
log INFO "Backup directory: $BACKUP_DIR"

SUCCESS=0; FAIL=0; SKIP=0; VALIDATE=0

for repo in "${REPOS[@]}"; do
  log INFO "Processing $repo..."
  
  # Detect language
  if [ -n "$LANG_OVERRIDE" ]; then
    LANG="$LANG_OVERRIDE"
  else
    LANG=$(gh repo list GlacierEQ --limit 1 --json name,primaryLanguage -q ".[] | select(.name == \"$repo\") | .primaryLanguage?.name // \"python\"" 2>/dev/null)
    case "$LANG" in
      Python) LANG="python" ;;
      TypeScript) LANG="typescript" ;;
      Go) LANG="go" ;;
      *) LANG="python" ;;
    esac
  fi
  
  log DEBUG "Detected language: $LANG for $repo"

  # Check if CI exists
  EXISTS=$(gh api repos/GlacierEQ/$repo/contents/.github/workflows/ci.yml --jq '.sha' 2>/dev/null)
  if [ -n "$EXISTS" ] && ! $UPGRADE; then
    log WARNING "$repo already has CI (use --upgrade to replace)"
    ((SKIP++))
    continue
  fi

  # Check default branch
  DEFAULT=$(gh api repos/GlacierEQ/$repo --jq '.defaultBranch // "main"' 2>/dev/null)
  log DEBUG "Default branch: $DEFAULT for $repo"

  WF="name: CI

on:
  push:
    branches: [$DEFAULT, develop]
  pull_request:
    branches: [$DEFAULT]

jobs:
  ci:
    uses: GlacierEQ/public-actions-runner-host/.github/workflows/reusable-quick-ci.yml@main
    with:
      repo_name: \${{ github.event.repository.name }}
      language: $LANG"

  # Validate workflow
  if ! validate_workflow "$WF" "$repo"; then
    ((FAIL++))
    continue
  fi
  
  ((VALIDATE++))

  if $VALIDATE_ONLY; then
    log SUCCESS "Workflow validation passed for $repo"
    continue
  fi

  if $DRY_RUN; then
    log INFO "Would deploy $LANG CI to $repo (branch: $DEFAULT)"
    ((SUCCESS++))
    continue
  fi

  # Backup existing CI if upgrading
  if [ -n "$EXISTS" ] && $UPGRADE; then
    backup_ci "$repo" "$EXISTS"
  fi

  ENCODED=$(echo "$WF" | python3 -c "import sys,base64; print(base64.b64encode(sys.stdin.read().encode()).decode())")

  # Deploy with retry logic
  DEPLOY_CMD=""
  if [ -n "$EXISTS" ]; then
    DEPLOY_CMD="gh api \"repos/GlacierEQ/$repo/contents/.github/workflows/ci.yml\" \
      -X PUT -f message=\"ci: upgrade to Spiral Engine self-hosted CI\" \
      -f content=\"$ENCODED\" -f sha=\"$EXISTS\" -f branch=\"$DEFAULT\" 2>&1"
  else
    DEPLOY_CMD="gh api \"repos/GlacierEQ/$repo/contents/.github/workflows/ci.yml\" \
      -X PUT -f message=\"ci: add Spiral Engine self-hosted CI\" \
      -f content=\"$ENCODED\" -f branch=\"$DEFAULT\" 2>&1"
  fi

  if retry_command "$DEPLOY_CMD"; then
    log SUCCESS "$repo ($LANG) deployed successfully"
    ((SUCCESS++))
  else
    log ERROR "$repo deployment failed after $MAX_RETRIES attempts"
    ((FAIL++))
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ Deployed: $SUCCESS${NC} | ${YELLOW}⏭️  Skipped: $SKIP${NC} | ${RED}❌ Failed: $FAIL${NC} | ${BLUE}🔍 Validated: $VALIDATE${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Log saved to: $LOG_FILE"
echo "Backups saved to: $BACKUP_DIR"