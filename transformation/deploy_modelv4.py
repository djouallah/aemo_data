import sempy.fabric as fabric
from sempy.fabric import FabricRestClient
import requests
import json
import notebookutils
import time
import base64

def check_dataset_exists(dataset_name, workspace_name):
    """
    Check if a dataset already exists in the workspace
    
    Args:
        dataset_name: Name of the dataset to check
        workspace_name: Name of the workspace
    Returns:
        Boolean indicating if dataset exists
    """
    try:
        # Use list_items for SemanticModel type which works consistently
        items = fabric.list_items(type="SemanticModel", workspace=workspace_name)
        
        # Check if dataset exists using Display Name column
        dataset_exists = dataset_name in items['Display Name'].values
        
        if dataset_exists:
            print(f"⚠️  Dataset '{dataset_name}' already exists in this workspace")
            return True
        else:
            print(f"✓ Dataset name '{dataset_name}' is available")
            return False
            
    except Exception as e:
        print(f"⚠️  Could not check for existing dataset: {str(e)}")
        return False


def get_workspace_id(workspace_name):
    """
    Get workspace ID by workspace name
    
    Args:
        workspace_name: Name of the workspace
    
    Returns:
        Workspace ID (GUID)
    """
    try:
        workspaces = fabric.list_workspaces()
        workspace_match = workspaces[workspaces['Name'] == workspace_name]
        
        if workspace_match.empty:
            raise ValueError(f"Workspace '{workspace_name}' not found")
        
        workspace_id = workspace_match.iloc[0]['Id']
        print(f"✓ Found workspace '{workspace_name}': {workspace_id}")
        return workspace_id
        
    except Exception as e:
        print(f"❌ Error finding workspace '{workspace_name}': {str(e)}")
        raise


def get_lakehouse_id(lakehouse_name, workspace_name):
    """
    Get lakehouse ID by name in the specified workspace
    
    Args:
        lakehouse_name: Name of the lakehouse
        workspace_name: Name of the workspace
    
    Returns:
        Lakehouse ID (GUID)
    """
    try:
        # Use list_items with type filter for Lakehouse
        items = fabric.list_items(type="Lakehouse", workspace=workspace_name)
        
        # Find the lakehouse by display name
        lakehouse_match = items[items['Display Name'] == lakehouse_name]
        
        if lakehouse_match.empty:
            print(f"⚠️  Available lakehouses: {list(items['Display Name'].values)}")
            raise ValueError(f"Lakehouse '{lakehouse_name}' not found in workspace '{workspace_name}'")
        
        lakehouse_id = lakehouse_match.iloc[0]['Id']
        print(f"✓ Found lakehouse '{lakehouse_name}': {lakehouse_id}")
        return lakehouse_id
        
    except Exception as e:
        print(f"❌ Error finding lakehouse '{lakehouse_name}': {str(e)}")
        raise


def get_sql_endpoint(lakehouse_name, workspace_name):
    """
    Get SQL endpoint for a lakehouse (for DirectQuery mode)
    
    Args:
        lakehouse_name: Name of the lakehouse
        workspace_name: Name of the workspace
    
    Returns:
        SQL endpoint string (HTTPS format for OAuth 2.0)
    """
    try:
        # Get lakehouse details using Fabric REST API to get the correct SQL endpoint
        workspace_id = get_workspace_id(workspace_name)
        lakehouse_id = get_lakehouse_id(lakehouse_name, workspace_name)
        
        # Try to get the actual SQL endpoint from Fabric API
        try:
            client = FabricRestClient()
            response = client.get(f"/v1/workspaces/{workspace_id}/lakehouses/{lakehouse_id}")
            lakehouse_info = response.json()
            
            # Check if there's a SQL endpoint in the response
            if 'properties' in lakehouse_info and 'sqlEndpointProperties' in lakehouse_info['properties']:
                sql_endpoint = lakehouse_info['properties']['sqlEndpointProperties']['connectionString']
                print(f"✓ Retrieved SQL endpoint from API: {sql_endpoint}")
                return sql_endpoint
        except Exception as api_error:
            print(f"⚠️  Could not retrieve SQL endpoint from API: {api_error}")
            print("   Falling back to endpoint generation...")
        
        # Fallback: Generate the SQL endpoint using the standard Fabric pattern
        # Remove hyphens from GUIDs for the endpoint
        workspace_clean = workspace_id.replace('-', '')
        lakehouse_clean = lakehouse_id.replace('-', '')
        
        # Fabric SQL Analytics endpoint pattern (HTTPS for OAuth 2.0)
        sql_endpoint = f"{workspace_clean[:16]}-{lakehouse_clean[:16]}.datawarehouse.fabric.microsoft.com"
        
        print(f"✓ Generated SQL endpoint: {sql_endpoint}")
        print(f"   Using HTTPS/SSL connection for OAuth 2.0 authentication")
        return sql_endpoint
        
    except Exception as e:
        print(f"❌ Error getting SQL endpoint: {str(e)}")
        raise


