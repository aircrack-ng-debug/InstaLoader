# Use an official lightweight Python image.
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the content of the local src directory to the working directory
COPY app.py .

# Set the port the app will run on. Railway wird diesen Wert überschreiben.
ENV PORT 8080

# Expose the port
EXPOSE 8080

# Specify the command to run on container startup
# Verwende Umgebungsvariablen für eine flexible Konfiguration
CMD gunicorn -w 2 --timeout 300 -b 0.0.0.0:$PORT app:app