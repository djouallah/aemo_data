import sempy_labs as labs
from sempy_labs.tom import TOMWrapper
import requests
import json
import notebookutils
import time

def check_dataset_exists(dataset_name, workspace_id):
    """
    Check if a dataset already exists in the workspace
    
    Args:
        dataset_name: Name of the dataset to check
        workspace_id: Workspace ID
    
    Returns:
        Boolean indicating if dataset exists
    """
    try:
        from sempy.fabric import list_datasets
        
        datasets = list_datasets(workspace=workspace_id)
        dataset_exists = dataset_name in datasets['Dataset Name'].values
        
        if dataset_exists:
            print(f"⚠️  Dataset '{dataset_name}' already exists in this workspace")
            return True
        else:
            print(f"✓ Dataset name '{dataset_name}' is available")
            return False
            
    except Exception as e:
        print(f"⚠️  Could not check for existing dataset: {str(e)}")
        return False


def get_workspace_id():
    """
    Get the current workspace ID automatically from Fabric context
    
    Returns:
        Workspace ID (GUID)
    """
    try:
        workspace_id = notebookutils.runtime.context.get("currentWorkspaceId")
        if not workspace_id:
            raise ValueError("Could not retrieve workspace ID from context")
        return workspace_id
    except Exception as e:
        print(f"❌ Error getting workspace ID: {str(e)}")
        raise


def get_lakehouse_id(lakehouse_name):
    """
    Get lakehouse ID by name using notebookutils
    
    Args:
        lakehouse_name: Name of the lakehouse
    
    Returns:
        Lakehouse ID (GUID)
    """
    try:
        lakehouse_artifact = notebookutils.lakehouse.get(lakehouse_name)
        lakehouse_id = lakehouse_artifact.id
        print(f"✓ Found lakehouse '{lakehouse_name}': {lakehouse_id}")
        return lakehouse_id
        
    except Exception as e:
        print(f"❌ Error finding lakehouse '{lakehouse_name}': {str(e)}")
        raise


def list_required_tables(bim_content, schema_name):
    """
    List all tables that will be required from the BIM file
    
    Args:
        bim_content: Dictionary containing the BIM content
        schema_name: Schema name that will be used
    
    Returns:
        List of required table names
    """
    required_tables = []
    if 'model' in bim_content and 'tables' in bim_content['model']:
        for table in bim_content['model']['tables']:
            if 'partitions' in table:
                for partition in table['partitions']:
                    if 'source' in partition and 'entityName' in partition['source']:
                        entity_name = partition['source']['entityName']
                        table_name = entity_name.split('.')[-1]
                        required_tables.append(table_name)
    
    if required_tables:
        print(f"Required tables in '{schema_name}' schema:")
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


def update_lakehouse_source(bim_content, workspace_id, lakehouse_id, schema_name):
    """
    Update the DirectLake data source with workspace, lakehouse IDs, and schema name
    
    Args:
        bim_content: Dictionary containing the BIM content
        workspace_id: Target workspace GUID
        lakehouse_id: Target lakehouse GUID
        schema_name: Schema name to use (e.g., 'temp', 'dbo', 'staging')
    
    Returns:
        Tuple of (modified BIM content, old expression name)
    """
    new_url = f"https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}"
    
    if 'model' in bim_content and 'expressions' in bim_content['model']:
        for expr in bim_content['model']['expressions']:
            if expr['name'] == 'DirectLake - temp':
                old_name = expr['name']
                expr['expression'] = [
                    "let",
                    f"    Source = AzureStorage.DataLake(\"{new_url}\", [HierarchicalNavigation=true])",
                    "in",
                    "    Source"
                ]
                # Keep the same expression name to avoid breaking partition references
                # Or update it and return the old name so we can update partitions
                print(f"✓ Updated DirectLake source")
                print(f"  - New URL: {new_url}")
                print(f"  - Schema: {schema_name}")
                print(f"  - Expression name: {old_name}")
                return bim_content, old_name
    
    raise ValueError("DirectLake expression 'DirectLake - temp' not found in BIM file")


def update_table_partitions(bim_content, schema_name, expression_name):
    """
    Update all table partitions to use the specified schema and verify expression source
    
    Args:
        bim_content: Dictionary containing the BIM content
        schema_name: Schema name to use
        expression_name: Name of the DirectLake expression to reference
    
    Returns:
        Modified BIM content
    """
    if 'model' in bim_content and 'tables' in bim_content['model']:
        tables_updated = 0
        print(f"Updating partition sources:")
        for table in bim_content['model']['tables']:
            if 'partitions' in table:
                for partition in table['partitions']:
                    if 'source' in partition:
                        # Update schemaName to new schema (keep the property as-is)
                        if 'schemaName' in partition['source']:
                            partition['source']['schemaName'] = schema_name
                        
                        # Keep entityName as-is (don't modify it at all)
                        entity_name = partition['source'].get('entityName', 'unknown')
                        print(f"  {table['name']:15} → {schema_name}.{entity_name}")
                        
                        # Ensure expressionSource matches the expression name
                        if 'expressionSource' in partition['source']:
                            partition['source']['expressionSource'] = expression_name
                            tables_updated += 1
        
        print(f"✓ Updated {tables_updated} table partition(s)")
        print(f"  - Schema: '{schema_name}'")
        print(f"  - Expression source: '{expression_name}'")
    
    return bim_content


