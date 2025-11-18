import notebookutils
import sempy.fabric as fabric

def get_workspace_id(workspace_name):
    """Get workspace ID from workspace name"""
    if not workspace_name:
        return None
    try:
        return fabric.resolve_workspace_id(workspace_name)
    except Exception as e:
        print(f"Error getting workspace ID: {e}")
        return None

def create_lakehouse_if_not_existsv2(lakehouse_name, workspace_name=None):
    """
    Create a lakehouse if it doesn't exist.
    
    Args:
        lakehouse_name: Name of the lakehouse
        workspace_name: Optional workspace name. If None, uses current workspace
        
    Returns:
        1 if successful (lakehouse exists or was created)
        0 if failed
    """
    # Get workspace ID if workspace name is provided
    workspace_id = None
    if workspace_name:
        workspace_id = get_workspace_id(workspace_name)
        if workspace_id is None:
            print(f"Workspace '{workspace_name}' not found - returning 0")
            return 0
    
    print(f"Attempting to get lakehouse '{lakehouse_name}' with workspace_id: {workspace_id}")
    try:
        notebookutils.lakehouse.get(lakehouse_name, workspaceId=workspace_id)
        print("Lakehouse found - returning 1")
        return 1
    except Exception as e:
        print(f"Lakehouse not found: {e}, attempting to create...")
        try:
            notebookutils.lakehouse.create(
                lakehouse_name,
                workspaceId=workspace_id,
                definition={"enableSchemas": True}
            )
            notebookutils.lakehouse.get(lakehouse_name, workspaceId=workspace_id)
            print("Lakehouse created - returning 1")
            return 1
        except Exception as e:
            print(f"Error creating lakehouse: {e} - returning 0")
            return 0
