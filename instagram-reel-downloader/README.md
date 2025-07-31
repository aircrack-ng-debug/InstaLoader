# Instagram Reel Downloader Microservice

A simple, containerized microservice to download Instagram Reels and Posts. It's designed to be called from automation workflows like n8n or used as a standalone service.

## Features

-   **Download via API**: Simple GET request to download a video.
-   **Direct Video Response**: Returns the MP4 file directly for easy processing.
-   **JSON Error Handling**: Provides clear JSON errors if a download fails, including `yt-dlp` output.
-   **Health Check**: A `/healthz` endpoint for monitoring.
-   **Authentication**: Optional API key protection.
-   **Containerized**: Ready for deployment with Docker.

---

## API Endpoints

### Health Check

-   **Endpoint**: `GET /healthz`
-   **Description**: Checks if the service is running and responsive.
-   **Success Response** (200 OK):
    ```json
    {
      "status": "ok"
    }
    ```

### Download Video

-   **Endpoint**: `GET /download?url=<instagram-url>`
-   **Description**: Downloads the video from the provided Instagram URL.
-   **Query Parameters**:
    -   `url` (required): The full URL of the Instagram Reel or Post (e.g., `https://www.instagram.com/p/C1a2b3c4d5e/`).
-   **Authentication (if `API_KEY` is set)**:
    -   Requires an `Authorization` header: `Authorization: Bearer <your-api-key>`
-   **Success Response** (200 OK):
    -   The raw MP4 video file.
-   **Error Response** (400, 401, 403, 500, 504):
    ```json
    {
      "error": "Descriptive error message.",
      "url": "The requested URL",
      "stdout": "Standard output from yt-dlp",
      "stderr": "Error output from yt-dlp"
    }
    ```

---

## Configuration

The service is configured via environment variables.

| Variable         | Description                                                                                                   | Default                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `PORT`           | The port the service will listen on. Gunicorn will bind to this port inside the container.                      | `8080`                                                      |
| `API_KEY`        | An optional secret key to protect the `/download` endpoint. If not set, the endpoint is public.                 | `null` (disabled)                                           |
| `COOKIES_PATH`   | Optional **container path** to a `cookies.txt` file for `yt-dlp` to use for logging into Instagram.             | `null` (not used)                                           |
| `YTDLP_FORMAT`   | The format string passed to `yt-dlp`'s `-f` flag. The default is optimized for high-quality MP4.                | `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best` |

---

## How to Run Locally (with Docker)

1.  **Build the Docker image:**
    ```bash
    docker build -t instagram-downloader .
    ```

2.  **Run the container:**

    *   **Without API Key:**
        ```bash
        docker run -d -p 8080:8080 --name insta-dl instagram-downloader
        ```

    *   **With API Key:**
        ```bash
        docker run -d -p 8080:8080 \
          -e API_KEY="your-secret-api-key" \
          --name insta-dl instagram-downloader
        ```

    *   **With a cookies file:**
        Place your `cookies.txt` file in the same directory. The command mounts it into the container and sets the `COOKIES_PATH` variable to the correct path *inside* the container.
        ```bash
        docker run -d -p 8080:8080 \
          -v "$(pwd)/cookies.txt:/app/cookies.txt" \
          -e COOKIES_PATH="/app/cookies.txt" \
          -e API_KEY="your-secret-api-key" \
          --name insta-dl instagram-downloader
        ```

---

## Example `curl` Commands

*   **Health Check:**
    ```bash
    curl http://localhost:8080/healthz
    ```

*   **Download a Reel (no auth):**
    ```bash
    # Make sure the service is running without an API_KEY
    curl -v --fail -o reel.mp4 "http://localhost:8080/download?url=https://www.instagram.com/reel/C2q3r4S5t6U/"
    ```

*   **Download a Reel (with auth):**
    ```bash
    # Make sure the service is running with API_KEY="my-secret"
    curl -v --fail -o reel.mp4 \
      -H "Authorization: Bearer my-secret" \
      "http://localhost:8080/download?url=https://www.instagram.com/reel/C2q3r4S5t6U/"
    ```

*   **Example of a failed download (e.g., invalid URL):**
    ```bash
    curl -H "Authorization: Bearer my-secret" \
      "http://localhost:8080/download?url=https://invalid.url"
    # Expected output (or similar):
    # {
    #   "error": "Failed to download video.",
    #   "stderr": "...",
    #   "stdout": "...",
    #   "url": "https://invalid.url"
    # }
    ```

---

## Deployment

This service is ready for deployment on any platform that supports Docker containers, such as **Railway**, Heroku, or Fly.io.

### Deploying on Railway

1.  Fork this repository to your GitHub account.
2.  Create a new project on Railway and select "Deploy from GitHub repo".
3.  Choose your forked repository.
4.  Railway will automatically detect the `Dockerfile` and build/deploy the service.
5.  In the project settings, go to the "Variables" tab and add your environment variables (e.g., `API_KEY`). You do not need to set `PORT` as Railway handles this automatically.
6.  If you need to use cookies, you can paste the content of your `cookies.txt` file into a variable (e.g., `COOKIE_FILE_CONTENT`) and modify the Docker CMD or have an entrypoint script to write this content to the `COOKIES_PATH` before the server starts. However, the volume mount method is more direct for local development.
7.  The health check endpoint (`/healthz`) can be used in Railway's service health monitoring settings to ensure the service is running correctly.
