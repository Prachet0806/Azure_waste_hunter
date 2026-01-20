import os
import datetime
from azure.storage.blob import BlobServiceClient

def archive_report(report: str):
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not set")

    container = os.environ.get("REPORT_CONTAINER", "waste-reports")

    blob = BlobServiceClient.from_connection_string(conn)
    container_client = blob.get_container_client(container)

    try:
        container_client.create_container()
    except Exception:
        pass  # already exists

    name = f"reports/{datetime.date.today()}.md"
    container_client.upload_blob(name, report, overwrite=True)
