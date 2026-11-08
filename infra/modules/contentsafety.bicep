// infra/modules/contentsafety.bicep
param name string
param location string

resource cs 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  kind:'ContentSafety'
  sku:{ name:'F0'}
  tags:{project:'ai'}
  properties:{
    customSubDomainName:name
    disableLocalAuth:true
    publicNetworkAccess:'Enabled'
  }
}

output name string = cs.name
output endpoint string = cs.properties.endpoint
