# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose the port Cloud Run will use
EXPOSE 8080

# Command to run Flask app
CMD ["python", "hdi_data.py"]

