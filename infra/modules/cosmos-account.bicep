param name string
param location string

resource acct 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
name: name
  location: location
  tags: { project: 'ai' }
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    disableLocalAuth: true            // Entra ID only, no keys
    locations: [ { locationName: location, failoverPriority: 0 } ]
  }
}
output name string = acct.name
