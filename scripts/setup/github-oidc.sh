#!/usr/bin/env bash
# One-time: GitHub Actions identity with OIDC login for this repo. Safe to rerun.
set -euo pipefail
source ~/pg-flightops.env

GH_USER=premdutt
REPO=flight-ops-lab
ENV_NAME=lab
NAME=gh-flightops-lab
CRED_NAME=gh-env-lab-ids

# 1. App registration (reuse if it already exists)
APP_ID=$(az ad app list --display-name "$NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$NAME" --query appId -o tsv)
  echo "Created app $APP_ID"
else
  echo "Reusing app $APP_ID"
fi

# 2. Service principal (wait for it to propagate before assigning roles)
SP_OID=$(az ad sp show --id "$APP_ID" --query id -o tsv 2>/dev/null || true)
if [ -z "$SP_OID" ]; then
  az ad sp create --id "$APP_ID" -o none
  SP_OID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
  echo "Created service principal; waiting 30s for it to propagate"
  sleep 30
fi

# 3. Contributor on the project and platform resource groups
for G in "$RG" "$PLATFORM_RG"; do
  az role assignment create --assignee-object-id "$SP_OID" --assignee-principal-type ServicePrincipal \
    --role Contributor --scope "$(az group show -n "$G" --query id -o tsv)" -o none
  echo "Contributor on $G"
done

# 4. Federated credential
# GitHub presents an immutable-ID subject:
#   repo:<owner>@<ownerId>/<repo>@<repoId>:environment:<env>
OWNER_ID=$(gh api "users/$GH_USER" --jq .id)
REPO_ID=$(gh api "repos/$GH_USER/$REPO" --jq .id)
SUBJECT="repo:$GH_USER@$OWNER_ID/$REPO@$REPO_ID:environment:$ENV_NAME"
echo "OIDC subject: $SUBJECT"

if ! az ad app federated-credential list --id "$APP_ID" --query "[].name" -o tsv | grep -qx "$CRED_NAME"; then
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"$CRED_NAME\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$SUBJECT\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
  echo "Federated credential created"
else
  echo "Federated credential already exists"
fi

# 5. GitHub secrets (identifiers only, no passwords)
gh secret set AZURE_CLIENT_ID --body "$APP_ID"
gh secret set AZURE_TENANT_ID --body "$(az account show --query tenantId -o tsv)"
gh secret set AZURE_SUBSCRIPTION_ID --body "$(az account show --query id -o tsv)"
gh secret set RG --body "$RG"

echo "Done. App ID: $APP_ID"