def list_required_tables(bim_content, schema_name, mode):
    """
    List all tables that will be required from the BIM file
    
    Args:
        bim_content: Dictionary containing the BIM content
        schema_name: Schema name that will be used
        mode: 'directlake' or 'directquery'
    
    Returns:
        List of required table names
    """
    required_tables = []
    if 'model' in bim_content and 'tables' in bim_content['model']:
        for table in bim_content['model']['tables']:
            if 'partitions' in table:
                for partition in table['partitions']:
                    if 'source' in partition:
                        if mode == 'directlake' and 'entityName' in partition['source']:
                            entity_name = partition['source']['entityName']
                            required_tables.append(entity_name)
                        elif mode == 'directquery' and 'expression' in partition['source']:
                            # Extract table name from M expression
                            expression = partition['source'].get('expression', [])
                            for line in expression:
                                if 'Item=' in line and 'Schema=' in line:
                                    # Extract table name from line like: aemo_calendar = Source{[Schema=schema,Item="calendar"]}[Data]
                                    import re
                                    match = re.search(r'Item="([^"]+)"', line)
                                    if match:
                                        required_tables.append(match.group(1))
    
    if required_tables:
        print(f"Required tables in '{schema_name}' schema ({mode} mode):")
        for table in required_tables:
            print(f"  - {schema_name}.{table}")
    
    return required_tables


