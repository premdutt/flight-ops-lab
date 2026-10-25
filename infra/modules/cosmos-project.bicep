// One project's database, containers and data access inside the shared account
param accountName string
param databaseName string
param throughput int = 400
param principalIds array

resource acct 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: accountName
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: acct
  name: databaseName
  properties: {
    resource: { id: databaseName }
    options: { throughput: throughput }   // shared by the containers below
  }
}

// Agent Framework's checkpoint store uses /workflow_name as its partition key
resource checkpoints 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: db
  name: 'checkpoints'
  properties: { resource: { id: 'checkpoints', partitionKey: { paths: [ '/workflow_name' ], kind: 'Hash' } } }
}

resource memory 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: db
  name: 'memory'
  properties: { resource: { id: 'memory', partitionKey: { paths: [ '/id' ], kind: 'Hash' } } }
}

resource requests 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: db
  name: 'requests'
  properties: { resource: { id: 'requests', partitionKey: { paths: [ '/user_id' ], kind: 'Hash' } } }
}

// Cosmos DB Built-in Data Contributor, scoped to this database only
resource dataRoles 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = [for p in principalIds: {
  parent: acct
  name: guid(acct.id, databaseName, p, 'data-contributor')
  properties: {
    roleDefinitionId: '${acct.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: p
    scope: '${acct.id}/dbs/${databaseName}'
  }
  dependsOn: [ db ]
}]

output endpoint string = acct.properties.documentEndpoint
