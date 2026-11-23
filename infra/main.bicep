// Deployed to rg-flightops-lab; Cosmos goes to the shared platform group
param suffix string
param platformRg string = 'rg-ai-platform'
param location string = resourceGroup().location
param principalIds array
param safetyLocation string = 'eastus'
param searchLocation string = 'eastus'


module cosmosAccount 'modules/cosmos-account.bicep' = {
  name: 'cosmos-account'
  scope: resourceGroup(platformRg)
  params: { name: 'cos-ai-${suffix}', location: location }
}

module cosmos 'modules/cosmos-project.bicep' = {
  name: 'cosmos-flightops'
  scope: resourceGroup(platformRg)
  params: {
    accountName: cosmosAccount.outputs.name
    databaseName: 'flightops'
    principalIds: principalIds
  }
}

module safety 'modules/contentsafety.bicep' = {
  name: 'contentsafety'
  scope: resourceGroup(platformRg)
  params: { name: 'cs-ai-${suffix}', location: safetyLocation }

}
// The free Search service already exists in eastus; a location can't be changed later
module search 'modules/search.bicep' = {
  name: 'search'
  scope: resourceGroup(platformRg)
  params: { name: 'srch-ai-${suffix}', location: searchLocation }
}

output cosmosEndpoint string = cosmos.outputs.endpoint
output safetyEndpoint string = safety.outputs.endpoint
output searchEndpoint string = search.outputs.endpoint
