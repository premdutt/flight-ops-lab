// infra/modules/search.bicep
param name string
param location string

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  sku: { name: 'free' }                       // only one free service per subscription
  tags: { project: 'ai' }
  identity: { type: 'SystemAssigned' }        // already on the service; keeps it for later Azure-side access
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: 'free'                    // free semantic ranker quota, already enabled
    disableLocalAuth: false                   // required by aadOrApiKey; the app still signs in with Entra ID
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http401WithBearerChallenge' } }
  }
}

output name string = search.name
output endpoint string = 'https://${name}.search.windows.net'
