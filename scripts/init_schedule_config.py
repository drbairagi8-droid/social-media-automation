import io
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from src.config import Config
from src.gdrive_manager import get_google_credentials


def main():
    config = Config()
    creds = get_google_credentials(config)
    drive = build("drive", "v3", credentials=creds)

    initial_config = {
        "all_posting_enabled": True,
        "slots": {
            "morning": {"enabled": True, "name": "Morning (07:00 AM IST)"},
            "afternoon": {"enabled": True, "name": "Afternoon (01:00 PM IST)"},
            "evening": {"enabled": True, "name": "Evening (07:00 PM IST)"},
        },
    }

    content_bytes = json.dumps(initial_config, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(content_bytes), mimetype="application/json", resumable=False)

    folder_id = config.gdrive_queue_folder_id
    query = f"name = 'schedule_config.json' and '{folder_id}' in parents and trashed = false"
    res = drive.files().list(q=query, fields="files(id, name)").execute()
    files = res.get("files", [])

    if files:
        f_id = files[0]["id"]
        drive.files().update(fileId=f_id, media_body=media).execute()
        print(f"Updated existing schedule_config.json in Drive (ID: {f_id})")
    else:
        meta = {
            "name": "schedule_config.json",
            "parents": [folder_id],
            "mimeType": "application/json",
        }
        c = drive.files().create(body=meta, media_body=media, fields="id").execute()
        print(f"Created new schedule_config.json in Drive (ID: {c['id']})")


if __name__ == "__main__":
    main()
