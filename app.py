from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can restrict later to only your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 👇 Base URL (change via environment variable in Render)
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

@app.get("/download")
async def download(url: str = Query(..., description="Video URL to download")):
    video_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "best[height<=720]/best",  # Limit to 720p for faster downloads
        "outtmpl": output_path,
        "noplaylist": True,
        "no_warnings": False,
        "extractaudio": False,
        "audioformat": "mp3",
        "embed_subs": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
    }

    try:
        logger.info(f"Processing URL: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First, extract info without downloading to check if it's accessible
            try:
                info = ydl.extract_info(url, download=False)
            except yt_dlp.DownloadError as e:
                error_msg = str(e).lower()
                
                # Handle specific error cases
                if "private video" in error_msg or "sign in" in error_msg:
                    return JSONResponse({"error": "This video is private or requires authentication."}, status_code=400)
                elif "video unavailable" in error_msg:
                    return JSONResponse({"error": "This video is unavailable or has been removed."}, status_code=400)
                elif "live stream" in error_msg and "not available" in error_msg:
                    return JSONResponse({"error": "Live streams cannot be downloaded while they are ongoing."}, status_code=400)
                elif "age-restricted" in error_msg:
                    return JSONResponse({"error": "This video is age-restricted and cannot be downloaded."}, status_code=400)
                else:
                    return JSONResponse({"error": f"Cannot access this video: {str(e)}"}, status_code=400)
            
            # If we got here, the video is accessible, now download it
            try:
                info = ydl.extract_info(url, download=True)
            except yt_dlp.DownloadError as e:
                return JSONResponse({"error": f"Download failed: {str(e)}"}, status_code=500)

            # Extract metadata
            title = info.get("title", "Unknown title")
            thumbnail = info.get("thumbnail")
            ext = info.get("ext", "mp4")
            filesize = info.get("filesize") or info.get("filesize_approx")
            platform = info.get("extractor", "Unknown")
            duration = info.get("duration")

            final_file = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
            
            if not os.path.exists(final_file):
                return JSONResponse({"error": "Download completed but file not found. Please try again."}, status_code=500)

            logger.info(f"Successfully downloaded: {title}")

            return JSONResponse({
                "id": video_id,
                "title": title,
                "thumbnail": thumbnail,
                "url": url,
                "platform": platform,
                "quality": info.get("format_note", "best available"),
                "format": ext,
                "duration": f"{duration // 60}:{duration % 60:02d}" if duration else "Unknown",
                "fileSize": f"{round(filesize/1024/1024, 2)} MB" if filesize else "Unknown",
                # 👇 Use BASE_URL instead of localhost
                "downloadUrl": f"{BASE_URL}/file/{video_id}.{ext}"
            })

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return JSONResponse({"error": f"An unexpected error occurred: {str(e)}"}, status_code=500)

@app.get("/file/{filename}")
async def get_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    return JSONResponse({"error": "File not found"}, status_code=404)

@app.get("/")
async def root():
    return {"message": "Clipster API is running!", "status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))  # Render sets PORT automatically
    uvicorn.run(app, host="0.0.0.0", port=port)