def deploy_model(lakehouse_name, schema_name, dataset_name, bim_url, wait_seconds=10):
    """
    Main deployment function
    
    Args:
        lakehouse_name: Name of the lakehouse to connect to
        schema_name: Schema name to use (e.g., 'temp', 'dbo', 'aemoo')
        dataset_name: Name for the deployed semantic model
        bim_url: URL to the BIM file on GitHub
        wait_seconds: Seconds to wait for permission propagation (default: 30)
    
    Returns:
        Dictionary with deployment results or 0 for failure
    """
    print("=" * 70)
    print("Power BI Semantic Model Deployment")
    print("=" * 70)
    
    try:
        # Step 1: Get workspace ID automatically
        print("\n[Step 1/7] Getting workspace information...")
        workspace_id = get_workspace_id()
        print(f"✓ Workspace ID: {workspace_id}")
        
        # Step 2: Check if dataset already exists
        print(f"\n[Step 2/7] Checking if dataset '{dataset_name}' exists...")
        dataset_exists = check_dataset_exists(dataset_name, workspace_id)
        
        if dataset_exists:
            print(f"\n✓ Dataset '{dataset_name}' already exists - skipping deployment")
            print(f"   Proceeding directly to refresh...")
            
            # Skip to refresh
            print("\n[Step 8/9] Waiting for permission propagation...")
            print("   Allowing time for any recent changes to propagate...")
            if wait_seconds > 0:
                for i in range(wait_seconds, 0, -5):
                    print(f"   ⏳ {i} seconds remaining...")
                    time.sleep(min(5, i))
                print("✓ Wait complete")
            else:
                print("✓ Skipping wait (wait_seconds=0)")
            
            # Refresh the existing model
            print("\n[Step 9/9] Refreshing semantic model...")
            print("   Loading data from lakehouse via DirectLake...")
            
            labs.refresh_semantic_model(
                dataset=dataset_name,
                workspace=workspace_id
            )
            
            print(f"✓ Successfully refreshed semantic model")
            
            print("\n" + "=" * 70)
            print("🎉 Refresh Completed Successfully!")
            print("=" * 70)
            print(f"\nDataset Name:     {dataset_name}")
            print(f"Workspace ID:     {workspace_id}")
            print("\n✓ Your semantic model has been refreshed!")
            print("=" * 70)
            
            return {
                'status': 'refreshed',
                'dataset_name': dataset_name,
                'workspace_id': workspace_id
            }
        
        # Step 3: Get lakehouse ID
        print(f"\n[Step 3/7] Finding lakehouse '{lakehouse_name}'...")
        lakehouse_id = get_lakehouse_id(lakehouse_name)
        
        # Step 4: Download BIM from GitHub
        print("\n[Step 4/7] Downloading BIM file from GitHub...")
        bim_content = download_bim_from_github(bim_url)
        
        # Step 5: Show required tables
        print(f"\n[Step 5/7] Listing required tables...")
        list_required_tables(bim_content, schema_name)
        
        # Step 6: Update lakehouse connection and schema
        print(f"\n[Step 6/7] Updating DirectLake connection and schema...")
        modified_bim, expression_name = update_lakehouse_source(bim_content, workspace_id, lakehouse_id, schema_name)
        modified_bim = update_table_partitions(modified_bim, schema_name, expression_name)
        
        # Update model name
        modified_bim['name'] = dataset_name
        modified_bim['id'] = dataset_name
        print(f"✓ Set model name to: {dataset_name}")
        
        # Step 7: Deploy to Fabric workspace
        print("\n[Step 7/7] Deploying semantic model...")
        print("   This may take a moment...")
        
        # Deploy using create_semantic_model_from_bim
        labs.create_semantic_model_from_bim(
            dataset=dataset_name,
            bim_file=modified_bim,
            workspace=workspace_id
        )
        
        print(f"✓ Successfully deployed semantic model")
        
        # Step 8: Wait for permission propagation
        print("\n[Step 8/9] Waiting for permission propagation...")
        print("   Allowing time for the semantic model to receive lakehouse access...")
        if wait_seconds > 0:
            for i in range(wait_seconds, 0, -5):
                print(f"   ⏳ {i} seconds remaining...")
                time.sleep(min(5, i))
            print("✓ Permission propagation wait complete")
        else:
            print("✓ Skipping wait (wait_seconds=0)")
        
        # Step 9: Refresh the model
        print("\n[Step 9/9] Refreshing semantic model...")
        print("   Loading data from lakehouse via DirectLake...")
        
        labs.refresh_semantic_model(
            dataset=dataset_name,
            workspace=workspace_id
        )
        
        print(f"✓ Successfully refreshed semantic model")
        
        print("\n" + "=" * 70)
        print("🎉 Deployment Completed Successfully!")
        print("=" * 70)
        print(f"\nDataset Name:     {dataset_name}")
        print(f"Workspace ID:     {workspace_id}")
        print(f"Lakehouse:        {lakehouse_name}")
        print(f"Lakehouse ID:     {lakehouse_id}")
        print(f"Schema:           {schema_name}")
        print("\n✓ Your semantic model is now ready to use in Power BI!")
        print("=" * 70)
        
        return 1
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ Deployment Failed")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print("\nTroubleshooting:")
        print(f"1. Verify lakehouse '{lakehouse_name}' exists in this workspace")
        print(f"2. Ensure lakehouse contains required tables in '{schema_name}' schema:")
        print(f"   - {schema_name}.calendar")
        print(f"   - {schema_name}.duid")
        print(f"   - {schema_name}.summary")
        print(f"   - {schema_name}.mstdatetime")
        print("3. Check you have contributor permissions in the workspace")
        print("=" * 70)
        
        return 0
