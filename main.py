from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import uuid
import os
import asyncio

app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    url: str
    type: str   # "video" or "audio"
    use_cookies: bool = False  # optional flag for login-required videos


@app.post("/download")
async def download_media(data: DownloadRequest):
    if not data.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    download_folder = "downloads"
    os.makedirs(download_folder, exist_ok=True)

    file_id = uuid.uuid4().hex
    output_template = os.path.join(download_folder, f"{file_id}.%(ext)s")

    if data.type == "video":
        format_choice = "best[ext=mp4]/best"
    elif data.type == "audio":
        format_choice = "bestaudio/best"
    else:
        raise HTTPException(status_code=400, detail="type must be 'audio' or 'video'")

    # yt-dlp options
    ydl_opts = {
        "format": format_choice,
        "outtmpl": output_template,
    }

    # Add cookies if requested
    if data.use_cookies:
        # Requires you to have cookies.txt in project root (export from browser)
        cookies_file = "cookies.txt"
        if not os.path.exists(cookies_file):
            raise HTTPException(status_code=400, detail="Cookie file not found")
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data.url)
            file_path = ydl.prepare_filename(info).replace("\\", "/")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=500, detail="Download failed")

        return {
            "status": "success",
            "title": info.get("title"),
            "type": data.type,
            "download_url": f"/file/{os.path.basename(file_path)}"
        }

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Download failed: {str(e)}. "
                   f"If video requires login, set `use_cookies` to true and provide cookies.txt"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/file/{filename}")
async def serve_file(filename: str):
    file_path = os.path.join("downloads", filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Schedule file deletion (asynchronous)
    asyncio.create_task(delete_file_after_delay(file_path, delay=10))

    return FileResponse(file_path, filename=filename)


async def delete_file_after_delay(file_path: str, delay: int = 10):
    await asyncio.sleep(delay)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Deleted: {file_path}")
        except Exception as e:
            print(f"Delete failed: {e}")
