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

# Set the port the app will run on
ENV PORT 8080

# Expose the port
EXPOSE 8080

# Specify the command to run on container startup
# Use Gunicorn as the WSGI server for production
# -w 4: 4 worker processes
# -b 0.0.0.0:$PORT: bind to all network interfaces on the specified port
# --timeout 300: 5-minute timeout for workers
CMD ["gunicorn", "-w", "2", "--timeout", "300", "-b", "0.0.0.0:8080", "app:app"]
