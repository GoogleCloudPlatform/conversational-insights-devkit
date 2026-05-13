# Use an official Python runtime as a parent image
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
# First, upgrade pip to the latest version to ensure a robust dependency resolver
RUN pip install --upgrade pip
# Now, install the application's dependencies
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Command to run the application using Gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