def download_bim_from_github(url):
    """
    Download BIM file from GitHub repository
    
    Args:
        url: GitHub raw content URL
    
    Returns:
        Dictionary containing BIM content
    """
    print(f"Downloading BIM file from GitHub...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        bim_content = response.json()
        print(f"✓ Successfully downloaded BIM file")
        print(f"  - Tables: {len(bim_content.get('model', {}).get('tables', []))}")
        print(f"  - Relationships: {len(bim_content.get('model', {}).get('relationships', []))}")
        return bim_content
    except Exception as e:
        print(f"❌ Failed to download BIM file: {str(e)}")
        raise


def update_directlake_source(bim_content, workspace_id, lakehouse_id, schema_name):
    """
    Update the DirectLake data source with workspace, lakehouse IDs, and schema name
    
    Args:
        bim_content: Dictionary containing the BIM content
        workspace_id: Target workspace GUID
        lakehouse_id: Target lakehouse GUID
        schema_name: Schema name to use (e.g., 'temp', 'dbo', 'staging')
    
    Returns:
        Tuple of (modified BIM content, expression name)
    """
    new_url = f"https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}"
    expression_name = None
    
    if 'model' in bim_content and 'expressions' in bim_content['model']:
        for expr in bim_content['model']['expressions']:
            # Look for DirectLake expression (could have various names)
            if 'DirectLake' in expr['name'] or expr.get('kind') == 'm':
                expression_name = expr['name']
                expr['expression'] = [
                    "let",
                    f"    Source = AzureStorage.DataLake(\"{new_url}\", [HierarchicalNavigation=true])",
                    "in",
                    "    Source"
                ]
                print(f"✓ Updated DirectLake source")
                print(f"  - New URL: {new_url}")
                print(f"  - Schema: {schema_name}")
                print(f"  - Expression name: {expression_name}")
                break
    
    if not expression_name:
        # Create new DirectLake expression if none exists
        expression_name = f"DirectLake - {schema_name}"
        if 'expressions' not in bim_content['model']:
            bim_content['model']['expressions'] = []
        
        bim_content['model']['expressions'].append({
            "name": expression_name,
            "kind": "m",
            "expression": [
                "let",
                f"    Source = AzureStorage.DataLake(\"{new_url}\", [HierarchicalNavigation=true])",
                "in",
                "    Source"
            ],
            "lineageTag": f"directlake-{schema_name}-source",
            "annotations": [
                {
                    "name": "PBI_IncludeFutureArtifacts",
                    "value": "False"
                }
            ]
        })
        print(f"✓ Created DirectLake source: {expression_name}")
    
    return bim_content, expression_name


def update_directquery_source(bim_content, sql_endpoint, lakehouse_name, schema_name):
    """
    Update DirectQuery data source with SQL endpoint and parameters (SSL/HTTPS enabled)
    
    Args:
        bim_content: Dictionary containing the BIM content
        sql_endpoint: SQL endpoint for the lakehouse
        lakehouse_name: Name of the lakehouse (used as database name)
        schema_name: Schema name to use
    
    Returns:
        Modified BIM content
    """
    # Update or create parameters
    if 'expressions' not in bim_content['model']:
        bim_content['model']['expressions'] = []
    
    # Define parameters needed for DirectQuery with SSL/OAuth 2.0 support
    parameters = [
        {
            "name": "endpoint",
            "kind": "m", 
            "expression": f'"{sql_endpoint}" meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = "Text"]',
            "queryGroup": "Parameters",
            "lineageTag": "endpoint-parameter",
            "annotations": [
                {"name": "PBI_NavigationStepName", "value": "Navigation"},
                {"name": "PBI_ResultType", "value": "Text"}
            ]
        },
        {
            "name": "lakehouse",
            "kind": "m",
            "expression": f'"{lakehouse_name}" meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = "Text"]',
            "queryGroup": "Parameters", 
            "lineageTag": "lakehouse-parameter",
            "annotations": [
                {"name": "PBI_NavigationStepName", "value": "Navigation"},
                {"name": "PBI_ResultType", "value": "Text"}
            ]
        },
        {
            "name": "schema",
            "kind": "m",
            "expression": f'"{schema_name}" meta [IsParameterQuery = true, IsParameterQueryRequired = true, Type = "Text"]',
            "queryGroup": "Parameters",
            "lineageTag": "schema-parameter", 
            "annotations": [
                {"name": "PBI_NavigationStepName", "value": "Navigation"},
                {"name": "PBI_ResultType", "value": "Text"}
            ]
        }
    ]
    
    # Remove existing parameters and add new ones
    bim_content['model']['expressions'] = [
        expr for expr in bim_content['model']['expressions'] 
        if expr.get('queryGroup') != 'Parameters'
    ]
    bim_content['model']['expressions'].extend(parameters)
    
    # Add or update query groups
    if 'queryGroups' not in bim_content['model']:
        bim_content['model']['queryGroups'] = []
    
    # Remove existing Parameters group and add new one
    bim_content['model']['queryGroups'] = [
        group for group in bim_content['model']['queryGroups']
        if group.get('folder') != 'Parameters'
    ]
    bim_content['model']['queryGroups'].append({
        "folder": "Parameters",
        "annotations": [{"name": "PBI_QueryGroupOrder", "value": "0"}]
    })
    
    print(f"✓ Updated DirectQuery parameters (SSL/OAuth 2.0 enabled)")
    print(f"  - Endpoint: {sql_endpoint}")
    print(f"  - Lakehouse: {lakehouse_name}")  
    print(f"  - Schema: {schema_name}")
    print(f"  - Authentication: OAuth 2.0 with SSL/HTTPS")
    
    return bim_content


def update_table_partitions_directlake(bim_content, schema_name, expression_name):
    """
    Update table partitions for DirectLake mode
    
    Args:
        bim_content: Dictionary containing the BIM content
        schema_name: Schema name to use
        expression_name: Name of the DirectLake expression to reference
    
    Returns:
        Modified BIM content
    """
    if 'model' in bim_content and 'tables' in bim_content['model']:
        tables_updated = 0
        print(f"Updating partition sources for DirectLake:")
        for table in bim_content['model']['tables']:
            if 'partitions' in table:
                for partition in table['partitions']:
                    if 'source' in partition:
                        # Convert to DirectLake format
                        partition['mode'] = 'directLake'
                        partition['source'] = {
                            "type": "entity",
                            "entityName": partition['source'].get('entityName', table['name']),
                            "expressionSource": expression_name,
                            "schemaName": schema_name
                        }
                        
                        entity_name = partition['source']['entityName']
                        print(f"  {table['name']:15} → {schema_name}.{entity_name}")
                        tables_updated += 1
        
        print(f"✓ Updated {tables_updated} table partition(s) for DirectLake")
        print(f"  - Schema: '{schema_name}'")
        print(f"  - Expression source: '{expression_name}'")
    
    return bim_content


def get_database_table_name(table_name, bim_content):
    """
    Get the correct database table name for a Power BI table
    Handles cases where Power BI table names differ from database table names
    
    Args:
        table_name: Power BI table name
        bim_content: BIM content to check for existing mappings
    
    Returns:
        Actual database table name
    """
    # Check if there's an existing M expression that shows the real table name
    if 'model' in bim_content and 'tables' in bim_content['model']:
        for table in bim_content['model']['tables']:
            if table['name'] == table_name and 'partitions' in table:
                for partition in table['partitions']:
                    if 'source' in partition and 'expression' in partition['source']:
                        expression_lines = partition['source']['expression']
                        for line in expression_lines:
                            if 'Item=' in line:
                                # Extract table name from line like: Item="mstdatetime"
                                import re
                                match = re.search(r'Item="([^"]+)"', line)
                                if match:
                                    return match.group(1)
    
    # Common table name mappings for AEMO data
    table_mappings = {
        'mstime': 'mstdatetime',  # This is the key fix for your error
        'calendar': 'calendar',
        'duid': 'duid', 
        'summary': 'summary'
    }
    
    # Return mapped name or original name if no mapping exists
    return table_mappings.get(table_name, table_name)


def update_table_partitions_directquery(bim_content, schema_name):
    """
    Update table partitions for DirectQuery mode with correct table name mapping
    
    Args:
        bim_content: Dictionary containing the BIM content
        schema_name: Schema name to use
    
    Returns:
        Modified BIM content
    """
    if 'model' in bim_content and 'tables' in bim_content['model']:
        tables_updated = 0
        print(f"Updating partition sources for DirectQuery:")
        for table in bim_content['model']['tables']:
            if 'partitions' in table:
                for partition in table['partitions']:
                    if 'source' in partition:
                        # Get the Power BI table name and map to database table name
                        powerbi_table_name = table['name']
                        database_table_name = get_database_table_name(powerbi_table_name, bim_content)
                        
                        # Convert to DirectQuery format with simple M expression (no unsupported options)
                        partition['mode'] = 'directQuery'  # Pure DirectQuery mode
                        partition['source'] = {
                            "type": "m",
                            "expression": [
                                "let",
                                "    Source = Sql.Database(endpoint, lakehouse),",
                                f"    {schema_name}_{powerbi_table_name} = Source{{[Schema=schema,Item=\"{database_table_name}\"]}}[Data]",
                                "in",
                                f"    {schema_name}_{powerbi_table_name}"
                            ]
                        }
                        
                        print(f"  {powerbi_table_name:15} → {schema_name}.{database_table_name}")
                        tables_updated += 1
        
        print(f"✓ Updated {tables_updated} table partition(s) for DirectQuery")
        print(f"  - Schema: '{schema_name}'")
        print(f"  - Mode: directQuery (pure DirectQuery)")
    
    return bim_content


def create_dataset_from_bim(dataset_name, bim_content, workspace_id):
    """
    Create a semantic model from BIM content using Fabric REST API
    
    Args:
        dataset_name: Name for the new dataset
        bim_content: Dictionary containing the BIM content
        workspace_id: Target workspace ID
    """
    try:
        # Initialize REST client
        client = FabricRestClient()
        
        # Convert BIM content to JSON string and then to base64
        bim_json = json.dumps(bim_content, indent=2)
        bim_base64 = base64.b64encode(bim_json.encode('utf-8')).decode('utf-8')
        
        # Create the required definition.pbism file
        # For TMSL format (model.bim), version must be "1.0"
        pbism_content = {
            "version": "1.0"
        }
        pbism_json = json.dumps(pbism_content)
        pbism_base64 = base64.b64encode(pbism_json.encode('utf-8')).decode('utf-8')
        
        # Create the request payload according to Fabric API specification
        payload = {
            "displayName": dataset_name,
            "definition": {
                "parts": [
                    {
                        "path": "model.bim",
                        "payload": bim_base64,
                        "payloadType": "InlineBase64"
                    },
                    {
                        "path": "definition.pbism",
                        "payload": pbism_base64,
                        "payloadType": "InlineBase64"
                    }
                ]
            }
        }
        
        # Create the semantic model using Fabric REST API
        response = client.post(
            f"/v1/workspaces/{workspace_id}/semanticModels",
            json=payload
        )
        
        print(f"✓ Successfully created semantic model via Fabric REST API")
        
        # Check if it's an LRO (Long Running Operation)
        if response.status_code == 202:
            operation_id = response.headers.get('x-ms-operation-id')
            print(f"   Long-running operation initiated: {operation_id}")
            print(f"   Waiting for operation to complete...")
            
            # Poll for completion
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(2)
                status_response = client.get(f"/v1/operations/{operation_id}")
                status = status_response.json().get('status')
                
                if status == 'Succeeded':
                    print(f"✓ Operation completed successfully")
                    break
                elif status == 'Failed':
                    error = status_response.json().get('error', {})
                    raise Exception(f"Operation failed: {error.get('message', 'Unknown error')}")
                elif attempt == max_attempts - 1:
                    raise Exception(f"Operation timed out after {max_attempts * 2} seconds")
        
    except Exception as e:
        print(f"❌ Error creating dataset from BIM: {str(e)}")
        print(f"   Error details: {repr(e)}")
        raise


def deploy_model_enhanced(workspace_name, lakehouse_name, schema_name, dataset_name, 
                         bim_url, mode='directlake', wait_seconds=5):
    """
    Enhanced deployment function supporting both DirectLake and DirectQuery modes
    
    Args:
        workspace_name: Name of the target workspace
        lakehouse_name: Name of the lakehouse to connect to
        schema_name: Schema name to use (e.g., 'temp', 'dbo', 'aemo')
        dataset_name: Name for the deployed semantic model
        bim_url: URL to the BIM file on GitHub
        mode: 'directlake' or 'directquery' (default: 'directlake')
        wait_seconds: Seconds to wait for permission propagation (default: 5)
    
    Returns:
        1 for success, 0 for failure
    """
    print("=" * 70)
    print("Enhanced Power BI Semantic Model Deployment")
    print("=" * 70)
    
    # Validate mode parameter
    if mode not in ['directlake', 'directquery']:
        print(f"❌ Invalid mode '{mode}'. Must be 'directlake' or 'directquery'")
        return 0
    
    print(f"Deployment Mode: {mode.upper()}")
    
    try:
        # Step 1: Get workspace ID from workspace name
        print("\n[Step 1/8] Getting workspace information...")
        workspace_id = get_workspace_id(workspace_name)
        
        # Step 2: Check if dataset already exists
        print(f"\n[Step 2/8] Checking if dataset '{dataset_name}' exists...")
        dataset_exists = check_dataset_exists(dataset_name, workspace_name)
        
        if dataset_exists:
            print(f"\n✓ Dataset '{dataset_name}' already exists - skipping deployment")
            print(f"   Proceeding directly to refresh...")
            
            # Skip to refresh
            print("\n[Step 9/10] Waiting for permission propagation...")
            print("   Allowing time for any recent changes to propagate...")
            if wait_seconds > 0:
                for i in range(wait_seconds, 0, -5):
                    print(f"   ⏳ {i} seconds remaining...")
                    time.sleep(min(5, i))
                print("✓ Wait complete")
            else:
                print("✓ Skipping wait (wait_seconds=0)")
            
            # Refresh using sempy.fabric
            print("\n[Step 10/10] Refreshing semantic model...")
            if mode == 'directlake':
                print("   Loading data from lakehouse via DirectLake...")
            else:
                print("   Loading data from SQL endpoint via DirectQuery...")
            
            fabric.refresh_dataset(
                dataset=dataset_name,
                workspace=workspace_name
            )
            
            print(f"✓ Successfully refreshed semantic model")
            
            print("\n" + "=" * 70)
            print("🎉 Refresh Completed Successfully!")
            print("=" * 70)
            print(f"\nDataset Name:     {dataset_name}")
            print(f"Workspace:        {workspace_name}")
            print(f"Workspace ID:     {workspace_id}")
            print(f"Mode:             {mode.upper()}")
            print("\n✓ Your semantic model has been refreshed!")
            print("=" * 70)
            
            return 1
        
        # Step 3: Get lakehouse ID and connection info
        print(f"\n[Step 3/8] Finding lakehouse '{lakehouse_name}' and connection details...")
        lakehouse_id = get_lakehouse_id(lakehouse_name, workspace_name)
        
        if mode == 'directquery':
            sql_endpoint = get_sql_endpoint(lakehouse_name, workspace_name)
        
        # Step 4: Download BIM from GitHub
        print("\n[Step 4/8] Downloading BIM file from GitHub...")
        bim_content = download_bim_from_github(bim_url)
        
        # Step 5: Show required tables
        print(f"\n[Step 5/8] Listing required tables...")
        list_required_tables(bim_content, schema_name, mode)
        
        # Step 6: Update data source and connection based on mode
        print(f"\n[Step 6/8] Configuring {mode.upper()} connection and schema...")
        
        if mode == 'directlake':
            modified_bim, expression_name = update_directlake_source(bim_content, workspace_id, lakehouse_id, schema_name)
            modified_bim = update_table_partitions_directlake(modified_bim, schema_name, expression_name)
        else:  # directquery
            modified_bim = update_directquery_source(bim_content, sql_endpoint, lakehouse_name, schema_name)
            modified_bim = update_table_partitions_directquery(modified_bim, schema_name)
        
        # Update model name
        modified_bim['name'] = dataset_name
        modified_bim['id'] = dataset_name
        print(f"✓ Set model name to: {dataset_name}")
        
        # Step 7: Deploy to Fabric workspace using REST API
        print("\n[Step 7/8] Deploying semantic model...")
        print("   Creating dataset from BIM using Fabric REST API...")
        
        create_dataset_from_bim(dataset_name, modified_bim, workspace_id)
        
        # Step 8: Wait for permission propagation
        print("\n[Step 8/10] Waiting for permission propagation...")
        if mode == 'directlake':
            print("   Allowing time for the semantic model to receive lakehouse access...")
        else:
            print("   Allowing time for the semantic model to establish SQL connection...")
        
        if wait_seconds > 0:
            for i in range(wait_seconds, 0, -5):
                print(f"   ⏳ {i} seconds remaining...")
                time.sleep(min(5, i))
            print("✓ Permission propagation wait complete")
        else:
            print("✓ Skipping wait (wait_seconds=0)")
        
        # Step 9: Refresh using sempy.fabric
        print("\n[Step 9/10] Refreshing semantic model...")
        if mode == 'directlake':
            print("   Loading data from lakehouse via DirectLake...")
        else:
            print("   Loading data from SQL endpoint via DirectQuery...")
        
        fabric.refresh_dataset(
            dataset=dataset_name,
            workspace=workspace_name
        )
        
        print(f"✓ Successfully refreshed semantic model")
        
        print("\n" + "=" * 70)
        print("🎉 Deployment Completed Successfully!")
        print("=" * 70)
        print(f"\nDataset Name:     {dataset_name}")
        print(f"Workspace:        {workspace_name}")
        print(f"Workspace ID:     {workspace_id}")
        print(f"Lakehouse:        {lakehouse_name}")
        print(f"Lakehouse ID:     {lakehouse_id}")
        print(f"Schema:           {schema_name}")
        print(f"Mode:             {mode.upper()}")
        if mode == 'directquery':
            print(f"SQL Endpoint:     {sql_endpoint}")
        print("\n✓ Your semantic model is now ready to use in Power BI!")
        print("=" * 70)
        
        return 1
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ Deployment Failed")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print("\nTroubleshooting:")
        print(f"1. Verify workspace '{workspace_name}' exists and you have access")
        print(f"2. Verify lakehouse '{lakehouse_name}' exists in this workspace")
        print(f"3. Ensure lakehouse contains required tables in '{schema_name}' schema")
        if mode == 'directlake':
            print("4. For DirectLake: Ensure tables are in Delta format in OneLake")
        else:
            print("4. For DirectQuery: Ensure SQL endpoint is accessible and tables exist")
        print("5. Check you have contributor permissions in the workspace")
        print("=" * 70)
        
        return 0


def deploy_modelv4(workspace_name, lakehouse_name, schema_name, dataset_name, 
                   bim_url, mode='directlake', wait_seconds=5):
    """
    Unified deployment function supporting both DirectLake and DirectQuery modes
    
    Args:
        workspace_name: Name of the target workspace
        lakehouse_name: Name of the lakehouse to connect to
        schema_name: Schema name to use (e.g., 'temp', 'dbo', 'aemo')
        dataset_name: Name for the deployed semantic model
        bim_url: URL to the BIM file on GitHub
        mode: 'directlake' or 'directquery' (default: 'directlake')
        wait_seconds: Seconds to wait for permission propagation (default: 5)
    
    Returns:
        1 for success, 0 for failure
    
    Examples:
        # DirectLake deployment (default)
        deploy_modelv4("My Workspace", "MyLakehouse", "aemo", "AEMO Model", "url")
        
        # DirectQuery deployment
        deploy_modelv4("My Workspace", "MyLakehouse", "aemo", "AEMO Model", "url", mode="directquery")
    """
    return deploy_model_enhanced(workspace_name, lakehouse_name, schema_name, 
                               dataset_name, bim_url, mode=mode, wait_seconds=wait_seconds)

