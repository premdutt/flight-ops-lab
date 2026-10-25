#!/usr/bin/env bash
# One-time: GitHub Actions identity with OIDC login. Safe to rerun.
set -euo pipefail
source ~/pg-flightops.env
GH_USER=premdutt
NAME=gh-flightops-lab

APP_ID=$(az ad app list --display-name $NAME --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name $NAME --query appId -o tsv)
  echo "Created app $APP_ID"
else
  echo "Reusing app $APP_ID"
fi

SP_OID=$(az ad sp show --id "$APP_ID" --query id -o tsv 2>/dev/null || true)
if [ -z "$SP_OID" ]; then
  az ad sp create --id "$APP_ID" -o none
  SP_OID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
  echo "Created service principal; waiting 30s for it to propagate"
  sleep 30
fi

for G in "$RG" "$PLATFORM_RG"; do
  az role assignment create --assignee-object-id "$SP_OID" --assignee-principal-type ServicePrincipal \
    --role Contributor --scope "$(az group show -n "$G" --query id -o tsv)" -o none
  echo "Contributor on $G"
done

if ! az ad app federated-credential list --id "$APP_ID" --query "[].name" -o tsv | grep -qx gh-env-lab; then
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"gh-env-lab\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:$GH_USER/flight-ops-lab:environment:lab\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
  echo "Federated credential created"
else
  echo "Federated credential already exists"
fi

gh secret set AZURE_CLIENT_ID --body "$APP_ID"
gh secret set AZURE_TENANT_ID --body "$(az account show --query tenantId -o tsv)"
gh secret set AZURE_SUBSCRIPTION_ID --body "$(az account show --query id -o tsv)"
gh secret set RG --body "$RG"
echo "Done. App ID: $APP_ID"