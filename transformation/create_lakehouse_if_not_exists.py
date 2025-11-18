import notebookutils
def create_lakehouse_if_not_exists(lakehouse_name):
    try:
        notebookutils.lakehouse.get(lakehouse_name)
        return 1
    except:
        try:
            notebookutils.lakehouse.create(lakehouse_name,definition={"enableSchemas": True})
            notebookutils.lakehouse.get(lakehouse_name)
            return 1
        except:
            return 0
